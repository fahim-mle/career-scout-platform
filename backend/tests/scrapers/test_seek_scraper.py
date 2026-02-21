"""Unit tests for Seek scraper helpers."""

from __future__ import annotations

from src.scrapers.seek import SeekScraper


def test_extract_external_id_from_seek_url() -> None:
    """External id should be parsed from canonical Seek job URL."""
    url = "https://www.seek.com.au/job/81234567?type=promoted"

    assert SeekScraper._extract_external_id(url) == "81234567"


def test_extract_external_id_returns_none_for_invalid_url() -> None:
    """Invalid Seek URL should not produce an external id."""
    assert SeekScraper._extract_external_id("https://www.seek.com.au/jobs") is None


def test_build_short_description_truncates_long_text() -> None:
    """Short description helper should truncate long descriptions."""
    source = " ".join(["seek"] * 200)

    short = SeekScraper._build_short_description(source)

    assert short is not None
    assert short.endswith("...")
    assert len(short) <= SeekScraper.SHORT_DESCRIPTION_MAX_LENGTH + 3


def test_parse_salary_number_supports_k_notation() -> None:
    """Salary parser should convert k suffix to full integer value."""
    parsed = SeekScraper._parse_salary_number("120", "$120k - $140k + super")

    assert parsed == 120000
