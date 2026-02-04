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
    handle: str | None = None
    app_password: str | None = None
    instance: str | None = None
    access_token: str | None = None
    consumer_key: str | None = None
    consumer_secret: str | None = None
    access_token_secret: str | None = None


class ModelConfig(BaseModel):
    """Configuration for a model tier."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"


class ModelsConfig(BaseModel):
    """Model configuration for different task types."""

    triage: ModelConfig = Field(
        default_factory=lambda: ModelConfig(model="claude-3-haiku-20240307")
    )
    research: ModelConfig = Field(
        default_factory=lambda: ModelConfig(model="claude-3-haiku-20240307")
    )
    conversation: ModelConfig = Field(default_factory=ModelConfig)


class ContextConfig(BaseModel):
    """Context.md configuration."""

    path: str = "context.md"
    max_tokens: int = 2000


class BlahSettings(BaseSettings):
    """Main application settings."""

    blah_home: Path = Field(default_factory=get_blah_home)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
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
    def resources_path(self) -> Path:
        return self.blah_home / "resources"

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
