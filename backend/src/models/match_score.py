"""Match score ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.models.base import BaseModel

ALLOWED_MATCH_CATEGORIES: tuple[str, ...] = (
    "Most Relevant",
    "Relevant",
    "Somewhat Relevant",
    "Not Relevant",
)
MATCH_CATEGORY_CHECK_CONDITION = f"category IN ({', '.join(repr(category) for category in ALLOWED_MATCH_CATEGORIES)})"


class MatchScore(BaseModel):
    """Represents a relevance score between a job and profile."""

    __tablename__ = "match_scores"
    __table_args__ = (
        UniqueConstraint("job_id", "profile_id", name="uq_match_scores_job_profile"),
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 100",
            name="ck_match_scores_relevance_score_range",
        ),
        CheckConstraint(
            MATCH_CATEGORY_CHECK_CONDITION,
            name="ck_match_scores_category_valid",
        ),
        Index("ix_match_scores_profile_id", "profile_id"),
        Index("ix_match_scores_relevance_score_desc", desc("relevance_score")),
        Index("ix_match_scores_scored_at_desc", desc("scored_at")),
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    scorer_version: Mapped[str | None] = mapped_column(String(100))

    @validates("relevance_score")
    def validate_relevance_score(self, key: str, value: int) -> int:
        """Validate relevance score within the supported percentage range.

        Args:
            key: SQLAlchemy attribute key.
            value: Relevance score value.

        Returns:
            Validated relevance score.

        Raises:
            ValueError: If score is not an integer between 0 and 100.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("relevance_score must be an integer.")
        if value < 0 or value > 100:
            raise ValueError("relevance_score must be between 0 and 100.")
        return value

    @validates("category")
    def validate_category(self, key: str, value: str) -> str:
        """Validate category against the supported label set.

        Args:
            key: SQLAlchemy attribute key.
            value: Category label.

        Returns:
            Validated category label.

        Raises:
            ValueError: If category is not one of the allowed values.
        """
        if value not in ALLOWED_MATCH_CATEGORIES:
            allowed_values = ", ".join(ALLOWED_MATCH_CATEGORIES)
            raise ValueError(
                f"Invalid category '{value}'. Allowed values: {allowed_values}."
            )
        return value


__all__ = ["ALLOWED_MATCH_CATEGORIES", "MatchScore"]
