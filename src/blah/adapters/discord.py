"""Discord adapter - thin proxy to MCP router's Discord backend."""

from __future__ import annotations

import logging
import os

import httpx

from blah.adapters.base import PlatformAdapter, PostContent, PostResult

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    """Discord platform adapter that proxies through the MCP router."""

    def __init__(self, router_url: str):
        self._router_url = router_url
        self._username: str | None = None
        self._user_id: str | None = None
        self._client = httpx.Client(
            base_url=f'{router_url}/discord',
            timeout=15,
        )

    @property
    def platform_name(self) -> str:
        return "discord"

    def authenticate(self) -> None:
        """Validate token via the router."""
        resp = self._client.get("/validate")
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Discord auth failed: {data['error']}")
        self._username = data.get("username")
        self._user_id = data.get("user_id")
        logger.info("Authenticated to Discord (via router) as %s", self._username)

    # -- Discord-specific read operations ----------------------------------

    def get_guilds(self) -> list[dict]:
        """List servers the user is a member of."""
        try:
            resp = self._client.get("/guilds")
            resp.raise_for_status()
            data = resp.json()
            return data.get("guilds", [])
        except Exception:
            logger.exception("Failed to fetch guilds from router")
            return []

    def get_guild_channels(self, guild_id: str) -> list[dict]:
        """List channels in a Discord server."""
        try:
            resp = self._client.get(f"/guilds/{guild_id}/channels")
            resp.raise_for_status()
            data = resp.json()
            return data.get("channels", [])
        except Exception:
            logger.exception("Failed to fetch channels for guild %s", guild_id)
            return []

    def get_channel_messages(
        self, channel_id: str, limit: int = 50, guild_id: str = "", channel_name: str = ""
    ) -> list[dict]:
        """Fetch messages from a Discord channel."""
        try:
            resp = self._client.get(
                f"/channels/{channel_id}/messages",
                params={"limit": limit, "guild_id": guild_id, "channel_name": channel_name},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("messages", [])
        except Exception:
            logger.exception("Failed to fetch messages from channel %s", channel_id)
            return []

    # -- PlatformAdapter interface -----------------------------------------

    def get_post(self, external_id: str) -> dict | None:
        """Fetch a specific message by discord:guild_id/channel_id/message_id."""
        try:
            parts = external_id.replace("discord:", "").split("/")
            if len(parts) != 3:
                logger.error("Invalid Discord external_id format: %s", external_id)
                return None
            guild_id, channel_id, message_id = parts

            resp = self._client.get(
                f"/channels/{channel_id}/messages",
                params={"limit": 1, "guild_id": guild_id},
            )
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("messages", [])
            # Find the specific message
            for msg in messages:
                if msg.get("external_id") == external_id:
                    return msg
            # Fallback: if we got exactly one result, return it
            if messages:
                return messages[0]
            return None
        except Exception:
            logger.exception("Failed to fetch message %s", external_id)
            return None

    def search_posts(self, query: str, limit: int = 25) -> list[dict]:
        """Search is not supported via Discord REST API."""
        logger.warning("Discord search_posts not supported")
        return []

    def post(self, content: PostContent) -> PostResult:
        """Send a message to a channel.

        content.reply_to should be the channel ID to post into.
        """
        if not content.reply_to:
            raise ValueError("Discord post requires reply_to set to channel_id")

        channel_id = content.reply_to
        resp = self._client.post(
            f"/channels/{channel_id}/messages",
            json={"content": content.text},
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", data)

        msg_id = msg.get("id", "unknown")
        external_id = f"discord:unknown/{channel_id}/{msg_id}"
        url = f"https://discord.com/channels/@me/{channel_id}/{msg_id}"

        logger.info("Posted message to channel %s via router", channel_id)

        return PostResult(
            external_id=external_id,
            external_url=url,
            platform="discord",
            metadata={"message_id": msg_id, "channel_id": channel_id},
        )

    def delete_post(self, external_id: str) -> bool:
        """Delete a message."""
        try:
            parts = external_id.replace("discord:", "").split("/")
            if len(parts) != 3:
                logger.error("Invalid Discord external_id format: %s", external_id)
                return False
            _guild_id, channel_id, message_id = parts

            resp = self._client.delete(
                f"/channels/{channel_id}/messages/{message_id}"
            )
            resp.raise_for_status()
            logger.info("Deleted message %s via router", external_id)
            return True
        except Exception:
            logger.exception("Failed to delete message %s", external_id)
            return False
