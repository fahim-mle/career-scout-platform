"""Seek detail-page parsing helpers."""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scrapers.common.selectors import (
    extract_html_from_page_selectors,
    extract_text_from_page_selectors,
)
from src.scrapers.common.text import build_short_description
from src.scrapers.seek.metadata import (
    build_seek_metadata,
    extract_classification_parts,
)


class SeekDetailParsingMixin:
    """Detail-page parsing behavior for Seek scraper."""

    async def _extract_text_from_page_selectors(
        self,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract normalized text from first matching page selector.

        Args:
            selectors: Ordered CSS selector fallbacks.

        Returns:
            Normalized text from first successful selector.

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
        """Extract raw outer HTML from first matching selector.

        Args:
            selectors: Ordered CSS selector fallbacks.
            extraction_label: Structured log label for extraction context.

        Returns:
            Raw outer HTML from first successful selector.

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
            success_message="Extracted Seek raw description HTML",
            timeout_message="Seek raw HTML extraction timed out",
            failure_message="Seek raw HTML extraction failed for selector",
            timeout_errors=(PlaywrightTimeoutError,),
        )

    async def _extract_job_type(self) -> str | None:
        """Extract job type from work-type/classification fields.

        Returns:
            Best available job type text, otherwise ``None``.
        """
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

        lowered = classifications.lower()
        for hint in self.JOB_TYPE_HINTS:
            if hint in lowered:
                return hint.title()
        return None

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
        return build_seek_metadata(
            platform=self.PLATFORM,
            location=location,
            date_posted=date_posted,
            work_type=work_type,
            classifications_text=classifications,
            salary_text=salary_text,
        )

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

    @staticmethod
    def _parse_salary_number(value: str, raw_text: str) -> int | None:
        """Parse salary token into integer, honoring ``k`` notation.

        Args:
            value: Captured numeric value token from salary text.
            raw_text: Original salary text for suffix inspection.

        Returns:
            Integer salary value when parseable, otherwise ``None``.
        """
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
        return extract_classification_parts(value)

    @classmethod
    def _build_short_description(cls, description_full: str | None) -> str | None:
        """Build short description from full text.

        Args:
            description_full: Full description text.

        Returns:
            Truncated summary text when full description exists.
        """
        if not description_full:
            return None

        return build_short_description(
            description_full=description_full,
            max_length=cls.SHORT_DESCRIPTION_MAX_LENGTH,
        )
