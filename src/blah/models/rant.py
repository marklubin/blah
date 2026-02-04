"""Rant, Piece, and Resource domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RantStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETE = "complete"


class PieceStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class ResourceType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOC = "doc"
    URL = "url"


class Resource(BaseModel):
    id: str
    type: ResourceType
    location: str


class Piece(BaseModel):
    id: str
    rant_id: str
    platform: str
    content: str
    target: dict | None = None
    scheduled_at: datetime | None = None
    status: PieceStatus = PieceStatus.DRAFT
    external_id: str | None = None
    external_url: str | None = None
    published_at: datetime | None = None
    error: str | None = None
    retry_count: int = 0
    manual_override: dict | None = None


class Rant(BaseModel):
    id: str
    title: str | None = None
    summary: str | None = None
    status: RantStatus = RantStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)
    pieces: list[Piece] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
