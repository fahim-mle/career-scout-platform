"""Indeed detail-page parsing helpers."""

from __future__ import annotations

from typing import Any

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scrapers.common.selectors import (
    extract_html_from_page_selectors,
    extract_text_from_page_selectors,
)
from src.scrapers.common.text import build_short_description
from src.scrapers.indeed.exceptions import IndeedTransientError


class IndeedDetailParsingMixin:
    """Detail-page extraction behavior for Indeed scraper."""

    async def scrape_job_details(self, job_url: str) -> dict[str, Any]:
        """Extract additional detail fields from an Indeed job page.

        Args:
            job_url: Absolute Indeed job URL.

        Returns:
            Dictionary with optional detail fields.

        Raises:
            RuntimeError: If scraper page is not initialized.
            IndeedTransientError: If detail page load fails.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        try:
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self.rate_limit(seconds=1.2)
            await self._close_popups_best_effort()
        except PlaywrightTimeoutError as exc:
            raise IndeedTransientError("Timed out loading Indeed detail page") from exc
        except Exception as exc:
            raise IndeedTransientError("Failed loading Indeed detail page") from exc

        description_full = await self._extract_text_from_page_selectors(
            selectors=self.DESCRIPTION_SELECTORS
        )
        description_short = self._build_short_description(description_full)

        raw_description_html: str | None = None
        try:
            raw_description_html = await self._extract_raw_description_html()
        except Exception as exc:
            logger.bind(
                scraper=self.__class__.__name__,
                url=job_url,
                error=str(exc),
            ).warning("Failed Indeed raw description HTML extraction")

        details: dict[str, Any] = {}
        if description_full:
            details["description_full"] = description_full
        if description_short:
            details["description_short"] = description_short
        if raw_description_html is not None:
            details["raw_html"] = raw_description_html

        salary_type_text = await self._extract_text_from_page_selectors(
            selectors=self.SALARY_AND_TYPE_SELECTORS
        )
        if salary_type_text:
            salary_range = self._extract_salary_range(salary_type_text)
            if salary_range:
                details["salary_range"] = salary_range

        job_type = await self._extract_job_type(salary_type_text=salary_type_text)
        if job_type:
            details["job_type"] = job_type

        metadata = await self._extract_metadata(
            salary_type_text=salary_type_text,
            job_type=job_type,
        )
        details["metadata"] = metadata

        return details

    async def _extract_raw_description_html(self) -> str | None:
        """Extract raw description HTML using stable selectors then fallback path.

        Returns:
            Raw HTML string from the first matching description container,
            otherwise ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        primary_html = await self._extract_html_from_page_selectors(
            selectors=self.DESCRIPTION_HTML_SELECTORS,
            extraction_label="description_html_primary",
        )
        if primary_html:
            return primary_html

        logger.bind(scraper=self.__class__.__name__).info(
            "Indeed description HTML primary selectors missed; trying fallback"
        )
        fallback_html = await self._extract_html_from_page_selectors(
            selectors=self.DESCRIPTION_HTML_FALLBACK_SELECTORS,
            extraction_label="description_html_fallback",
        )
        if fallback_html:
            return fallback_html

        logger.bind(scraper=self.__class__.__name__).info(
            "Indeed description HTML not found across selector chain"
        )
        return None

    async def _close_popups_best_effort(self) -> None:
        """Attempt to close blocking popups without failing the scrape.

        Returns:
            None.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for selector in self.POPUP_CLOSE_SELECTORS:
            try:
                button = await self.page.query_selector(selector)
                if button is None:
                    continue
                await button.click(timeout=2_000)
                await self.rate_limit(seconds=0.4)
                logger.bind(scraper=self.__class__.__name__, selector=selector).info(
                    "Closed Indeed popup element"
                )
                return
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    error=str(exc),
                ).debug("Ignoring Indeed popup close failure")
                continue

    async def _extract_text_from_page_selectors(
        self,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract normalized text from first matching page selector.

        Args:
            selectors: Ordered CSS selector fallbacks.

        Returns:
            Normalized text when found, else ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        return await extract_text_from_page_selectors(
            page=self.page,
            selectors=selectors,
            normalize_text=self._normalize_text,
            timeout_errors=(PlaywrightTimeoutError,),
        )

    async def _extract_html_from_page_selectors(
        self,
        selectors: tuple[str, ...],
        extraction_label: str,
    ) -> str | None:
        """Extract raw outer HTML from first matching selector.

        Args:
            selectors: Ordered CSS selector fallbacks.
            extraction_label: Structured log label for extraction context.

        Returns:
            Raw outer HTML string when found, otherwise ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        return await extract_html_from_page_selectors(
            page=self.page,
            selectors=selectors,
            extraction_label=extraction_label,
            scraper_name=self.__class__.__name__,
            success_message="Extracted Indeed raw description HTML",
            timeout_message="Indeed raw HTML extraction timed out",
            failure_message="Indeed raw HTML extraction failed for selector",
            timeout_errors=(PlaywrightTimeoutError,),
        )

    @classmethod
    def _build_short_description(cls, description_full: str | None) -> str | None:
        """Build short description from full text.

        Args:
            description_full: Full normalized description text.

        Returns:
            Truncated short description when needed.
        """
        if not description_full:
            return None

        return build_short_description(
            description_full=description_full,
            max_length=cls.SHORT_DESCRIPTION_MAX_LENGTH,
        )
