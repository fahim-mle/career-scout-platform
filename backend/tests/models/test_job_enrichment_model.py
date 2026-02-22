"""Unit tests for JobEnrichment model-level validators."""

from __future__ import annotations

import pytest

from src.models.job_enrichment import JobEnrichment


def test_description_sections_validation_accepts_valid_shape() -> None:
    """Validator should accept list of section objects with non-empty fields."""
    enrichment = JobEnrichment(
        job_id=1,
        extractor_version="heuristic-v1",
        status="partial",
        description_sections=[
            {
                "title": "Overview",
                "items": ["Build APIs", "Collaborate with product"],
            }
        ],
    )

    assert enrichment.description_sections == [
        {
            "title": "Overview",
            "items": ["Build APIs", "Collaborate with product"],
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-list",
        [{"title": "", "items": ["x"]}],
        [{"title": "Overview", "items": [""]}],
        [{"title": "Overview", "items": "not-a-list"}],
    ],
)
def test_description_sections_validation_rejects_invalid_shapes(
    payload: object,
) -> None:
    """Validator should reject malformed description section payloads."""
    with pytest.raises(ValueError, match="description_sections"):
        JobEnrichment(
            job_id=1,
            extractor_version="heuristic-v1",
            status="partial",
            description_sections=payload,
        )
