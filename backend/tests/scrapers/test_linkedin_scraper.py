"""Unit tests for LinkedIn scraper text processing helpers."""

from __future__ import annotations

from src.scrapers.linkedin import LinkedInScraper


def test_sanitize_description_prefers_about_the_job_block() -> None:
    """Sanitizer keeps useful content and trims noisy page footer blocks."""
    raw = (
        "Header content About the job Build APIs with Python and FastAPI. "
        "Set alert for similar jobs Footer links"
    )

    result = LinkedInScraper._sanitize_description_text(raw)

    assert result is not None
    assert result.startswith("About the job")
    assert "Set alert for similar jobs" not in result


def test_sanitize_description_truncates_excessively_long_text() -> None:
    """Sanitizer enforces the configured full-description maximum length."""
    raw = "About the job " + ("python " * 1000)

    result = LinkedInScraper._sanitize_description_text(raw)

    assert result is not None
    assert len(result) <= LinkedInScraper.MAX_DESCRIPTION_FULL_LENGTH


def test_build_short_description_truncates_long_text() -> None:
    """Short description helper truncates and appends ellipsis for long input."""
    raw = " ".join(["engineer"] * 200)

    result = LinkedInScraper._build_short_description(raw)

    assert result is not None
    assert len(result) <= LinkedInScraper.SHORT_DESCRIPTION_MAX_LENGTH + 3
    assert result.endswith("...")


def test_sanitize_description_removes_trailing_more_artifact() -> None:
    """Sanitizer removes trailing LinkedIn expansion affordance text."""
    raw = "About the job Build APIs with Python and FastAPI. … more"

    result = LinkedInScraper._sanitize_description_text(raw)

    assert result is not None
    assert not result.endswith("… more")
    assert result.endswith("FastAPI.")


def test_normalize_text_deduplicates_adjacent_repeated_title_phrase() -> None:
    """Title normalization should collapse repeated adjacent title phrases."""
    raw_title = "Software Engineer Software Engineer"

    result = LinkedInScraper._normalize_text(raw_title)

    assert result == "Software Engineer"


def test_normalize_text_keeps_non_duplicate_title_unchanged() -> None:
    """Title normalization should keep distinct titles unchanged."""
    raw_title = "Senior Software Engineer"

    result = LinkedInScraper._normalize_text(raw_title)

    assert result == "Senior Software Engineer"
