"""Mock platform adapters for testing."""

from __future__ import annotations

from blah.adapters.base import PlatformAdapter, PostContent, PostResult


class MockPlatformAdapter(PlatformAdapter):
    """Mock adapter that records calls without hitting any API."""

    def __init__(self, platform: str = "bluesky", fail_on_post: bool = False):
        self._platform = platform
        self._fail_on_post = fail_on_post
        self._authenticated = False
        self.posts: list[PostContent] = []
        self.deleted: list[str] = []
        self._post_counter = 0

    @property
    def platform_name(self) -> str:
        return self._platform

    def authenticate(self) -> None:
        self._authenticated = True

    def post(self, content: PostContent) -> PostResult:
        if self._fail_on_post:
            raise RuntimeError("Mock post failure")

        self._post_counter += 1
        ext_id = f"mock://{self._platform}/{self._post_counter}"
        ext_url = f"https://{self._platform}.example.com/post/{self._post_counter}"
        self.posts.append(content)

        return PostResult(
            external_id=ext_id,
            external_url=ext_url,
            platform=self._platform,
        )

    def delete_post(self, external_id: str) -> bool:
        self.deleted.append(external_id)
        return True

    def get_post(self, external_id: str) -> dict | None:
        return {"id": external_id, "text": "mock post"}
