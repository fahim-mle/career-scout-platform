"""Pydantic schemas for job create, update, and response payloads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from src.models.job import ALLOWED_PLATFORMS


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
    posted_date: date | None = None
    scraped_at: datetime | None = None
    is_active: bool = True
    skills: list[str] | None = None
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
    posted_date: date | None = None
    scraped_at: datetime | None = None
    is_active: bool | None = None
    skills: list[str] | None = None
    salary_range: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class JobResponse(BaseModel):
    """Schema returned for persisted job records."""

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
    posted_date: date | None
    scraped_at: datetime
    is_active: bool
    skills: list[str] | None
    salary_range: dict[str, Any] | None

    model_config = ConfigDict(from_attributes=True)


__all__ = [
    "ALLOWED_PLATFORMS",
    "JobCreate",
    "JobResponse",
    "JobUpdate",
]
