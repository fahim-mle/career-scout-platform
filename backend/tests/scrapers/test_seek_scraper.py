"""Unit tests for Seek scraper helpers."""

from __future__ import annotations

import pytest
from typing import Any, cast

from src.scrapers.seek import SeekScraper


class _FakeElement:
    """Minimal fake Playwright element for Seek scraper unit tests."""

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


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_raw_description_html() -> None:
    """Detail scraping should include raw description HTML in scraped_jobs."""
    html_block = '<div data-automation="jobAdDetails"><p>Build APIs</p></div>'
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text="Build APIs with FastAPI", outer_html=html_block
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["description_full"] == "Build APIs with FastAPI"
    assert details["description_short"] == "Build APIs with FastAPI"
    assert details["scraped_jobs"] == html_block


@pytest.mark.asyncio
async def test_scrape_job_details_sets_scraped_jobs_none_when_html_missing() -> None:
    """Detail scraping should keep running when raw HTML cannot be extracted."""
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text="Reliable text payload", raise_on_evaluate=True
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["description_full"] == "Reliable text payload"
    assert details["description_short"] == "Reliable text payload"
    assert details["scraped_jobs"] is None


@pytest.mark.asyncio
async def test_scrape_job_details_keeps_existing_text_behavior() -> None:
    """Detail scraping should preserve existing description truncation behavior."""
    long_text = " ".join(["seek"] * 200)
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text=long_text,
                    outer_html='<div data-automation="jobAdDetails"><p>seek</p></div>',
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["description_full"] == long_text
    assert details["description_short"] is not None
    assert details["description_short"].endswith("...")
    assert (
        len(details["description_short"])
        <= SeekScraper.SHORT_DESCRIPTION_MAX_LENGTH + 3
    )
