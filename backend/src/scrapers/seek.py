"""Seek Playwright scraper implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlencode

from loguru import logger
from playwright.async_api import ElementHandle, TimeoutError as PlaywrightTimeoutError

from src.scrapers.base import BaseScraper


class SeekScraper(BaseScraper):
    """Scraper for public Seek job search pages."""

    BASE_URL = "https://www.seek.com.au"
    SEARCH_URL = f"{BASE_URL}/jobs"
    PLATFORM = "seek"
    MAX_LIMIT = 20
    SHORT_DESCRIPTION_MAX_LENGTH = 360
    JOB_CARD_SELECTORS = (
        'article[data-testid="job-card"]',
        "article",
    )
    TITLE_LINK_SELECTORS = (
        'a[data-automation="jobTitle"]',
        'a[data-automation="job-title"]',
        "a[href*='/job/']",
    )
    COMPANY_SELECTORS = (
        'a[data-automation="jobCompany"]',
        'span[data-automation="jobCompany"]',
    )
    LOCATION_SELECTORS = (
        'a[data-automation="jobLocation"]',
        'span[data-automation="jobLocation"]',
    )
    CARD_SNIPPET_SELECTORS = (
        'span[data-automation="jobShortDescription"]',
        'div[data-automation="jobShortDescription"]',
    )
    DESCRIPTION_SELECTORS = (
        'div[data-automation="jobAdDetails"]',
        'div[data-automation="job-description"]',
    )
    DESCRIPTION_HTML_SELECTORS = (
        'article[data-automation="jobAdDetails"]',
        'section[data-automation="jobAdDetails"]',
        'div[data-automation="jobAdDetails"]',
        'div[data-automation="job-description"]',
    )
    DESCRIPTION_HTML_FALLBACK_SELECTORS = (
        "main",
        "article",
        '[data-testid="job-details"]',
    )
    CLASSIFICATIONS_SELECTORS = (
        '*[data-automation="job-detail-classifications"]',
        '*[data-automation="jobClassifications"]',
    )
    WORK_TYPE_SELECTORS = (
        '*[data-automation="job-detail-work-type"]',
        '*[data-automation="jobDetailWorkType"]',
    )
    LOCATION_DETAIL_SELECTORS = (
        '*[data-automation="job-detail-location"]',
        '*[data-automation="jobDetailLocation"]',
    )
    DATE_POSTED_SELECTORS = (
        '*[data-automation="job-detail-date"]',
        '*[data-automation="jobDetailDate"]',
        '*[data-automation="jobDate"]',
    )
    SALARY_SELECTORS = (
        '*[data-automation="job-detail-salary"]',
        '*[data-automation="jobSalary"]',
    )

    async def login(self) -> None:
        """No-op login; Seek listings are publicly available."""
        logger.bind(scraper=self.__class__.__name__).info("Seek does not require login")

    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Scrape job cards and detail payloads from Seek search results."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        safe_limit = max(1, min(limit, self.MAX_LIMIT))
        search_url = self._build_search_url(query=query, location=location)
        logger.bind(
            scraper=self.__class__.__name__,
            query=query,
            location=location,
            limit=safe_limit,
        ).info("Starting Seek jobs scrape")

        try:
            await self.page.goto(search_url, wait_until="domcontentloaded")
            await self.rate_limit(seconds=1.0)
        except PlaywrightTimeoutError as exc:
            raise SeekTransientError("Timed out loading Seek search page") from exc
        except Exception as exc:
            raise SeekTransientError("Failed loading Seek search page") from exc

        cards = await self._collect_job_cards()
        if not cards:
            logger.bind(scraper=self.__class__.__name__).warning(
                "No Seek job cards found"
            )
            return []

        jobs: list[dict[str, Any]] = []
        for card in cards:
            if len(jobs) >= safe_limit:
                break

            try:
                payload = await self._parse_job_card(card=card)
                if payload is None:
                    continue
                jobs.append(payload)
            except Exception as exc:
                logger.bind(scraper=self.__class__.__name__, error=str(exc)).warning(
                    "Skipping Seek card due to parse error"
                )

        for job in jobs:
            url = str(job.get("url", "")).strip()
            if not url:
                continue

            try:
                details = await self.scrape_job_details(job_url=url)
                if details:
                    job.update(details)
            except SeekNonRetryableError:
                raise
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__, error=str(exc), url=url
                ).warning("Failed to enrich Seek job with detail page")

        logger.bind(scraper=self.__class__.__name__, scraped_count=len(jobs)).info(
            "Completed Seek jobs scrape"
        )
        return jobs

    async def scrape_job_details(self, job_url: str) -> dict[str, Any]:
        """Extract details from a Seek job detail page."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        try:
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self.rate_limit(seconds=1.0)
        except PlaywrightTimeoutError as exc:
            raise SeekTransientError("Timed out loading Seek detail page") from exc
        except Exception as exc:
            raise SeekTransientError("Failed loading Seek detail page") from exc

        description_full = await self._extract_text_from_page_selectors(
            selectors=self.DESCRIPTION_SELECTORS
        )
        description_full = self._normalize_text(description_full or "")
        description_short = self._build_short_description(description_full)

        raw_description_html: str | None = None
        try:
            raw_description_html = await self._extract_raw_description_html()
        except Exception as exc:
            logger.bind(
                scraper=self.__class__.__name__,
                url=job_url,
                error=str(exc),
            ).warning("Failed Seek raw description HTML extraction")

        details: dict[str, Any] = {}
        if description_full:
            details["description_full"] = description_full
            details["description_short"] = description_short
        details["scraped_jobs"] = raw_description_html

        job_type = await self._extract_job_type()
        if job_type:
            details["job_type"] = job_type

        salary_text = await self._extract_text_from_page_selectors(
            selectors=self.SALARY_SELECTORS
        )
        salary_range = self._extract_salary_range_from_text(salary_text)
        if salary_range:
            details["salary_range"] = salary_range

        location_detail = await self._extract_text_from_page_selectors(
            selectors=self.LOCATION_DETAIL_SELECTORS
        )
        if location_detail:
            details["location"] = location_detail

        details["metadata"] = await self._extract_seek_metadata(
            location=location_detail,
            work_type=job_type,
            salary_text=salary_text,
        )

        return details

    async def _extract_seek_metadata(
        self,
        location: str | None,
        work_type: str | None,
        salary_text: str | None,
    ) -> dict[str, Any]:
        """Extract Seek metadata into generic payload keys.

        Args:
            location: Optional location text extracted from detail page.
            work_type: Optional work type text inferred from detail selectors.
            salary_text: Optional raw salary text extracted from detail selectors.

        Returns:
            Metadata dictionary containing platform and available Seek fields.
        """
        date_posted = await self._extract_text_from_page_selectors(
            selectors=self.DATE_POSTED_SELECTORS
        )
        classifications = await self._extract_text_from_page_selectors(
            selectors=self.CLASSIFICATIONS_SELECTORS
        )
        classification, subclassification = self._extract_classification_parts(
            classifications
        )

        metadata: dict[str, Any] = {"platform": self.PLATFORM}
        optional_fields = {
            "location": location,
            "date_posted": date_posted,
            "work_type": work_type,
            "classification": classification,
            "subclassification": subclassification,
            "salary_text": salary_text,
        }
        metadata.update(
            {
                key: value
                for key, value in optional_fields.items()
                if value is not None and str(value).strip() != ""
            }
        )
        return metadata

    async def _collect_job_cards(self) -> list[ElementHandle]:
        """Collect job card elements from search results."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for _ in range(4):
            for selector in self.JOB_CARD_SELECTORS:
                cards = await self.page.query_selector_all(selector)
                if cards:
                    return cards
            await self.page.mouse.wheel(0, 1400)
            await self.rate_limit(seconds=0.8)

        return []

    async def _parse_job_card(self, card: ElementHandle) -> dict[str, Any] | None:
        """Parse an individual Seek card into normalized payload."""
        link = await self._query_first(card, self.TITLE_LINK_SELECTORS)
        if link is None:
            return None

        raw_url = await link.get_attribute("href")
        if not raw_url:
            return None

        job_url = self._to_absolute_url(raw_url)
        external_id = self._extract_external_id(job_url)
        if external_id is None:
            return None

        title = self._normalize_text(await link.inner_text() if link else "")
        company = await self._extract_first_text(card, self.COMPANY_SELECTORS)
        location = await self._extract_first_text(card, self.LOCATION_SELECTORS)
        snippet = await self._extract_first_text(card, self.CARD_SNIPPET_SELECTORS)

        if not title or not company or not location:
            return None

        return {
            "external_id": external_id,
            "platform": self.PLATFORM,
            "url": job_url,
            "title": title,
            "company": company,
            "location": location,
            "description_short": snippet,
            "scraped_at": datetime.now(timezone.utc),
        }

    async def _extract_text_from_page_selectors(
        self,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract normalized text from first matching page selector."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element is None:
                continue
            try:
                raw_text = await element.inner_text()
                normalized = self._normalize_text(raw_text)
                if normalized:
                    return normalized
            except PlaywrightTimeoutError:
                continue
        return None

    async def _extract_raw_description_html(self) -> str | None:
        """Extract raw description HTML using durable selectors then fallback path."""
        primary_html = await self._extract_html_from_page_selectors(
            selectors=self.DESCRIPTION_HTML_SELECTORS,
            extraction_label="description_html_primary",
        )
        if primary_html:
            return primary_html

        logger.bind(scraper=self.__class__.__name__).info(
            "Seek description HTML primary selectors missed; trying fallback"
        )
        fallback_html = await self._extract_html_from_page_selectors(
            selectors=self.DESCRIPTION_HTML_FALLBACK_SELECTORS,
            extraction_label="description_html_fallback",
        )
        if fallback_html:
            return fallback_html

        logger.bind(scraper=self.__class__.__name__).info(
            "Seek description HTML not found across selector chain"
        )
        return None

    async def _extract_html_from_page_selectors(
        self,
        selectors: tuple[str, ...],
        extraction_label: str,
    ) -> str | None:
        """Extract raw outer HTML from first matching selector."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for selector in selectors:
            element = await self.page.query_selector(selector)
            if element is None:
                continue

            try:
                raw_html = await element.evaluate("node => node.outerHTML")
                if isinstance(raw_html, str) and raw_html.strip():
                    logger.bind(
                        scraper=self.__class__.__name__,
                        selector=selector,
                        extraction_label=extraction_label,
                    ).info("Extracted Seek raw description HTML")
                    return raw_html.strip()
            except PlaywrightTimeoutError:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    extraction_label=extraction_label,
                ).debug("Seek raw HTML extraction timed out")
                continue
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    extraction_label=extraction_label,
                    error=str(exc),
                ).debug("Seek raw HTML extraction failed for selector")
                continue

        return None

    async def _extract_job_type(self) -> str | None:
        """Extract job type from work-type/classification fields."""
        work_type = await self._extract_text_from_page_selectors(
            self.WORK_TYPE_SELECTORS
        )
        if work_type:
            return work_type

        classifications = await self._extract_text_from_page_selectors(
            self.CLASSIFICATIONS_SELECTORS
        )
        if not classifications:
            return None

        hints = ("full time", "part time", "contract", "casual", "temporary")
        lowered = classifications.lower()
        for hint in hints:
            if hint in lowered:
                return hint.title()
        return None

    def _extract_salary_range_from_text(
        self,
        salary_text: str | None,
    ) -> dict[str, Any] | None:
        """Extract salary range from salary text.

        Args:
            salary_text: Raw salary text from detail page.

        Returns:
            Structured salary payload when min/max values are found.
        """
        if not salary_text:
            return None

        matches = re.findall(r"(?:AUD\s*)?\$\s*([\d,.]+)k?", salary_text, flags=re.I)
        if len(matches) < 2:
            return None

        min_value = self._parse_salary_number(matches[0], salary_text)
        max_value = self._parse_salary_number(matches[1], salary_text)
        if min_value is None or max_value is None:
            return None
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        return {
            "min": min_value,
            "max": max_value,
            "currency": "AUD",
            "raw": salary_text,
        }

    @classmethod
    def _extract_classification_parts(
        cls,
        value: str | None,
    ) -> tuple[str | None, str | None]:
        """Split classification text into classification/subclassification.

        Args:
            value: Raw classification text from detail page.

        Returns:
            Tuple of ``(classification, subclassification)`` values.
        """
        normalized = cls._normalize_text(value or "")
        if not normalized:
            return (None, None)

        for delimiter in (" / ", " - ", " | ", ": "):
            if delimiter in normalized:
                left, right = normalized.split(delimiter, maxsplit=1)
                classification = cls._normalize_text(left)
                subclassification = cls._normalize_text(right)
                return (classification, subclassification)

        return (normalized, None)

    async def _extract_first_text(
        self,
        root: ElementHandle,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract first non-empty normalized text from selector fallback list."""
        for selector in selectors:
            element = await root.query_selector(selector)
            if element is None:
                continue
            value = self._normalize_text(await element.inner_text())
            if value:
                return value
        return None

    async def _query_first(
        self,
        root: ElementHandle,
        selectors: tuple[str, ...],
    ) -> ElementHandle | None:
        """Return first matching child element for fallback selectors."""
        for selector in selectors:
            element = await root.query_selector(selector)
            if element is not None:
                return element
        return None

    @classmethod
    def _build_short_description(cls, description_full: str | None) -> str | None:
        """Build short description from full text."""
        if not description_full:
            return None

        if len(description_full) <= cls.SHORT_DESCRIPTION_MAX_LENGTH:
            return description_full

        cutoff = description_full.rfind(" ", 0, cls.SHORT_DESCRIPTION_MAX_LENGTH)
        if cutoff <= 0:
            cutoff = cls.SHORT_DESCRIPTION_MAX_LENGTH
        return f"{description_full[:cutoff].rstrip()}..."

    @classmethod
    def _build_search_url(cls, query: str, location: str) -> str:
        """Build encoded Seek search URL."""
        params = {
            "keywords": query,
            "where": location,
            "sortmode": "ListedDate",
        }
        return f"{cls.SEARCH_URL}?{urlencode(params)}"

    @classmethod
    def _to_absolute_url(cls, raw_url: str) -> str:
        """Ensure URL is absolute Seek URL."""
        if raw_url.startswith("http"):
            return raw_url
        return f"{cls.BASE_URL}{raw_url}"

    @staticmethod
    def _extract_external_id(job_url: str) -> str | None:
        """Extract numeric external id from Seek job URL."""
        match = re.search(r"/job/(\d+)", job_url)
        if not match:
            return None
        return match.group(1)

    @staticmethod
    def _parse_salary_number(value: str, raw_text: str) -> int | None:
        """Parse salary token into integer, honoring `k` notation."""
        compact = value.replace(",", "").strip()
        if not compact:
            return None

        try:
            number = float(compact)
        except ValueError:
            return None

        salary_tokens = re.findall(
            r"(?:AUD\s*)?\$?\s*([\d,.]+)\s*([kK]?)",
            raw_text,
            flags=re.I,
        )
        has_k_suffix = any(
            token_value.replace(",", "").strip() == compact and bool(token_suffix)
            for token_value, token_suffix in salary_tokens
        )

        if has_k_suffix:
            number *= 1000

        return int(number)

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace."""
        normalized = " ".join(value.split())
        return normalized if normalized else None


class SeekScraperError(RuntimeError):
    """Base Seek scraper exception type."""


class SeekTransientError(SeekScraperError):
    """Raised for retryable Seek scraper failures."""


class SeekNonRetryableError(SeekScraperError):
    """Raised for deterministic Seek scraper failures."""


__all__ = [
    "SeekNonRetryableError",
    "SeekScraper",
    "SeekScraperError",
    "SeekTransientError",
]
