"""Config YAML schema models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformConfig(BaseModel):
    """Configuration for a single platform in config.yaml."""

    enabled: bool = False
    method: str = "api"


class BlueskyConfig(PlatformConfig):
    handle: str | None = None
    app_password: str | None = None


class TwitterConfig(PlatformConfig):
    consumer_key: str | None = None
    consumer_secret: str | None = None
    access_token: str | None = None
    access_token_secret: str | None = None


class ModelTierConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"


class ModelsYamlConfig(BaseModel):
    triage: ModelTierConfig = Field(
        default_factory=lambda: ModelTierConfig(model="claude-sonnet-4-5")
    )
    research: ModelTierConfig = Field(
        default_factory=lambda: ModelTierConfig(model="claude-sonnet-4-5")
    )
    conversation: ModelTierConfig = Field(default_factory=ModelTierConfig)


class ContextYamlConfig(BaseModel):
    path: str = "context.md"
    max_tokens: int = 2000


class ConfigYaml(BaseModel):
    """Top-level config.yaml schema."""

    models: ModelsYamlConfig = Field(default_factory=ModelsYamlConfig)
    context: ContextYamlConfig = Field(default_factory=ContextYamlConfig)
    platforms: dict[str, dict] = Field(default_factory=dict)
