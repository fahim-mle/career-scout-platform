"""Unit tests for Indeed scraper helper behavior."""

from __future__ import annotations

from datetime import datetime
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
        """Return fake attribute value for card parsing tests."""
        return self._attributes.get(name)

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return fake nested element for selector fallback chain."""
        return self._children.get(selector)


class _FakeClickableElement(_FakeElement):
    """Fake element that tracks click calls for popup tests."""

    def __init__(self, *, raise_on_click: bool = False) -> None:
        super().__init__()
        self.raise_on_click = raise_on_click
        self.click_calls = 0

    async def click(self, timeout: int) -> None:
        """Record click calls and optionally raise to simulate popup failures."""
        del timeout
        self.click_calls += 1
        if self.raise_on_click:
            raise RuntimeError("popup close failed")


class _FakePage:
    """Minimal fake Playwright page for selector extraction tests."""

    def __init__(
        self,
        elements: dict[str, _FakeElement],
        elements_all: dict[str, list[_FakeElement]] | None = None,
    ) -> None:
        self._elements = elements
        self._elements_all = elements_all or {}

    async def goto(self, url: str, wait_until: str) -> None:
        """Simulate page navigation call for scrape_job_details."""
        del url, wait_until

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return mapped fake element for selector or ``None``."""
        return self._elements.get(selector)

    async def query_selector_all(self, selector: str) -> list[_FakeElement]:
        """Return mapped fake element list for selector or empty list."""
        return self._elements_all.get(selector, [])


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
async def test_parse_job_card_extracts_key_fields() -> None:
    """Card parser should return normalized Indeed key fields."""
    scraper = IndeedScraper()
    card = _FakeElement(
        attributes={"data-jk": "abc123"},
        children={
            "h2.jobTitle a": _FakeElement(
                text="Backend Engineer",
                attributes={"href": "/viewjob?jk=abc123", "data-jk": "abc123"},
            ),
            '[data-testid="company-name"]': _FakeElement(text="Career Scout"),
            '[data-testid="job-location"]': _FakeElement(text="Melbourne VIC"),
            '[data-testid="jobsnippet_footer"]': _FakeElement(
                text="Work with Python and FastAPI"
            ),
        },
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is not None
    assert payload["external_id"] == "abc123"
    assert payload["platform"] == "indeed"
    assert payload["url"] == "https://au.indeed.com/viewjob?jk=abc123"
    assert payload["title"] == "Backend Engineer"
    assert payload["company"] == "Career Scout"
    assert payload["location"] == "Melbourne VIC"
    assert payload["description_short"] == "Work with Python and FastAPI"
    assert isinstance(payload["scraped_at"], datetime)


@pytest.mark.asyncio
async def test_parse_job_card_returns_none_when_required_field_missing() -> None:
    """Card parser should skip cards missing required Indeed fields."""
    scraper = IndeedScraper()
    card = _FakeElement(
        attributes={"data-jk": "abc123"},
        children={
            "h2.jobTitle a": _FakeElement(
                text="Backend Engineer",
                attributes={"href": "/viewjob?jk=abc123", "data-jk": "abc123"},
            ),
            '[data-testid="company-name"]': _FakeElement(text="Career Scout"),
        },
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is None


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_full_metadata_payload() -> None:
    """Detail scraping should include all requested metadata keys when present."""
    html_block = '<div id="jobDescriptionText"><p>Build robust APIs</p></div>'
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(
                    text="Build robust APIs", outer_html=html_block
                ),
                "#salaryInfoAndJobType": _FakeElement(
                    text="$120k - $150k per year · Full-time"
                ),
                '[data-testid="job-location"]': _FakeElement(text="Sydney NSW"),
                '[data-testid="jobsearch-JobMetadataFooter"]': _FakeElement(
                    text="Posted 2 days ago"
                ),
                '[data-testid="company-rating"]': _FakeElement(text="4.2/5"),
            },
            elements_all={
                '[data-testid="benefitItem"]': [
                    _FakeElement(text="Health insurance"),
                    _FakeElement(text="Work from home"),
                    _FakeElement(text="Health insurance"),
                ]
            },
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=abc")

    assert {"description_full", "description_short", "raw_html", "metadata"} <= set(
        details.keys()
    )
    assert details["description_full"] == "Build robust APIs"
    assert details["description_short"] == "Build robust APIs"
    assert details["raw_html"] == html_block
    assert details["metadata"] == {
        "platform": "indeed",
        "location": "Sydney NSW",
        "date_posted": "Posted 2 days ago",
        "work_type": "Full-Time",
        "salary_text": "$120k - $150k per year · Full-time",
        "company_rating": "4.2/5",
        "benefits": ["Health insurance", "Work from home"],
    }


@pytest.mark.asyncio
async def test_scrape_job_details_omits_raw_html_when_html_missing() -> None:
    """Detail scraping should omit raw HTML key when extraction misses."""
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
    assert "raw_html" not in details
    assert details["metadata"] == {"platform": "indeed"}


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_raw_html_from_fallback_selector() -> None:
    """Detail scraping should use fallback selectors when primary HTML selectors miss."""
    fallback_html = "<main><section><p>Fallback indeed details</p></section></main>"
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "main": _FakeElement(
                    text="Fallback indeed details",
                    outer_html=fallback_html,
                )
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details(
        "https://au.indeed.com/viewjob?jk=fallback"
    )

    assert details["description_full"] == "Fallback indeed details"
    assert details["raw_html"] == fallback_html
    assert details["metadata"] == {"platform": "indeed"}


@pytest.mark.asyncio
async def test_scrape_job_details_extracts_sparse_metadata_payload() -> None:
    """Detail scraping should include only metadata keys available in page markup."""
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(text="Minimal metadata page"),
                '[data-testid="jobsearch-JobMetadataFooter"]': _FakeElement(
                    text="Posted today"
                ),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=abc")

    assert details["metadata"] == {
        "platform": "indeed",
        "date_posted": "Posted today",
    }


@pytest.mark.asyncio
async def test_scrape_job_details_handles_popup_close_failure_and_partial_dom() -> None:
    """Detail scraping should continue metadata extraction even if popup close fails."""
    close_button = _FakeClickableElement(raise_on_click=True)
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                'button[aria-label="Close"]': close_button,
                "#jobDescriptionText": _FakeElement(text="Role details"),
                '[data-testid="job-location"]': _FakeElement(text="Melbourne VIC"),
            }
        ),
    )

    async def noop_rate_limit(seconds: float | None = None) -> None:
        del seconds

    scraper.rate_limit = noop_rate_limit  # type: ignore[method-assign]

    details = await scraper.scrape_job_details("https://au.indeed.com/viewjob?jk=popup")

    assert close_button.click_calls == 1
    assert details["description_full"] == "Role details"
    assert details["metadata"] == {
        "platform": "indeed",
        "location": "Melbourne VIC",
    }


@pytest.mark.asyncio
async def test_scrape_job_details_keeps_core_fields_behavior() -> None:
    """Detail scraping should preserve core field extraction behavior."""
    long_text = " ".join(["indeed"] * 200)
    scraper = IndeedScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                "#jobDescriptionText": _FakeElement(
                    text=long_text,
                    outer_html='<div id="jobDescriptionText"><p>indeed</p></div>',
                ),
                "#salaryInfoAndJobType": _FakeElement(
                    text="$100k - $130k per year · Contract"
                ),
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
    assert details["salary_range"] == {
        "min": 100000,
        "max": 130000,
        "currency": "AUD",
        "raw": "$100k - $130k per year · Contract",
    }
    assert details["job_type"] == "Contract"
