"""Unit tests for Indeed scraper helper behavior."""

from __future__ import annotations

from src.scrapers.indeed import IndeedScraper


def test_extract_external_id_prefers_data_jk() -> None:
    """External id should use data-jk when present."""
    result = IndeedScraper._extract_external_id(
        job_url="https://au.indeed.com/viewjob?jk=url-fallback",
        card_data_jk="card-jk-123",
        link_data_jk="link-jk-999",
    )

    assert result == "card-jk-123"


def test_extract_external_id_falls_back_to_url_jk() -> None:
    """External id should fallback to jk query param from URL."""
    result = IndeedScraper._extract_external_id(
        job_url="https://au.indeed.com/viewjob?jk=abc123def456&from=serp",
        card_data_jk=None,
        link_data_jk=None,
    )

    assert result == "abc123def456"


def test_build_short_description_truncates_long_text() -> None:
    """Short description helper truncates and appends ellipsis."""
    source = " ".join(["indeed"] * 200)

    short = IndeedScraper._build_short_description(source)

    assert short is not None
    assert short.endswith("...")
    assert len(short) <= IndeedScraper.SHORT_DESCRIPTION_MAX_LENGTH + 3


def test_extract_salary_range_parses_k_notation() -> None:
    """Salary parser should convert k notation to integer ranges."""
    salary = IndeedScraper._extract_salary_range("$120k - $150k per year")

    assert salary is not None
    assert salary["min"] == 120000
    assert salary["max"] == 150000
    assert salary["currency"] == "AUD"


def test_extract_job_type_from_text_detects_contract() -> None:
    """Job type parser should infer contract from metadata text."""
    result = IndeedScraper._extract_job_type_from_text("Salary: $80/hr - Contract role")

    assert result == "Contract"
