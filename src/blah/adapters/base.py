"""Platform adapter abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PostResult:
    """Result of posting content to a platform."""

    external_id: str
    external_url: str
    platform: str
    metadata: dict = field(default_factory=dict)


@dataclass
class PostContent:
    """Content to be posted to a platform."""

    text: str
    reply_to: str | None = None
    images: list[str] | None = None
    link_card: str | None = None


class PlatformAdapter(ABC):
    """Abstract base for platform integrations.

    Each platform (Bluesky, Twitter, etc.) implements this interface.
    All methods are synchronous.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform identifier (e.g. 'bluesky', 'twitter')."""

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the platform. Called before any other operations."""

    @abstractmethod
    def post(self, content: PostContent) -> PostResult:
        """Create a new post on the platform."""

    @abstractmethod
    def delete_post(self, external_id: str) -> bool:
        """Delete a post by its platform-specific ID. Returns True if deleted."""

    @abstractmethod
    def get_post(self, external_id: str) -> dict | None:
        """Fetch a post by its platform-specific ID."""

    def post_thread(self, contents: list[PostContent]) -> list[PostResult]:
        """Post a thread (sequence of replies). Default implementation chains post()."""
        results = []
        reply_to = None
        for content in contents:
            if reply_to:
                content.reply_to = reply_to
            result = self.post(content)
            reply_to = result.external_id
            results.append(result)
        return results

    def get_timeline(
        self, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch the authenticated user's home timeline."""
        return {"items": [], "cursor": None}

    def get_author_feed(
        self, handle: str, limit: int = 50, cursor: str | None = None
    ) -> dict:
        """Fetch recent posts by a specific author."""
        return {"items": [], "cursor": None}

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search for posts matching a query."""
        return []

    def get_post_thread(self, uri: str, depth: int = 10) -> dict | None:
        """Fetch a post and its thread context (parents + replies)."""
        return None

    def get_profile(self, handle: str) -> dict | None:
        """Fetch a user profile."""
        return None

    def follow(self, handle: str) -> bool:
        """Follow a user. Returns True if successful."""
        return False
