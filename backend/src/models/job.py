"""Job ORM model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.models.base import BaseModel


class Job(BaseModel):
    """Represents a scraped job listing."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "external_id", "platform", name="uq_jobs_external_id_platform"
        ),
        CheckConstraint(
            "platform IN ('linkedin', 'seek', 'indeed')",
            name="ck_jobs_platform_valid",
        ),
        Index("ix_jobs_platform", "platform"),
        Index("ix_jobs_posted_date", "posted_date"),
        Index("ix_jobs_is_active", "is_active"),
    )

    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    salary_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    @validates("platform")
    def validate_platform(self, key: str, value: str) -> str:
        """Validate supported platform values."""
        allowed_platforms: set[str] = {"linkedin", "seek", "indeed"}
        if value not in allowed_platforms:
            allowed_values = ", ".join(sorted(allowed_platforms))
            raise ValueError(
                f"Invalid platform '{value}'. Allowed values: {allowed_values}."
            )
        return value

    @validates("skills")
    def validate_skills(self, key: str, value: list[str] | None) -> list[str] | None:
        """Validate skills as a list of strings."""
        if value is None:
            return value

        if not isinstance(value, list):
            raise ValueError("Invalid skills payload: expected a list of strings.")

        invalid_items = [
            item for item in value if not isinstance(item, str) or not item.strip()
        ]
        if invalid_items:
            raise ValueError(
                "Invalid skills payload: each skill must be a non-empty string."
            )

        return value

    @validates("salary_range")
    def validate_salary_range(
        self,
        key: str,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Validate salary_range structure and values."""
        if value is None:
            return value

        if not isinstance(value, dict):
            raise ValueError("Invalid salary_range payload: expected an object.")

        required_keys = {"min", "max", "currency"}
        missing_keys = required_keys - set(value.keys())
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(
                f"Invalid salary_range payload: missing required keys: {missing}."
            )

        min_salary = value.get("min")
        max_salary = value.get("max")
        currency = value.get("currency")

        if not isinstance(min_salary, (int, float)):
            raise ValueError("Invalid salary_range payload: 'min' must be numeric.")
        if not isinstance(max_salary, (int, float)):
            raise ValueError("Invalid salary_range payload: 'max' must be numeric.")
        if min_salary > max_salary:
            raise ValueError("Invalid salary_range payload: 'min' cannot exceed 'max'.")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError(
                "Invalid salary_range payload: 'currency' must be a non-empty string."
            )

        return value
