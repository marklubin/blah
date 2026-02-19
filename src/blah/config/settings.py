"""Application settings loaded from config.yaml and environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


def get_blah_home() -> Path:
    """Return the BLAH_HOME directory, defaulting to ~/.blah."""
    return Path(os.environ.get("BLAH_HOME", Path.home() / ".blah"))


class PlatformCredentials(BaseModel):
    """Credentials for a single platform."""

    enabled: bool = False
    # Bluesky
    handle: str | None = None
    app_password: str | None = None
    # Mastodon
    instance: str | None = None
    access_token: str | None = None
    # Twitter/X - OAuth 2.0 (writes via xdk)
    client_id: str | None = None
    client_secret: str | None = None
    oauth2_token: dict | None = None  # {access_token, refresh_token, expires_at, ...}
    # Twitter/X - twitterapi.io (reads)
    twitterapi_io_key: str | None = None
    # Reddit
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_username: str | None = None
    reddit_password: str | None = None
    # Discord (user token — selfbot)
    discord_token: str | None = None
    # Telegram
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_string: str | None = None


class ModelConfig(BaseModel):
    """Configuration for a model tier."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"


class ModelsConfig(BaseModel):
    """Model configuration for different task types."""

    triage: ModelConfig = Field(
        default_factory=lambda: ModelConfig(model="claude-sonnet-4-5")
    )
    research: ModelConfig = Field(
        default_factory=lambda: ModelConfig(model="claude-sonnet-4-5")
    )
    conversation: ModelConfig = Field(default_factory=ModelConfig)


class QueueConfig(BaseModel):
    """Configuration for the Cloudflare suggestion queue (KV-backed)."""

    enabled: bool = False
    account_id: str | None = None
    kv_namespace_id: str | None = None
    api_token: str | None = None
    worker_url: str | None = None
    worker_token: str | None = None


class ContextConfig(BaseModel):
    """Context.md configuration."""

    path: str = "context.md"
    max_tokens: int = 2000


class BlahSettings(BaseSettings):
    """Main application settings."""

    blah_home: Path = Field(default_factory=get_blah_home)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    platforms: dict[str, PlatformCredentials] = Field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.blah_home / "blah.db"

    @property
    def config_path(self) -> Path:
        return self.blah_home / "config.yaml"

    @property
    def context_path(self) -> Path:
        return self.blah_home / self.context.path

    @property
    def memory_json_path(self) -> Path:
        return self.blah_home / "memory.json"

    @property
    def resources_path(self) -> Path:
        return self.blah_home / "resources"

    def save(self) -> None:
        """Persist current settings (including refreshed tokens) to config.yaml."""
        data = {
            "models": self.models.model_dump(),
            "context": self.context.model_dump(),
            "queue": self.queue.model_dump(exclude_none=True),
            "platforms": {
                name: creds.model_dump(exclude_none=True)
                for name, creds in self.platforms.items()
            },
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, blah_home: Path | None = None) -> BlahSettings:
        """Load settings from config.yaml + environment, with blah_home override."""
        home = blah_home or get_blah_home()
        config_path = home / "config.yaml"

        config_data: dict = {}
        if config_path.exists():
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

        config_data["blah_home"] = home
        return cls(**config_data)
