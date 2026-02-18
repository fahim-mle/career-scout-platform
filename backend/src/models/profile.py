"""Profile ORM model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.models.base import BaseModel


class Profile(BaseModel):
    """Represents the single candidate profile used for matching."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "experience_years >= 0",
            name="ck_profiles_experience_years_non_negative",
        ),
        CheckConstraint(
            "jsonb_typeof(skills) = 'array' AND jsonb_array_length(skills) > 0",
            name="ck_profiles_skills_non_empty_array",
        ),
        CheckConstraint(
            "preferences IS NULL OR jsonb_typeof(preferences) = 'object'",
            name="ck_profiles_preferences_object",
        ),
        Index("ix_profiles_location", "location"),
        Index("ix_profiles_skills_gin", "skills", postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    experience_years: Mapped[int] = mapped_column(Integer, nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    @validates("experience_years")
    def validate_experience_years(self, key: str, value: int) -> int:
        """Validate experience years as a non-negative integer.

        Args:
            key: SQLAlchemy field key.
            value: Experience years value to validate.

        Returns:
            Validated experience years.

        Raises:
            ValueError: If value is not a valid non-negative integer.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("experience_years must be an integer.")
        if value < 0:
            raise ValueError("experience_years cannot be negative.")
        return value

    @validates("skills")
    def validate_skills(self, key: str, value: list[str]) -> list[str]:
        """Validate skills as a non-empty list of strings.

        Args:
            key: SQLAlchemy field key.
            value: Skills payload to validate.

        Returns:
            Validated skills list.

        Raises:
            ValueError: If skills payload is invalid.
        """
        if not isinstance(value, list):
            raise ValueError("skills must be a list of strings.")
        if not value:
            raise ValueError("skills must contain at least one skill.")
        if any(not isinstance(skill, str) or not skill.strip() for skill in value):
            raise ValueError("skills must contain only non-empty strings.")
        return value

    @validates("preferences")
    def validate_preferences(
        self,
        key: str,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Validate optional preferences as an object payload.

        Args:
            key: SQLAlchemy field key.
            value: Preferences payload to validate.

        Returns:
            Validated preferences payload.

        Raises:
            ValueError: If preferences payload is not an object.
        """
        if value is not None and not isinstance(value, dict):
            raise ValueError("preferences must be an object when provided.")
        return value


__all__ = ["Profile"]
