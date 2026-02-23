"""Indeed Playwright scraper implementation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scrapers.base import BaseScraper
from src.scrapers.common.text import normalize_whitespace
from src.scrapers.indeed.card_parsing import IndeedCardParsingMixin
from src.scrapers.indeed.constants import (
    BASE_URL,
    BENEFITS_ITEM_SELECTORS,
    CARD_SNIPPET_SELECTORS,
    COMPANY_RATING_SELECTORS,
    COMPANY_SELECTORS,
    DATE_POSTED_SELECTORS,
    DESCRIPTION_HTML_FALLBACK_SELECTORS,
    DESCRIPTION_HTML_SELECTORS,
    DESCRIPTION_SELECTORS,
    HEADER_JOB_TYPE_SELECTORS,
    JOB_CARD_SELECTORS,
    JOB_TYPE_HINTS,
    LOCATION_SELECTORS,
    MAX_LIMIT,
    METADATA_LOCATION_SELECTORS,
    PLATFORM,
    POPUP_CLOSE_SELECTORS,
    SALARY_AND_TYPE_SELECTORS,
    SALARY_TEXT_SELECTORS,
    SEARCH_URL,
    SHORT_DESCRIPTION_MAX_LENGTH,
    TITLE_LINK_SELECTORS,
)
from src.scrapers.indeed.detail_parsing import IndeedDetailParsingMixin
from src.scrapers.indeed.exceptions import IndeedNonRetryableError, IndeedTransientError
from src.scrapers.indeed.metadata_parsing import IndeedMetadataParsingMixin


class IndeedScraper(
    BaseScraper,
    IndeedCardParsingMixin,
    IndeedDetailParsingMixin,
    IndeedMetadataParsingMixin,
):
    """Scraper for public Indeed Australia job search pages."""

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
    SALARY_AND_TYPE_SELECTORS = SALARY_AND_TYPE_SELECTORS
    METADATA_LOCATION_SELECTORS = METADATA_LOCATION_SELECTORS
    DATE_POSTED_SELECTORS = DATE_POSTED_SELECTORS
    SALARY_TEXT_SELECTORS = SALARY_TEXT_SELECTORS
    COMPANY_RATING_SELECTORS = COMPANY_RATING_SELECTORS
    BENEFITS_ITEM_SELECTORS = BENEFITS_ITEM_SELECTORS
    HEADER_JOB_TYPE_SELECTORS = HEADER_JOB_TYPE_SELECTORS
    POPUP_CLOSE_SELECTORS = POPUP_CLOSE_SELECTORS
    JOB_TYPE_HINTS = JOB_TYPE_HINTS

    async def login(self) -> None:
        """Perform no-op login because Indeed jobs are publicly visible."""
        logger.bind(scraper=self.__class__.__name__).info(
            "Indeed does not require login"
        )

    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Scrape Indeed cards and detail payloads from search results.

        Args:
            query: Search keyword string.
            location: Search location string.
            limit: Maximum number of jobs to collect.

        Returns:
            List of normalized job payload dictionaries.

        Raises:
            RuntimeError: If scraper page is not initialized.
            IndeedTransientError: If a retryable browser/navigation failure occurs.
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
        ).info("Starting Indeed jobs scrape")

        try:
            await self.page.goto(search_url, wait_until="domcontentloaded")
            await self.rate_limit(seconds=1.5)
            await self._close_popups_best_effort()
        except PlaywrightTimeoutError as exc:
            raise IndeedTransientError("Timed out loading Indeed search page") from exc
        except Exception as exc:
            raise IndeedTransientError("Failed loading Indeed search page") from exc

        cards = await self._collect_job_cards()
        if not cards:
            logger.bind(scraper=self.__class__.__name__).warning(
                "No Indeed job cards found"
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
                    "Skipping Indeed card due to parse error"
                )

        for job in jobs:
            url = str(job.get("url", "")).strip()
            if not url:
                continue

            try:
                details = await self.scrape_job_details(job_url=url)
                if details:
                    job.update(details)
            except IndeedNonRetryableError:
                raise
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__, error=str(exc), url=url
                ).warning("Failed to enrich Indeed job with detail page")

        logger.bind(scraper=self.__class__.__name__, scraped_count=len(jobs)).info(
            "Completed Indeed jobs scrape"
        )
        return jobs

    @classmethod
    def _build_search_url(cls, query: str, location: str) -> str:
        """Build encoded Indeed search URL.

        Args:
            query: Search keyword.
            location: Search location.

        Returns:
            Fully encoded Indeed jobs URL.
        """
        params = {"q": query, "l": location, "sort": "date"}
        return f"{cls.SEARCH_URL}?{urlencode(params)}"

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace.

        Args:
            value: Raw text.

        Returns:
            Normalized string or ``None`` when empty.
        """
        return normalize_whitespace(value)
