"""Triage service — fast relevance scoring with Haiku."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from blah.config.settings import BlahSettings
from blah.db.repository import FeedItemRepo
from blah.llm.client import LLMClient

logger = logging.getLogger(__name__)

# Score threshold for passing triage
TRIAGE_THRESHOLD = 0.3

# Batch size for triage calls
BATCH_SIZE = 20


@dataclass
class TriageResult:
    """Result of triaging a batch of items."""

    passed: list[dict]  # Items above threshold
    discarded: list[dict]  # Items below threshold
    total: int


class TriageService:
    """Score feed items for relevance using fast Haiku model."""

    def __init__(
        self,
        db: sqlite3.Connection,
        settings: BlahSettings,
        llm_client: LLMClient | None = None,
        memory: object | None = None,
    ):
        self._db = db
        self._settings = settings
        self._memory = memory
        self._feed_repo = FeedItemRepo(db)

        # Store config for creating per-thread LLM clients
        if llm_client:
            self._llm = llm_client
            self._llm_config = {
                "provider": llm_client.provider,
                "model": llm_client.model,
                "base_url": llm_client.base_url,
            }
        else:
            model_config = settings.models.triage
            self._llm_config = {
                "provider": model_config.provider,
                "model": model_config.model,
                "base_url": model_config.base_url,
            }
            self._llm = LLMClient(**self._llm_config)

        self._thread_local = threading.local()

    def triage_raw_items(self, limit: int = 1000) -> TriageResult:
        """Triage all raw items, updating their status."""
        items = self._feed_repo.list_by_status("raw", limit=limit)
        if not items:
            logger.info("No raw items to triage")
            return TriageResult(passed=[], discarded=[], total=0)

        context = self._load_context()
        return self._triage_batch(items, context)

    def triage_items(self, items: list[dict], context: str) -> TriageResult:
        """Triage a specific list of items."""
        return self._triage_batch(items, context)

    def _triage_batch(self, items: list[dict], context: str) -> TriageResult:
        """Score batches of items concurrently and update their status."""
        passed = []
        discarded = []
        max_workers = self._settings.concurrency.triage_workers

        batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_batch = {
                pool.submit(self._score_batch, batch, context): batch
                for batch in batches
            }
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    scores = future.result()

                    # DB writes on main thread (serialized)
                    for item, (score, reason) in zip(batch, scores, strict=False):
                        if score >= TRIAGE_THRESHOLD:
                            self._feed_repo.update(
                                item["id"],
                                status="triaged",
                                relevance_score=score,
                                triage_reason=reason,
                            )
                            item["relevance_score"] = score
                            item["triage_reason"] = reason
                            passed.append(item)
                            logger.debug(
                                "Item %s passed triage: %.2f - %s",
                                item["id"][:8], score, reason[:50],
                            )
                        else:
                            self._feed_repo.update(
                                item["id"],
                                status="discarded",
                                relevance_score=score,
                                triage_reason=reason,
                            )
                            discarded.append(item)
                            logger.debug(
                                "Item %s discarded: %.2f - %s",
                                item["id"][:8], score, reason[:50],
                            )
                except Exception as e:
                    logger.exception("Batch scoring failed: %s", e)
                    for item in batch:
                        discarded.append(item)

        logger.info(
            "Triage complete: %d passed, %d discarded",
            len(passed), len(discarded),
        )
        return TriageResult(passed=passed, discarded=discarded, total=len(items))

    def _get_thread_llm(self) -> LLMClient:
        """Get a per-thread LLM client to avoid connection pool contention."""
        if not hasattr(self._thread_local, "llm"):
            self._thread_local.llm = LLMClient(**self._llm_config)
        return self._thread_local.llm

    def _score_batch(
        self, items: list[dict], context: str
    ) -> list[tuple[float, str]]:
        """Score a batch of items using LLM.

        Returns list of (score, reason) tuples.
        """
        # Build the prompt
        items_text = "\n\n".join(
            f"[Item {i+1}]\n"
            f"Author: {item.get('author', 'unknown')}\n"
            f"Content: {item.get('content', '')[:500]}"
            for i, item in enumerate(items)
        )

        prompt = f"""You are scoring social media posts for relevance to a user's interests.

## User Context
{context}

## Items to Score
{items_text}

## Instructions
For each item, provide:
1. A relevance score from 0.0 to 1.0
2. A brief reason (1 sentence)

Score based on:
- Topic match with user interests
- Author relevance (are they someone the user follows or should know?)
- Engagement potential (would user want to respond?)

## Output Format
Return a JSON array with one object per item:
[
  {{"score": 0.8, "reason": "Directly addresses AI memory architecture"}},
  {{"score": 0.2, "reason": "Off-topic, about cooking"}},
  ...
]

Return ONLY the JSON array, no other text."""

        try:
            llm = self._get_thread_llm()
            response = llm.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
            )

            # Parse the response — LLMResponse has .text; Anthropic Message has .content[0].text
            if hasattr(response, "text") and isinstance(response.text, str):
                text = response.text.strip()
            else:
                text = response.content[0].text.strip()
            # Handle potential markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            scores_data = json.loads(text)

            # Extract scores and reasons
            results = []
            for item_score in scores_data:
                score = float(item_score.get("score", 0.0))
                reason = item_score.get("reason", "No reason provided")
                results.append((score, reason))

            # Pad with zeros if LLM returned fewer items
            while len(results) < len(items):
                results.append((0.0, "Scoring error"))

            return results

        except Exception as e:
            logger.exception("Failed to score batch: %s", e)
            # Return zeros for all items on error
            return [(0.0, f"Scoring error: {e}")] * len(items)

    def _load_context(self) -> str:
        """Load context — from memory provider if available, else context.md."""
        if self._memory is not None:
            try:
                ctx = self._memory.get_context()
                return ctx.to_prompt_text()
            except Exception:
                logger.exception("Memory provider failed, falling back to context.md")
        try:
            return self._settings.context_path.read_text()
        except FileNotFoundError:
            return "(No context configured)"
