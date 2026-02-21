"""Processed enrichment output for raw jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.models.base import BaseModel


class JobEnrichment(BaseModel):
    """Represents processed enrichment fields generated from a raw job."""

    __tablename__ = "job_enrichments"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "extractor_version",
            name="uq_job_enrichments_job_id_extractor_version",
        ),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_job_enrichments_salary_min_lte_salary_max",
        ),
        Index(
            "ix_job_enrichments_job_status_enriched_at_desc",
            "job_id",
            "status",
            desc("enriched_at"),
        ),
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    salary_max: Mapped[float | None] = mapped_column(
        Numeric(12, 2, asdecimal=False),
        nullable=True,
    )
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    salary_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_by_field: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    description_sections: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    @validates("skills")
    def validate_skills(self, key: str, value: list[str] | None) -> list[str] | None:
        """Validate skills payload shape.

        Args:
            key: SQLAlchemy attribute key.
            value: Skills list payload.

        Returns:
            The original payload when valid.

        Raises:
            ValueError: If skills is not a list of non-empty strings.
        """
        if value is None:
            return value
        if not isinstance(value, list):
            raise ValueError("skills must be a list of non-empty strings")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("skills must be a list of non-empty strings")
        return value

    @validates("confidence_by_field")
    def validate_confidence_by_field(
        self,
        key: str,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Validate confidence map payload.

        Args:
            key: SQLAlchemy attribute key.
            value: Confidence map payload.

        Returns:
            The original payload when valid.

        Raises:
            ValueError: If payload is not a JSON object.
        """
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("confidence_by_field must be an object")
        return value


__all__ = ["JobEnrichment"]
