"""Pydantic schemas for job create, update, and response payloads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from src.models.job import ALLOWED_PLATFORMS

MAX_RAW_HTML_LENGTH = 100_000


class JobCreate(BaseModel):
    """Schema for creating a new job listing."""

    external_id: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=20)
    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    job_type: str | None = Field(default=None, max_length=50)
    description_short: str | None = None
    description_full: str | None = None
    raw_html: str | None = Field(default=None, max_length=MAX_RAW_HTML_LENGTH)
    metadata: dict[str, Any] | None = None
    posted_date: date | None = None
    scraped_at: datetime | None = None
    is_active: bool = True
    # DEPRECATED: Use job_enrichments.skills instead. Will be removed in a future migration.
    skills: list[str] | None = None
    # DEPRECATED: Use job_enrichments salary fields instead. Will be removed in a future migration.
    salary_range: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class JobUpdate(BaseModel):
    """Schema for updating an existing job listing."""

    external_id: str | None = Field(default=None, min_length=1, max_length=255)
    platform: str | None = Field(default=None, min_length=1, max_length=20)
    url: AnyHttpUrl | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    company: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    job_type: str | None = Field(default=None, max_length=50)
    description_short: str | None = None
    description_full: str | None = None
    raw_html: str | None = Field(default=None, max_length=MAX_RAW_HTML_LENGTH)
    metadata: dict[str, Any] | None = None
    posted_date: date | None = None
    scraped_at: datetime | None = None
    is_active: bool | None = None
    # DEPRECATED: Use job_enrichments.skills instead. Will be removed in a future migration.
    skills: list[str] | None = None
    # DEPRECATED: Use job_enrichments salary fields instead. Will be removed in a future migration.
    salary_range: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class RawJobResponse(BaseModel):
    """Schema returned for persisted raw scraped job records."""

    id: int
    created_at: datetime
    updated_at: datetime
    external_id: str
    platform: str
    url: str
    title: str
    company: str
    location: str
    job_type: str | None
    description_short: str | None
    description_full: str | None
    raw_html: str | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="platform_metadata",
    )
    posted_date: date | None
    scraped_at: datetime
    is_active: bool
    # DEPRECATED: Use job_enrichments.skills instead. Will be removed in a future migration.
    skills: list[str] | None
    # DEPRECATED: Use job_enrichments salary fields instead. Will be removed in a future migration.
    salary_range: dict[str, Any] | None
    relevance_score: int | None = None

    model_config = ConfigDict(from_attributes=True)


class EnrichedJobResponse(BaseModel):
    """Schema returned for jobs enriched with processed metadata."""

    id: int
    created_at: datetime
    updated_at: datetime
    external_id: str
    platform: str
    url: str
    title: str
    company: str
    location: str
    description_short: str | None
    description_full: str | None
    raw_html: str | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias="platform_metadata",
    )
    posted_date: date | None
    scraped_at: datetime
    is_active: bool
    # DEPRECATED: Use job_enrichments.skills instead. Will be removed in a future migration.
    skills: list[str] | None = None
    job_type: str | None = None
    # DEPRECATED: Use job_enrichments salary fields instead. Will be removed in a future migration.
    salary_range: dict[str, Any] | None = None
    enrichment_status: str | None = None
    enrichment_version: str | None = None
    enrichment_updated_at: datetime | None = None
    description_sections: list[dict[str, Any]] | None = None
    relevance_score: int | None = None

    model_config = ConfigDict(from_attributes=True)


JobResponse = RawJobResponse


__all__ = [
    "ALLOWED_PLATFORMS",
    "EnrichedJobResponse",
    "JobCreate",
    "JobResponse",
    "RawJobResponse",
    "JobUpdate",
]
