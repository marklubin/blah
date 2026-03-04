"""Triage service — fast relevance scoring with batch LLM inference."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass

from blah.config.settings import BlahSettings
from blah.db.repository import FeedItemRepo
from blah.llm.client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)

# Score threshold for passing triage
TRIAGE_THRESHOLD = 0.5

# Batch size for triage calls
BATCH_SIZE = 20


@dataclass
class TriageResult:
    """Result of triaging a batch of items."""

    passed: list[dict]  # Items above threshold
    discarded: list[dict]  # Items below threshold
    total: int


class TriageService:
    """Score feed items for relevance using batch LLM inference."""

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

        if llm_client:
            self._llm = llm_client
        else:
            model_config = settings.models.triage
            self._llm = LLMClient(
                provider=model_config.provider,
                model=model_config.model,
                base_url=model_config.base_url,
            )

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
        """Score all items via a single batch LLM call."""
        passed = []
        discarded = []

        batches = [items[i : i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

        # Build all prompts upfront
        requests = []
        for batch in batches:
            prompt = self._build_score_prompt(batch, context)
            requests.append({"messages": [{"role": "user", "content": prompt}], "max_tokens": 2000})

        # Single batch call — one HTTP request to Modal
        logger.info("Sending %d triage batches (%d items) via batch_chat", len(batches), len(items))
        responses = self._llm.batch_chat(requests)

        # Process results
        for batch, response in zip(batches, responses):
            try:
                scores = self._parse_scores(response, len(batch))
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

    def _build_score_prompt(self, items: list[dict], context: str) -> str:
        """Build the scoring prompt for a batch of items."""
        items_text = "\n\n".join(
            f"[Item {i+1}] ({item.get('platform', 'unknown')})\n"
            f"Author: {item.get('author', 'unknown')}\n"
            f"Content: {item.get('content', '')[:500]}"
            for i, item in enumerate(items)
        )

        return f"""You are scoring social media posts for relevance to a user's interests.

## User Context
{context}

## Items to Score
{items_text}

## Instructions
For each item, provide:
1. A relevance score from 0.0 to 1.0
2. A brief reason (1 sentence)

Score strictly on a continuous 0.0-1.0 scale:
- 0.0-0.2: Off-topic, no connection to user's interests
- 0.3-0.4: Tangential — vaguely related but no engagement opportunity
- 0.5-0.6: Relevant topic but generic — user could engage but wouldn't stand out
- 0.7-0.8: Directly relevant — clear engagement opportunity matching user's expertise
- 0.9-1.0: High-value signal — user has unique insight to contribute, high-visibility thread

Be discriminating. Most items should score below 0.5. Only items where the user
has something specific and valuable to add should score 0.7+.

Use the full continuous range (e.g. 0.35, 0.62, 0.74) — do NOT round to fixed values.

## Output Format
Return a JSON array with one object per item:
[
  {{"score": 0.82, "reason": "Directly addresses AI memory architecture, user has CDR framework insight"}},
  {{"score": 0.15, "reason": "Off-topic, about cooking"}},
  ...
]

Return ONLY the JSON array, no other text."""

    def _parse_scores(self, response: LLMResponse, expected_count: int) -> list[tuple[float, str]]:
        """Parse LLM response into (score, reason) tuples."""
        text = response.text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        scores_data = json.loads(text)

        results = []
        for item_score in scores_data:
            score = float(item_score.get("score", 0.0))
            reason = item_score.get("reason", "No reason provided")
            results.append((score, reason))

        # Pad with zeros if LLM returned fewer items
        while len(results) < expected_count:
            results.append((0.0, "Scoring error"))

        return results

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
