"""Research service — deep enrichment with suggested engagement angles."""

from __future__ import annotations

import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from blah.adapters.base import PlatformAdapter
from blah.config.settings import BlahSettings
from blah.db.repository import FeedItemRepo
from blah.llm.client import LLMClient, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class Enrichment:
    """Enrichment data for a feed item."""

    full_thread: str | None = None
    author_context: str | None = None
    related_posts: list[str] = field(default_factory=list)
    suggested_angles: list[str] = field(default_factory=list)
    relevance_notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "full_thread": self.full_thread,
            "author_context": self.author_context,
            "related_posts": self.related_posts,
            "suggested_angles": self.suggested_angles,
            "relevance_notes": self.relevance_notes,
        }


@dataclass
class ResearchResult:
    """Result of researching items."""

    researched: list[dict]
    failed: list[dict]
    total: int


class ResearchService:
    """Enrich triaged items with context and suggested engagement angles."""

    def __init__(
        self,
        db: sqlite3.Connection,
        settings: BlahSettings,
        adapters: dict[str, PlatformAdapter],
        llm_client: LLMClient | None = None,
        memory: object | None = None,
    ):
        self._db = db
        self._settings = settings
        self._adapters = adapters
        self._memory = memory
        self._feed_repo = FeedItemRepo(db)

        if llm_client:
            self._llm = llm_client
        else:
            model_config = settings.models.research
            self._llm = LLMClient(
                provider=model_config.provider,
                model=model_config.model,
                base_url=model_config.base_url,
            )

    def research_triaged_items(self, limit: int = 200) -> ResearchResult:
        """Research all triaged items, updating their enrichment."""
        items = self._feed_repo.list_by_status("triaged", limit=limit)
        if not items:
            logger.info("No triaged items to research")
            return ResearchResult(researched=[], failed=[], total=0)

        context = self._load_context()
        return self._research_items(items, context)

    def research_item(self, item: dict, context: str) -> Enrichment | None:
        """Research a single item and return enrichment."""
        try:
            enrichment = self._fetch_context(item)
            prompt = self._build_angles_prompt(item, enrichment, context)
            responses = self._llm.batch_chat([
                {"messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}
            ])
            angles = self._parse_angles(responses[0])
            enrichment.suggested_angles = angles.get("angles", [])
            enrichment.relevance_notes = angles.get("relevance_notes", "")
            return enrichment
        except Exception as e:
            logger.exception("Failed to research item %s: %s", item["id"], e)
            return None

    def _research_items(self, items: list[dict], context: str) -> ResearchResult:
        """Research items: concurrent I/O fetch, then batch LLM inference."""
        researched = []
        failed = []
        max_workers = self._settings.concurrency.research_workers

        # Phase 1: Fetch thread + author context concurrently (platform I/O)
        enrichments: dict[str, Enrichment] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_item = {
                pool.submit(self._fetch_context, item): item
                for item in items
            }
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    enrichments[item["id"]] = future.result()
                except Exception as e:
                    logger.exception("Failed to fetch context for %s: %s", item["id"], e)
                    failed.append(item)

        # Phase 2: Batch LLM inference for engagement angles
        items_to_research = [item for item in items if item["id"] in enrichments]
        if not items_to_research:
            logger.info("No items with context to research")
            return ResearchResult(researched=researched, failed=failed, total=len(items))

        requests = []
        for item in items_to_research:
            enrichment = enrichments[item["id"]]
            prompt = self._build_angles_prompt(item, enrichment, context)
            requests.append({"messages": [{"role": "user", "content": prompt}], "max_tokens": 1000})

        logger.info("Sending %d research prompts via batch_chat", len(requests))
        responses = self._llm.batch_chat(requests)

        for item, response in zip(items_to_research, responses):
            enrichment = enrichments[item["id"]]
            try:
                angles = self._parse_angles(response)
                enrichment.suggested_angles = angles.get("angles", [])
                enrichment.relevance_notes = angles.get("relevance_notes", "")

                self._feed_repo.update(
                    item["id"],
                    status="researched",
                    enrichment=enrichment.to_dict(),
                )
                item["enrichment"] = enrichment.to_dict()
                researched.append(item)
                logger.info(
                    "Researched item %s: %d angles suggested",
                    item["id"][:8],
                    len(enrichment.suggested_angles),
                )
            except Exception as e:
                logger.exception("Failed to research item %s: %s", item["id"], e)
                failed.append(item)

        logger.info(
            "Research complete: %d researched, %d failed",
            len(researched), len(failed),
        )
        return ResearchResult(
            researched=researched, failed=failed, total=len(items)
        )

    def _fetch_context(self, item: dict) -> Enrichment:
        """Fetch thread and author context from platform APIs."""
        platform = item.get("platform", "bluesky")
        adapter = self._adapters.get(platform)
        enrichment = Enrichment()

        if adapter and item.get("external_id"):
            try:
                thread = adapter.get_post_thread(item["external_id"])
                if thread:
                    enrichment.full_thread = self._format_thread(thread)
            except Exception as e:
                logger.warning("Could not fetch thread: %s", e)

        author_handle = self._extract_author_handle(item)
        if adapter and author_handle:
            try:
                profile = adapter.get_profile(author_handle)
                if profile:
                    enrichment.author_context = self._format_author(profile)
                recent = adapter.get_author_feed(author_handle, limit=5)
                if recent and recent.get("items"):
                    enrichment.related_posts = [
                        p.get("uri") for p in recent["items"][:3]
                    ]
            except Exception as e:
                logger.warning("Could not fetch author info: %s", e)

        return enrichment

    def _build_angles_prompt(
        self, item: dict, enrichment: Enrichment, context: str
    ) -> str:
        """Build the engagement angles prompt."""
        return f"""You are helping someone decide how to engage with a social media post.

## Who You're Helping (their context)
{context}

## The Post to Engage With
Author: {item.get('author', 'unknown')}
Content: {item.get('content', '')}

## Thread Context
{enrichment.full_thread or '(No thread context available)'}

## Author Background
{enrichment.author_context or '(No author info available)'}

## Your Task
1. Explain why this post is relevant to the user (1-2 sentences)
2. Suggest 2-3 specific engagement angles that:
   - Match the user's voice and expertise
   - Add genuine value to the conversation
   - Feel natural, not forced or promotional
   - Could lead to meaningful connection

## Output Format
Return JSON:
{{
  "relevance_notes": "Why this matters to them...",
  "angles": [
    "Angle 1: Specific suggestion with example wording...",
    "Angle 2: Different approach...",
    "Angle 3: Optional third angle..."
  ]
}}

Return ONLY the JSON, no other text."""

    def _parse_angles(self, response: LLMResponse) -> dict:
        """Parse LLM response into angles dict."""
        text = response.text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.loads(text)

    def _format_thread(self, thread: dict) -> str:
        """Format a thread dict into readable text."""
        parts = []

        for parent in thread.get("parents", []):
            author = parent.get("author", {}).get("handle", "unknown")
            text = parent.get("text", "")
            parts.append(f"@{author}: {text}")

        post = thread.get("post", {})
        if post:
            author = post.get("author", {}).get("handle", "unknown")
            text = post.get("text", "")
            parts.append(f">>> @{author}: {text}")

        for reply in thread.get("replies", [])[:3]:
            author = reply.get("author", {}).get("handle", "unknown")
            text = reply.get("text", "")
            parts.append(f"  └ @{author}: {text}")

        return "\n\n".join(parts)

    def _format_author(self, profile: dict) -> str:
        """Format a profile dict into readable text."""
        parts = [
            f"Handle: @{profile.get('handle', 'unknown')}",
        ]
        if profile.get("display_name"):
            parts.append(f"Name: {profile['display_name']}")
        if profile.get("description"):
            parts.append(f"Bio: {profile['description']}")
        if profile.get("followers_count"):
            parts.append(f"Followers: {profile['followers_count']}")
        return "\n".join(parts)

    def _extract_author_handle(self, item: dict) -> str | None:
        """Extract author handle from item."""
        author = item.get("author")
        if isinstance(author, dict):
            return author.get("handle")
        if isinstance(author, str) and not author.startswith("did:"):
            return author
        return None

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
