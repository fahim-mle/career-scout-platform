"""Seek Playwright scraper implementation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scrapers.base import BaseScraper
from src.scrapers.common.text import normalize_whitespace
from src.scrapers.seek.card_parsing import SeekCardParsingMixin
from src.scrapers.seek.constants import (
    BASE_URL,
    CARD_SNIPPET_SELECTORS,
    CLASSIFICATIONS_SELECTORS,
    COMPANY_SELECTORS,
    DATE_POSTED_SELECTORS,
    DESCRIPTION_HTML_FALLBACK_SELECTORS,
    DESCRIPTION_HTML_SELECTORS,
    DESCRIPTION_SELECTORS,
    JOB_CARD_SELECTORS,
    JOB_TYPE_HINTS,
    LOCATION_DETAIL_SELECTORS,
    LOCATION_SELECTORS,
    MAX_LIMIT,
    PLATFORM,
    SALARY_SELECTORS,
    SEARCH_URL,
    SHORT_DESCRIPTION_MAX_LENGTH,
    TITLE_LINK_SELECTORS,
    WORK_TYPE_SELECTORS,
)
from src.scrapers.seek.detail_parsing import SeekDetailParsingMixin
from src.scrapers.seek.exceptions import SeekNonRetryableError, SeekTransientError


class SeekScraper(BaseScraper, SeekCardParsingMixin, SeekDetailParsingMixin):
    """Scraper for public Seek job search pages."""

    BASE_URL = BASE_URL
    SEARCH_URL = SEARCH_URL
    PLATFORM = PLATFORM
    MAX_LIMIT = MAX_LIMIT
    SHORT_DESCRIPTION_MAX_LENGTH = SHORT_DESCRIPTION_MAX_LENGTH
    JOB_CARD_SELECTORS = JOB_CARD_SELECTORS
    TITLE_LINK_SELECTORS = TITLE_LINK_SELECTORS
    COMPANY_SELECTORS = COMPANY_SELECTORS
    LOCATION_SELECTORS = LOCATION_SELECTORS
    CARD_SNIPPET_SELECTORS = CARD_SNIPPET_SELECTORS
    DESCRIPTION_SELECTORS = DESCRIPTION_SELECTORS
    DESCRIPTION_HTML_SELECTORS = DESCRIPTION_HTML_SELECTORS
    DESCRIPTION_HTML_FALLBACK_SELECTORS = DESCRIPTION_HTML_FALLBACK_SELECTORS
    CLASSIFICATIONS_SELECTORS = CLASSIFICATIONS_SELECTORS
    WORK_TYPE_SELECTORS = WORK_TYPE_SELECTORS
    LOCATION_DETAIL_SELECTORS = LOCATION_DETAIL_SELECTORS
    DATE_POSTED_SELECTORS = DATE_POSTED_SELECTORS
    SALARY_SELECTORS = SALARY_SELECTORS
    JOB_TYPE_HINTS = JOB_TYPE_HINTS

    async def login(self) -> None:
        """No-op login; Seek listings are publicly available."""
        logger.bind(scraper=self.__class__.__name__).info("Seek does not require login")

    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Scrape job cards and detail payloads from Seek search results.

        Args:
            query: Job search query string.
            location: Search location string.
            limit: Maximum number of jobs to return.

        Returns:
            List of normalized job payload dictionaries.

        Raises:
            RuntimeError: If scraper page is not initialized.
            SeekTransientError: If the search page cannot be loaded reliably.
            SeekNonRetryableError: Propagated deterministic non-retryable errors.
        """
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
                    scraper=self.__class__.__name__,
                    error=str(exc),
                    url=url,
                ).warning("Failed to enrich Seek job with detail page")

        logger.bind(scraper=self.__class__.__name__, scraped_count=len(jobs)).info(
            "Completed Seek jobs scrape"
        )
        return jobs

    async def scrape_job_details(self, job_url: str) -> dict[str, Any]:
        """Extract details from a Seek job detail page.

        Args:
            job_url: Absolute Seek job detail URL.

        Returns:
            Dictionary with enrichable description, metadata, and salary fields.

        Raises:
            RuntimeError: If scraper page is not initialized.
            SeekTransientError: If detail page navigation fails.
        """
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

    @classmethod
    def _build_search_url(cls, query: str, location: str) -> str:
        """Build encoded Seek search URL.

        Args:
            query: Job search keyword query.
            location: Job search location string.

        Returns:
            Fully encoded Seek search URL.
        """
        params = {
            "keywords": query,
            "where": location,
            "sortmode": "ListedDate",
        }
        return f"{cls.SEARCH_URL}?{urlencode(params)}"

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace.

        Args:
            value: Input text.

        Returns:
            Normalized value or ``None`` when empty after normalization.
        """
        return normalize_whitespace(value)
