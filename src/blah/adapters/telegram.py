"""Telegram adapter — read-only monitoring via Telethon."""
from __future__ import annotations

import logging

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """Read-only Telegram adapter for monitoring public channels."""

    def __init__(self, api_id: int, api_hash: str, session_string: str):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_string = session_string
        self._client: TelegramClient | None = None

    @property
    def platform_name(self) -> str:
        return "telegram"

    def authenticate(self) -> None:
        """Connect to Telegram using StringSession."""
        self._client = TelegramClient(
            StringSession(self._session_string),
            self._api_id,
            self._api_hash,
        )
        self._client.connect()
        if not self._client.is_user_authorized():
            raise RuntimeError(
                "Telegram session is not authorized. "
                "Run scripts/telegram_auth.py to generate a new session string."
            )
        me = self._client.get_me()
        logger.info("Authenticated to Telegram as %s", me.username or me.id)

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        return self._client

    def get_channel_messages(
        self, channel_id: str, limit: int = 50, **kwargs
    ) -> list[dict]:
        """Fetch messages from a Telegram channel.

        Args:
            channel_id: Channel username (without @) or numeric ID
            limit: Max messages to fetch
            **kwargs: Swallows extra args from pipeline (guild_id, channel_name, etc.)
        """
        try:
            entity = self.client.get_entity(channel_id)
            messages = self.client.get_messages(entity, limit=limit)

            items = []
            for msg in messages:
                if not msg.text:
                    continue

                # Build author info
                sender = msg.sender
                if sender:
                    author_handle = getattr(sender, "username", None) or str(sender.id)
                    author_name = getattr(sender, "first_name", "") or author_handle
                else:
                    author_handle = channel_id
                    author_name = channel_id

                items.append({
                    "external_id": f"tg_{channel_id}_{msg.id}",
                    "uri": f"tg_{channel_id}_{msg.id}",
                    "url": f"https://t.me/{channel_id}/{msg.id}",
                    "text": msg.text,
                    "author": {
                        "handle": author_handle,
                        "display_name": author_name,
                    },
                    "created_at": msg.date.isoformat() if msg.date else None,
                    "like_count": 0,
                    "repost_count": msg.forwards or 0,
                    "reply_count": 0,
                })

            return items
        except Exception:
            logger.exception("Failed to fetch messages from Telegram channel %s", channel_id)
            return []

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a single message by tg_{channel}_{msg_id}."""
        try:
            # Parse external_id: tg_{channel}_{msg_id}
            parts = external_id.split("_", 2)
            if len(parts) != 3 or parts[0] != "tg":
                logger.error("Invalid Telegram external_id format: %s", external_id)
                return None

            channel = parts[1]
            msg_id = int(parts[2])

            entity = self.client.get_entity(channel)
            messages = self.client.get_messages(entity, ids=[msg_id])

            if not messages or not messages[0]:
                return None

            msg = messages[0]
            return {
                "external_id": external_id,
                "text": msg.text or "",
                "url": f"https://t.me/{channel}/{msg_id}",
                "like_count": 0,
                "repost_count": msg.forwards or 0,
                "reply_count": 0,
                "created_at": msg.date.isoformat() if msg.date else None,
            }
        except Exception:
            logger.exception("Failed to fetch Telegram message %s", external_id)
            return None

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search is not supported for Telegram channels."""
        logger.warning("Telegram search_posts not supported")
        return []

    # -- Write operations (not supported) --

    def post(self, content: PostContent) -> PostResult:
        raise NotImplementedError("Telegram adapter is read-only")

    def delete_post(self, external_id: str) -> bool:
        raise NotImplementedError("Telegram adapter is read-only")

    def follow(self, handle: str) -> bool:
        """Join a channel is not supported via adapter."""
        return False
