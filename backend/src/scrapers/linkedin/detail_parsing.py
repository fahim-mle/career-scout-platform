"""LinkedIn detail-page parsing helpers."""

from __future__ import annotations

from typing import Any

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.scrapers.common.selectors import (
    extract_html_from_page_selectors,
    extract_text_from_page_selectors,
)
from src.scrapers.common.text import build_short_description
from src.scrapers.linkedin.metadata import (
    build_default_metadata,
    looks_like_relative_date,
    normalize_metadata_text,
    parse_top_card_metadata_text,
)


class LinkedInDetailParsingMixin:
    """Detail-page extraction behavior for LinkedIn scraper."""

    async def _extract_description_html_with_fallback(self) -> str | None:
        """Extract raw description HTML from preferred and fallback selectors.

        Returns:
            Raw HTML string from the first matching description container,
            otherwise ``None``.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for attempt in range(1, self.MAX_DETAIL_EXTRACTION_ATTEMPTS + 1):
            if attempt > 1:
                logger.bind(
                    scraper=self.__class__.__name__,
                    attempt=attempt,
                ).info("Retrying LinkedIn raw description HTML extraction")
                await self._rate_limit_with_jitter(base_seconds=1.0)

            html = await self._extract_html_from_page_selectors(
                selectors=self.DESCRIPTION_HTML_SELECTORS,
                extraction_label="description_html",
            )
            if html:
                return html

            await self._expand_description_if_available()

        logger.bind(scraper=self.__class__.__name__).info(
            "Falling back to broad selectors for raw LinkedIn description HTML"
        )
        fallback_html = await self._extract_html_from_page_selectors(
            selectors=self.DESCRIPTION_FALLBACK_SELECTORS,
            extraction_label="description_html_fallback",
        )
        return self._cap_fallback_description_html(fallback_html)

    async def _extract_top_card_metadata(self) -> dict[str, Any]:
        """Extract LinkedIn top-card metadata into generic schema payload.

        Returns:
            Metadata payload with fixed LinkedIn metadata keys.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        metadata = self._build_default_metadata()
        for selector in self.TOP_CARD_METADATA_SELECTORS:
            element = await self.page.query_selector(selector)
            if element is None:
                continue

            try:
                raw_text = await element.inner_text()
            except PlaywrightTimeoutError:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                ).debug("LinkedIn top-card metadata selector timed out")
                continue

            parsed = self._parse_top_card_metadata_text(raw_text)
            metadata.update(parsed)
            logger.bind(
                scraper=self.__class__.__name__,
                selector=selector,
                has_location=bool(metadata.get("location")),
                has_date_posted=bool(metadata.get("date_posted")),
                has_applicants=bool(metadata.get("number_of_applicants")),
                promoted=bool(metadata.get("promoted_by_hirer")),
                actively_reviewing=bool(metadata.get("actively_reviewing_applicants")),
            ).info("Extracted LinkedIn top-card metadata")
            return metadata

        logger.bind(scraper=self.__class__.__name__).info(
            "LinkedIn top-card metadata block not found; using defaults"
        )
        return metadata

    async def _extract_description_with_fallback(self) -> str | None:
        """Extract job description using staged fallback strategy.

        Returns:
            Best-effort normalized full description text.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for attempt in range(1, self.MAX_DETAIL_EXTRACTION_ATTEMPTS + 1):
            if attempt > 1:
                await self._rate_limit_with_jitter(base_seconds=1.0)

            await self._expand_description_if_available()
            candidate = await self._extract_text_from_page_selectors(
                selectors=self.DESCRIPTION_SELECTORS
            )
            if candidate:
                return candidate

        return await self._extract_text_from_page_selectors(
            selectors=self.DESCRIPTION_FALLBACK_SELECTORS
        )

    async def _expand_description_if_available(self) -> None:
        """Click description expansion controls when present."""
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for selector in self.DESCRIPTION_SHOW_MORE_SELECTORS:
            button = await self.page.query_selector(selector)
            if button is None:
                continue

            try:
                await button.click(timeout=2_500)
                return
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    error=str(exc),
                ).debug("Ignoring LinkedIn description expand failure")
                continue

    async def _extract_text_from_page_selectors(
        self,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract normalized text from first matching page selector.

        Args:
            selectors: Ordered CSS selector fallbacks.

        Returns:
            Normalized text when found, otherwise ``None``.

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
            success_message="Extracted LinkedIn raw HTML block",
            timeout_message="LinkedIn raw HTML extraction timed out",
            failure_message="LinkedIn raw HTML extraction failed for selector",
            timeout_errors=(PlaywrightTimeoutError,),
        )

    async def _extract_job_type(self) -> str | None:
        """Extract job type value from detail page insights.

        Returns:
            Normalized job type text when found, otherwise ``None``.
        """
        insight_text = await self._extract_text_from_page_selectors(
            selectors=self.DETAIL_JOB_TYPE_SELECTORS
        )
        if not insight_text:
            return None

        lower_insight = insight_text.lower()
        for hint in self.JOB_TYPE_HINTS:
            if hint in lower_insight:
                return hint.title()

        return None

    @classmethod
    def _build_short_description(cls, description_full: str | None) -> str | None:
        """Create a short summary from full description text.

        Args:
            description_full: Full normalized description text.

        Returns:
            Truncated description summary or ``None`` when full text is missing.
        """
        if not description_full:
            return None

        summary_text = cls._normalize_text(description_full)
        if not summary_text:
            return None

        return build_short_description(
            description_full=summary_text,
            max_length=cls.SHORT_DESCRIPTION_MAX_LENGTH,
            normalizer=cls._normalize_text,
        )

    @classmethod
    def _build_default_metadata(cls) -> dict[str, Any]:
        """Build default LinkedIn metadata payload for generic schema storage.

        Returns:
            Metadata object containing stable LinkedIn metadata keys.
        """
        return build_default_metadata()

    @classmethod
    def _parse_top_card_metadata_text(cls, raw_text: str | None) -> dict[str, Any]:
        """Parse LinkedIn top-card tertiary text into metadata keys.

        Args:
            raw_text: Raw top-card text content from LinkedIn detail page.

        Returns:
            Parsed metadata fields excluding the fixed platform key.
        """
        return parse_top_card_metadata_text(raw_text)

    @classmethod
    def _cap_fallback_description_html(cls, value: str | None) -> str | None:
        """Cap broad-fallback HTML payload size before persistence.

        Args:
            value: Raw fallback HTML payload.

        Returns:
            Original payload when within the safety limit, otherwise a truncated copy.
        """
        if value is None:
            return None
        if len(value) <= cls.MAX_FALLBACK_DESCRIPTION_HTML_LENGTH:
            return value

        logger.bind(
            scraper=cls.__name__,
            original_length=len(value),
            capped_length=cls.MAX_FALLBACK_DESCRIPTION_HTML_LENGTH,
        ).warning("Capped LinkedIn fallback raw description HTML payload")
        return value[: cls.MAX_FALLBACK_DESCRIPTION_HTML_LENGTH]

    @staticmethod
    def _normalize_metadata_text(value: str | None) -> str | None:
        """Normalize metadata text by collapsing all whitespace.

        Args:
            value: Raw metadata text.

        Returns:
            Whitespace-normalized metadata text when present, otherwise ``None``.
        """
        return normalize_metadata_text(value)

    @staticmethod
    def _looks_like_relative_date(value: str) -> bool:
        """Return whether text appears to be LinkedIn relative date wording.

        Args:
            value: Candidate metadata segment.

        Returns:
            ``True`` when segment resembles a relative date value.
        """
        return looks_like_relative_date(value)

    @classmethod
    def _sanitize_description_text(cls, value: str | None) -> str | None:
        """Normalize and trim noisy LinkedIn detail text to useful content."""
        if not value:
            return None

        normalized = cls._normalize_description_text(value)
        if not normalized:
            return None

        about_marker = "About the job"
        if about_marker in normalized:
            normalized = normalized[normalized.find(about_marker) :]

        for marker in cls.DESCRIPTION_END_MARKERS:
            if marker in normalized:
                normalized = normalized[: normalized.find(marker)]

        normalized = cls.DESCRIPTION_TRAILING_MORE_PATTERN.sub("", normalized).strip()

        normalized = cls._normalize_description_text(normalized)
        if not normalized:
            return None

        if len(normalized) <= cls.MAX_DESCRIPTION_FULL_LENGTH:
            return normalized

        cutoff = normalized.rfind(" ", 0, cls.MAX_DESCRIPTION_FULL_LENGTH)
        if cutoff <= 0:
            cutoff = cls.MAX_DESCRIPTION_FULL_LENGTH
        return normalized[:cutoff].rstrip()

    @classmethod
    def _normalize_description_text(cls, value: str) -> str | None:
        """Normalize text while keeping line breaks for section readability."""
        raw_lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        normalized_lines: list[str] = []
        for line in raw_lines:
            compact = cls._normalize_text(line)
            if compact:
                normalized_lines.append(compact)

        if not normalized_lines:
            return None
        return "\n".join(normalized_lines)
