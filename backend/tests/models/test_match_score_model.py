"""Unit tests for MatchScore model validations."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.match_score import MatchScore


def test_match_score_valid_creation() -> None:
    """Model accepts a valid score and category."""
    instance = MatchScore(
        job_id=1,
        profile_id=1,
        relevance_score=92,
        category="Most Relevant",
        explanation="Strong skill overlap and matching seniority.",
        scored_at=datetime.now(timezone.utc),
    )

    assert instance.job_id == 1
    assert instance.profile_id == 1
    assert instance.relevance_score == 92
    assert instance.category == "Most Relevant"


def test_match_score_invalid_relevance_score_rejected() -> None:
    """Model rejects relevance scores outside the accepted range."""
    with pytest.raises(ValueError, match="relevance_score must be between 0 and 100"):
        MatchScore(
            job_id=1,
            profile_id=1,
            relevance_score=101,
            category="Relevant",
            explanation="Out-of-range score should fail.",
            scored_at=datetime.now(timezone.utc),
        )


def test_match_score_invalid_category_rejected() -> None:
    """Model rejects categories outside the supported set."""
    with pytest.raises(ValueError, match="Invalid category"):
        MatchScore(
            job_id=1,
            profile_id=1,
            relevance_score=50,
            category="Unknown",
            explanation="Invalid category should fail.",
            scored_at=datetime.now(timezone.utc),
        )
