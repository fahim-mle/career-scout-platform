"""Unit tests for LinkedIn scraper text processing helpers."""

from __future__ import annotations

from datetime import datetime
import pytest
from typing import Any, cast

from src.scrapers.linkedin import LinkedInScraper


class _FakeElement:
    """Minimal fake Playwright element for LinkedIn scraper unit tests."""

    def __init__(
        self,
        *,
        text: str = "",
        outer_html: str = "",
        attributes: dict[str, str] | None = None,
        children: dict[str, "_FakeElement"] | None = None,
    ) -> None:
        self._text = text
        self._outer_html = outer_html
        self._attributes = attributes or {}
        self._children = children or {}

    async def inner_text(self) -> str:
        """Return fake element text payload."""
        return self._text

    async def evaluate(self, expression: str) -> str:
        """Return fake outerHTML for the expected evaluate expression."""
        if expression != "node => node.outerHTML":
            raise ValueError("Unexpected expression")
        return self._outer_html

    async def get_attribute(self, name: str) -> str | None:
        """Return fake attribute value for card parsing helpers."""
        return self._attributes.get(name)

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return fake nested element for selector-based card parsing."""
        return self._children.get(selector)


class _FakePage:
    """Minimal fake Playwright page for selector-based extraction tests."""

    def __init__(self, elements: dict[str, _FakeElement]) -> None:
        self._elements = elements

    async def goto(self, url: str, wait_until: str) -> None:
        """Simulate page navigation call for scrape_job_details."""
        del url, wait_until

    async def query_selector(self, selector: str) -> _FakeElement | None:
        """Return mapped fake element for a selector or ``None``."""
        return self._elements.get(selector)


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


def test_normalize_text_collapses_whitespace() -> None:
    """Generic text normalization should collapse repeated whitespace."""
    raw_title = "  Software   Engineer   "

    result = LinkedInScraper._normalize_text(raw_title)

    assert result == "Software Engineer"


def test_normalize_text_keeps_non_duplicate_text_unchanged() -> None:
    """Generic text normalization should preserve non-empty content."""
    raw_title = "Senior Software Engineer"

    result = LinkedInScraper._normalize_text(raw_title)

    assert result == "Senior Software Engineer"


def test_normalize_text_does_not_apply_title_specific_deduplication() -> None:
    """Generic text normalization should not collapse repeated title phrases."""
    raw_title = "Software Engineer - Software Engineer"

    result = LinkedInScraper._normalize_text(raw_title)

    assert result == "Software Engineer - Software Engineer"


@pytest.mark.asyncio
async def test_extract_html_from_page_selectors_returns_raw_html_when_present() -> None:
    """Raw HTML extraction should return the first matching selector block."""
    scraper = LinkedInScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            {
                "#job-details": _FakeElement(
                    outer_html=(
                        '<div id="job-details"><p>About the job</p><p>Build APIs.</p></div>'
                    )
                )
            }
        ),
    )

    raw_html = await scraper._extract_html_from_page_selectors(
        selectors=("#job-details", ".jobs-box__html-content"),
        extraction_label="unit_test",
    )

    assert raw_html is not None
    assert raw_html.startswith('<div id="job-details">')
    assert "Build APIs." in raw_html


@pytest.mark.asyncio
async def test_extract_html_from_page_selectors_returns_none_when_missing() -> None:
    """Raw HTML extraction should be resilient when no selector exists."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))

    raw_html = await scraper._extract_html_from_page_selectors(
        selectors=("#job-details", ".jobs-box__html-content"),
        extraction_label="unit_test",
    )

    assert raw_html is None


@pytest.mark.asyncio
async def test_extract_description_html_with_fallback_uses_preferred_selectors() -> (
    None
):
    """Description HTML helper should return preferred selector payload first."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))

    async def fake_extract_html_from_page_selectors(
        selectors: tuple[str, ...], extraction_label: str
    ) -> str | None:
        del selectors, extraction_label
        return '<section class="show-more-less-html"><p>Preferred</p></section>'

    # Intentional private-method monkeypatch: isolates fallback orchestration path.
    scraper._extract_html_from_page_selectors = (  # type: ignore[method-assign]
        fake_extract_html_from_page_selectors
    )

    raw_html = await scraper._extract_description_html_with_fallback()

    assert raw_html is not None
    assert "Preferred" in raw_html


@pytest.mark.asyncio
async def test_extract_description_html_with_fallback_uses_fallback_selectors() -> None:
    """Description HTML helper should fall back when preferred selectors miss."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))
    calls: list[tuple[str, tuple[str, ...]]] = []

    async def fake_extract_html_from_page_selectors(
        selectors: tuple[str, ...], extraction_label: str
    ) -> str | None:
        calls.append((extraction_label, selectors))
        if extraction_label == "description_html_fallback":
            return "<main><p>Fallback block</p></main>"
        return None

    async def noop() -> None:
        return None

    async def noop_with_arg(base_seconds: float | None = None) -> None:
        del base_seconds
        return None

    # Intentional private-method monkeypatch: targets branch ordering deterministically.
    scraper._extract_html_from_page_selectors = (  # type: ignore[method-assign]
        fake_extract_html_from_page_selectors
    )
    scraper._expand_description_if_available = noop  # type: ignore[method-assign]
    scraper._rate_limit_with_jitter = noop_with_arg  # type: ignore[method-assign]

    raw_html = await scraper._extract_description_html_with_fallback()

    assert raw_html == "<main><p>Fallback block</p></main>"
    assert calls[0][0] == "description_html"
    assert calls[-1][0] == "description_html_fallback"


@pytest.mark.asyncio
async def test_extract_description_html_with_fallback_caps_large_fallback_payload() -> (
    None
):
    """Fallback extraction should cap oversized raw HTML payloads."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))
    oversized_html = "<main>" + (
        "x" * (scraper.MAX_FALLBACK_DESCRIPTION_HTML_LENGTH + 25)
    )

    async def fake_extract_html_from_page_selectors(
        selectors: tuple[str, ...], extraction_label: str
    ) -> str | None:
        del selectors
        if extraction_label == "description_html_fallback":
            return oversized_html
        return None

    async def noop() -> None:
        return None

    async def noop_with_arg(base_seconds: float | None = None) -> None:
        del base_seconds
        return None

    # Intentional private-method monkeypatch: validates fallback truncation guard.
    scraper._extract_html_from_page_selectors = (  # type: ignore[method-assign]
        fake_extract_html_from_page_selectors
    )
    scraper._expand_description_if_available = noop  # type: ignore[method-assign]
    scraper._rate_limit_with_jitter = noop_with_arg  # type: ignore[method-assign]

    raw_html = await scraper._extract_description_html_with_fallback()

    assert raw_html is not None
    assert len(raw_html) == scraper.MAX_FALLBACK_DESCRIPTION_HTML_LENGTH


@pytest.mark.asyncio
async def test_extract_top_card_metadata_extracts_expected_fields() -> None:
    """Top-card extraction should populate metadata from primary selector text."""
    scraper = LinkedInScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                scraper.TOP_CARD_METADATA_SELECTORS[0]: _FakeElement(
                    text=(
                        "Sydney, New South Wales, Australia · 1 day ago · "
                        "Over 100 applicants · Promoted by hirer"
                    )
                )
            }
        ),
    )

    metadata = await scraper._extract_top_card_metadata()

    assert metadata["platform"] == "linkedin"
    assert metadata["location"] == "Sydney, New South Wales, Australia"
    assert metadata["date_posted"] == "1 day ago"
    assert metadata["number_of_applicants"] == "Over 100 applicants"
    assert metadata["promoted_by_hirer"] is True


@pytest.mark.asyncio
async def test_extract_top_card_metadata_returns_defaults_when_missing() -> None:
    """Top-card extraction should return default metadata when block is absent."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))

    metadata = await scraper._extract_top_card_metadata()

    assert metadata == {
        "platform": "linkedin",
        "location": None,
        "date_posted": None,
        "number_of_applicants": None,
        "promoted_by_hirer": False,
        "actively_reviewing_applicants": False,
    }


@pytest.mark.asyncio
async def test_extract_top_card_metadata_uses_next_selector_when_first_is_empty() -> (
    None
):
    """Top-card extraction should continue selector chain after empty metadata."""
    scraper = LinkedInScraper()
    scraper.page = cast(
        Any,
        _FakePage(
            elements={
                scraper.TOP_CARD_METADATA_SELECTORS[0]: _FakeElement(text="   "),
                scraper.TOP_CARD_METADATA_SELECTORS[1]: _FakeElement(
                    text=(
                        "Melbourne, Victoria, Australia · 2 days ago · "
                        "Over 25 applicants"
                    )
                ),
            }
        ),
    )

    metadata = await scraper._extract_top_card_metadata()

    assert metadata["platform"] == "linkedin"
    assert metadata["location"] == "Melbourne, Victoria, Australia"
    assert metadata["date_posted"] == "2 days ago"
    assert metadata["number_of_applicants"] == "Over 25 applicants"


def test_parse_top_card_metadata_text_maps_all_expected_fields() -> None:
    """Top-card parser should extract location/date/applicants and status flags."""
    metadata = LinkedInScraper._parse_top_card_metadata_text(
        (
            "Sydney, New South Wales, Australia · 1 day ago · "
            "Over 100 applicants · Promoted by hirer · Actively reviewing applicants"
        )
    )

    assert metadata["location"] == "Sydney, New South Wales, Australia"
    assert metadata["date_posted"] == "1 day ago"
    assert metadata["number_of_applicants"] == "Over 100 applicants"
    assert metadata["promoted_by_hirer"] is True
    assert metadata["actively_reviewing_applicants"] is True


def test_parse_top_card_metadata_text_handles_missing_fields() -> None:
    """Top-card parser should keep defaults when optional fields are absent."""
    metadata = LinkedInScraper._parse_top_card_metadata_text(
        "Melbourne, Victoria, Australia · Promoted by hirer"
    )

    assert metadata["location"] == "Melbourne, Victoria, Australia"
    assert metadata["date_posted"] is None
    assert metadata["number_of_applicants"] is None
    assert metadata["promoted_by_hirer"] is True
    assert metadata["actively_reviewing_applicants"] is False


@pytest.mark.asyncio
async def test_parse_job_card_extracts_key_fields() -> None:
    """Card parsing should populate required LinkedIn card fields."""
    scraper = LinkedInScraper()
    card = _FakeElement(
        attributes={"data-entity-urn": "urn:li:jobPosting:998877"},
        children={
            "a.base-card__full-link": _FakeElement(
                text="Senior Backend Engineer",
                attributes={"href": "/jobs/view/998877"},
            ),
            "h3.base-search-card__title": _FakeElement(text="Senior Backend Engineer"),
            "h4.base-search-card__subtitle": _FakeElement(text="Career Scout"),
            "span.job-search-card__location": _FakeElement(text="Remote"),
            ".job-search-card__snippet": _FakeElement(
                text="Build APIs with Python and FastAPI"
            ),
        },
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is not None
    assert payload["external_id"] == "998877"
    assert payload["platform"] == "linkedin"
    assert payload["url"] == "https://www.linkedin.com/jobs/view/998877"
    assert payload["title"] == "Senior Backend Engineer"
    assert payload["company"] == "Career Scout"
    assert payload["location"] == "Remote"
    assert payload["description_short"] == "Build APIs with Python and FastAPI"
    assert payload["description_full"] == "Build APIs with Python and FastAPI"
    assert isinstance(payload["scraped_at"], datetime)


@pytest.mark.asyncio
async def test_parse_job_card_returns_none_when_required_field_missing() -> None:
    """Card parsing should skip payloads missing required fields."""
    scraper = LinkedInScraper()
    card = _FakeElement(
        attributes={"data-entity-urn": "urn:li:jobPosting:112233"},
        children={
            "a.base-card__full-link": _FakeElement(
                text="Backend Engineer",
                attributes={"href": "/jobs/view/112233"},
            ),
            "h3.base-search-card__title": _FakeElement(text="Backend Engineer"),
            "h4.base-search-card__subtitle": _FakeElement(text="Career Scout"),
        },
    )

    payload = await scraper._parse_job_card(card=cast(Any, card))

    assert payload is None


@pytest.mark.asyncio
async def test_scrape_job_details_includes_baseline_detail_payload_keys() -> None:
    """Detail extraction should expose stable core payload fields."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))

    async def noop_stage(stage: str) -> None:
        del stage

    async def noop_rate(base_seconds: float | None = None) -> None:
        del base_seconds

    async def fake_extract_text_from_page_selectors(
        selectors: tuple[str, ...],
    ) -> str | None:
        del selectors
        return "About the job Build resilient APIs"

    async def fake_extract_description_with_fallback() -> str | None:
        return None

    async def fake_extract_description_html_with_fallback() -> str | None:
        return '<div id="job-details"><p>Build resilient APIs</p></div>'

    async def fake_extract_top_card_metadata() -> dict[str, Any]:
        return {
            "platform": "linkedin",
            "location": "Sydney",
            "date_posted": "1 day ago",
            "number_of_applicants": "Over 100 applicants",
            "promoted_by_hirer": True,
            "actively_reviewing_applicants": False,
        }

    async def fake_extract_job_type() -> str | None:
        return "Full-Time"

    scraper._assert_no_challenge = noop_stage  # type: ignore[method-assign]
    scraper._rate_limit_with_jitter = noop_rate  # type: ignore[method-assign]
    scraper._extract_text_from_page_selectors = (  # type: ignore[method-assign]
        fake_extract_text_from_page_selectors
    )
    scraper._extract_description_with_fallback = (  # type: ignore[method-assign]
        fake_extract_description_with_fallback
    )
    scraper._extract_description_html_with_fallback = (  # type: ignore[method-assign]
        fake_extract_description_html_with_fallback
    )
    scraper._extract_top_card_metadata = fake_extract_top_card_metadata  # type: ignore[method-assign]
    scraper._extract_job_type = fake_extract_job_type  # type: ignore[method-assign]

    details = await scraper.scrape_job_details(
        "https://www.linkedin.com/jobs/view/998877"
    )

    assert details["description_full"] == "About the job Build resilient APIs"
    assert details["description_short"] == "About the job Build resilient APIs"
    assert (
        details["raw_html"] == '<div id="job-details"><p>Build resilient APIs</p></div>'
    )
    assert details["metadata"]["platform"] == "linkedin"


@pytest.mark.asyncio
async def test_scrape_job_details_sparse_dom_keeps_metadata_defaults() -> None:
    """Detail extraction should preserve default metadata on sparse pages."""
    scraper = LinkedInScraper()
    scraper.page = cast(Any, _FakePage(elements={}))

    async def noop_stage(stage: str) -> None:
        del stage

    async def noop_rate(base_seconds: float | None = None) -> None:
        del base_seconds

    async def fake_extract_text_from_page_selectors(
        selectors: tuple[str, ...],
    ) -> str | None:
        del selectors
        return None

    async def fake_extract_description_with_fallback() -> str | None:
        return None

    async def fake_extract_description_html_with_fallback() -> str | None:
        return None

    async def fake_extract_top_card_metadata() -> dict[str, Any]:
        return scraper._build_default_metadata()

    async def fake_extract_job_type() -> str | None:
        return None

    scraper._assert_no_challenge = noop_stage  # type: ignore[method-assign]
    scraper._rate_limit_with_jitter = noop_rate  # type: ignore[method-assign]
    scraper._extract_text_from_page_selectors = (  # type: ignore[method-assign]
        fake_extract_text_from_page_selectors
    )
    scraper._extract_description_with_fallback = (  # type: ignore[method-assign]
        fake_extract_description_with_fallback
    )
    scraper._extract_description_html_with_fallback = (  # type: ignore[method-assign]
        fake_extract_description_html_with_fallback
    )
    scraper._extract_top_card_metadata = fake_extract_top_card_metadata  # type: ignore[method-assign]
    scraper._extract_job_type = fake_extract_job_type  # type: ignore[method-assign]

    details = await scraper.scrape_job_details(
        "https://www.linkedin.com/jobs/view/445566"
    )

    assert details == {
        "metadata": {
            "platform": "linkedin",
            "location": None,
            "date_posted": None,
            "number_of_applicants": None,
            "promoted_by_hirer": False,
            "actively_reviewing_applicants": False,
        }
    }
