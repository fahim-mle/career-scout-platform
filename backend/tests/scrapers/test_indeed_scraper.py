"""Unit tests for Indeed scraper helper behavior."""

from __future__ import annotations

import pytest
from typing import Any, cast

from src.scrapers.indeed import IndeedScraper


class _FakeElement:
    """Minimal fake Playwright element for Indeed scraper unit tests."""

    def __init__(
        self,
        *,
        text: str = "",
        outer_html: str = "",
        raise_on_evaluate: bool = False,
    ) -> None:
        self._text = text
        self._outer_html = outer_html
        self._raise_on_evaluate = raise_on_evaluate

    async def inner_text(self) -> str:
        """Return fake element text payload."""
        return self._text

    async def evaluate(self, expression: str) -> str:
        """Return fake outerHTML for the expected evaluate expression."""
        if expression != "node => node.outerHTML":
            raise ValueError("Unexpected expression")
        if self._raise_on_evaluate:
            raise RuntimeError("outerHTML unavailable")
        return self._outer_html


class _FakePage:
    """Minimal fake Playwright page for selector extraction tests."""

    def __init__(self, elements: dict[str, _FakeElement]) -> None:
        self._elements = elements

    async def goto(self, url: str, wait_until: str) -> None:
        """Simulate page navigation call for scrape_job_details."""
        del url, wait_until

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return mapped fake element for selector or ``None``."""
        return self._elements.get(selector)


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


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_raw_description_html() -> None:
    """Detail scraping should include raw description HTML in scraped_jobs."""
    html_block = '<div id="jobDescriptionText"><p>Build robust APIs</p></div>'
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(
                    text="Build robust APIs", outer_html=html_block
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=abc")

    assert details["description_full"] == "Build robust APIs"
    assert details["description_short"] == "Build robust APIs"
    assert details["scraped_jobs"] == html_block


@pytest.mark.asyncio
async def test_scrape_job_details_sets_scraped_jobs_none_when_html_missing() -> None:
    """Detail scraping should keep running when raw HTML cannot be extracted."""
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(
                    text="Text extraction still works",
                    raise_on_evaluate=True,
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=abc")

    assert details["description_full"] == "Text extraction still works"
    assert details["description_short"] == "Text extraction still works"
    assert details["scraped_jobs"] is None


@pytest.mark.asyncio
async def test_scrape_job_details_keeps_existing_text_behavior() -> None:
    """Detail scraping should preserve description truncation behavior."""
    long_text = " ".join(["indeed"] * 200)
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(
                    text=long_text,
                    outer_html='<div id="jobDescriptionText"><p>indeed</p></div>',
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=abc")

    assert details["description_full"] == long_text
    assert details["description_short"] is not None
    assert details["description_short"].endswith("...")
    assert (
        len(details["description_short"])
        <= IndeedScraper.SHORT_DESCRIPTION_MAX_LENGTH + 3
    )
