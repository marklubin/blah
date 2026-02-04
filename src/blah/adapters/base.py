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
