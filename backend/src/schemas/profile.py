"""Pydantic schemas for profile create, update, and response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SkillName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProfileCreate(BaseModel):
    """Schema for creating the singleton candidate profile."""

    name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    experience_years: int = Field(ge=0)
    skills: list[SkillName] = Field(min_length=1)
    preferences: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ProfileUpdate(BaseModel):
    """Schema for updating the singleton candidate profile."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    experience_years: int | None = Field(default=None, ge=0)
    skills: list[SkillName] | None = Field(default=None, min_length=1)
    preferences: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class ProfileResponse(BaseModel):
    """Schema returned for persisted profile records."""

    id: int
    created_at: datetime
    updated_at: datetime
    name: str
    location: str
    experience_years: int
    skills: list[str]
    preferences: dict[str, Any] | None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


__all__ = ["ProfileCreate", "ProfileResponse", "ProfileUpdate"]
