"""Pydantic schemas for match score payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MatchCategory = Literal[
    "Most Relevant",
    "Relevant",
    "Somewhat Relevant",
    "Not Relevant",
]


class MatchScoreCreate(BaseModel):
    """Schema for creating a match score."""

    job_id: int = Field(gt=0)
    profile_id: int = Field(gt=0)
    relevance_score: int = Field(ge=0, le=100)
    category: MatchCategory
    explanation: str = Field(min_length=1)
    scored_at: datetime | None = None
    scorer_version: str | None = None

    model_config = ConfigDict(extra="forbid")


class MatchScoreUpdate(BaseModel):
    """Schema for updating a match score."""

    relevance_score: int | None = Field(default=None, ge=0, le=100)
    category: MatchCategory | None = None
    explanation: str | None = Field(default=None, min_length=1)
    scored_at: datetime | None = None
    scorer_version: str | None = None

    model_config = ConfigDict(extra="forbid")


class MatchScoreResponse(BaseModel):
    """Schema returned for persisted match score records."""

    id: int
    created_at: datetime
    updated_at: datetime
    job_id: int
    profile_id: int
    relevance_score: int
    category: MatchCategory
    explanation: str
    scored_at: datetime
    scorer_version: str | None = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


__all__ = [
    "MatchCategory",
    "MatchScoreCreate",
    "MatchScoreResponse",
    "MatchScoreUpdate",
]
