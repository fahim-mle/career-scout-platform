"""Unit tests for Seek scraper helpers."""

from __future__ import annotations

from datetime import datetime
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
        attributes: dict[str, str] | None = None,
        children: dict[str, "_FakeElement"] | None = None,
    ) -> None:
        self._text = text
        self._outer_html = outer_html
        self._raise_on_evaluate = raise_on_evaluate
        self._attributes = attributes or {}
        self._children = children or {}

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

    async def get_attribute(self, name: str) -> str | None:
        """Return fake attribute values for parser tests."""
        return self._attributes.get(name)

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return fake child element for selector fallback tests."""
        return self._children.get(selector)


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
async def test_parse_job_card_extracts_key_fields() -> None:
    """Card parser should return normalized Seek payload fields."""
    scraper = SeekScraper()
    card = _FakeElement(
        children={
            'a[data-automation="jobTitle"]': _FakeElement(
                text="Senior Backend Engineer",
                attributes={"href": "/job/81234567"},
            ),
            'a[data-automation="jobCompany"]': _FakeElement(text="Career Scout"),
            'a[data-automation="jobLocation"]': _FakeElement(text="Brisbane QLD"),
            'span[data-automation="jobShortDescription"]': _FakeElement(
                text="Build and operate backend services"
            ),
        }
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is not None
    assert payload["external_id"] == "81234567"
    assert payload["platform"] == "seek"
    assert payload["url"] == "https://www.seek.com.au/job/81234567"
    assert payload["title"] == "Senior Backend Engineer"
    assert payload["company"] == "Career Scout"
    assert payload["location"] == "Brisbane QLD"
    assert payload["description_short"] == "Build and operate backend services"
    assert isinstance(payload["scraped_at"], datetime)


@pytest.mark.asyncio
async def test_parse_job_card_returns_none_when_required_field_missing() -> None:
    """Card parser should skip cards missing required Seek fields."""
    scraper = SeekScraper()
    card = _FakeElement(
        children={
            'a[data-automation="jobTitle"]': _FakeElement(
                text="Senior Backend Engineer",
                attributes={"href": "/job/81234567"},
            ),
            'a[data-automation="jobCompany"]': _FakeElement(text="Career Scout"),
        }
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is None


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_raw_description_html() -> None:
    """Detail scraping should include raw description HTML in raw_html."""
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

    assert {"description_full", "description_short", "raw_html", "metadata"} <= set(
        details.keys()
    )
    assert details["description_full"] == "Build APIs with FastAPI"
    assert details["description_short"] == "Build APIs with FastAPI"
    assert details["raw_html"] == html_block
    assert details["metadata"] == {"platform": "seek"}


@pytest.mark.asyncio
async def test_scrape_job_details_sets_raw_html_none_when_html_missing() -> None:
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
    assert details["raw_html"] is None
    assert details["metadata"] == {"platform": "seek"}


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_full_seek_metadata() -> None:
    """Detail scraping should extract complete Seek metadata when available."""
    html_block = '<div data-automation="jobAdDetails"><p>Build APIs</p></div>'
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text="Build APIs with FastAPI",
                    outer_html=html_block,
                ),
                '*[data-automation="job-detail-work-type"]': _FakeElement(
                    text="Full time"
                ),
                '*[data-automation="job-detail-classifications"]': _FakeElement(
                    text="Engineering / Software"
                ),
                '*[data-automation="job-detail-location"]': _FakeElement(
                    text="Sydney NSW"
                ),
                '*[data-automation="job-detail-date"]': _FakeElement(
                    text="Posted 2d ago"
                ),
                '*[data-automation="job-detail-salary"]': _FakeElement(
                    text="$120k - $140k + super"
                ),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["job_type"] == "Full time"
    assert details["location"] == "Sydney NSW"
    assert details["salary_range"] == {
        "min": 120000,
        "max": 140000,
        "currency": "AUD",
        "raw": "$120k - $140k + super",
    }
    assert details["metadata"] == {
        "platform": "seek",
        "location": "Sydney NSW",
        "date_posted": "Posted 2d ago",
        "work_type": "Full time",
        "classification": "Engineering",
        "subclassification": "Software",
        "salary_text": "$120k - $140k + super",
    }


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_partial_seek_metadata() -> None:
    """Detail scraping should return partial metadata for sparse pages."""
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text="Simple description"
                ),
                '*[data-automation="job-detail-classifications"]': _FakeElement(
                    text="Community Services"
                ),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["metadata"] == {
        "platform": "seek",
        "classification": "Community Services",
    }


@pytest.mark.asyncio
async def test_scrape_job_details_uses_fallback_selector_for_raw_html() -> None:
    """Detail scraping should fall back to generic selectors for raw HTML extraction."""
    fallback_html = "<main><section><p>Fallback role details</p></section></main>"
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="jobAdDetails"]': _FakeElement(
                    text="Fallback role details"
                ),
                "main": _FakeElement(outer_html=fallback_html),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["description_full"] == "Fallback role details"
    assert details["raw_html"] == fallback_html
    assert details["metadata"] == {"platform": "seek"}


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_metadata_from_alternate_selectors() -> None:
    """Detail scraping should support Seek metadata selector variants."""
    scraper = SeekScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'div[data-automation="job-description"]': _FakeElement(
                    text="Variant detail body",
                    outer_html='<div data-automation="job-description">Variant detail body</div>',
                ),
                '*[data-automation="jobDetailWorkType"]': _FakeElement(text="Contract"),
                '*[data-automation="jobDetailLocation"]': _FakeElement(
                    text="Melbourne VIC"
                ),
                '*[data-automation="jobDetailDate"]': _FakeElement(text="Posted today"),
                '*[data-automation="jobClassifications"]': _FakeElement(
                    text="Engineering - Platform"
                ),
                '*[data-automation="jobSalary"]': _FakeElement(text="$150k - $160k"),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://www.seek.com.au/job/81234567")

    assert details["job_type"] == "Contract"
    assert details["location"] == "Melbourne VIC"
    assert details["metadata"] == {
        "platform": "seek",
        "location": "Melbourne VIC",
        "date_posted": "Posted today",
        "work_type": "Contract",
        "classification": "Engineering",
        "subclassification": "Platform",
        "salary_text": "$150k - $160k",
    }


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
    assert (
        details["raw_html"] == '<div data-automation="jobAdDetails"><p>seek</p></div>'
    )
