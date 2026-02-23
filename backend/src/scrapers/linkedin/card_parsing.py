"""LinkedIn result-card parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urljoin

from loguru import logger
from playwright.async_api import ElementHandle

from src.core.title_normalization import (
    normalize_job_title,
    normalize_title_whitespace,
    title_preview_for_log,
)
from src.scrapers.common.cards import (
    extract_first_raw_text,
    extract_first_text,
    query_first,
)


class LinkedInCardParsingMixin:
    """Card-level parsing behavior for LinkedIn scraper."""

    async def _collect_job_cards(self) -> list[ElementHandle]:
        """Collect visible job card elements using resilient selector fallbacks.

        Returns:
            List of matched card elements or an empty list when no cards are available.

        Raises:
            RuntimeError: If scraper page is not initialized.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        for _ in range(4):
            for selector in self.JOB_CARD_SELECTORS:
                cards = await self.page.query_selector_all(selector)
                if cards:
                    return cards

            await self.page.mouse.wheel(0, 1200)
            await self.rate_limit(seconds=0.8)

        return []

    async def _parse_job_card(
        self,
        card: ElementHandle,
    ) -> dict[str, Any] | None:
        """Parse an individual LinkedIn card into normalized job payload.

        Args:
            card: Card element handle from the LinkedIn results list.

        Returns:
            Parsed job payload dictionary when required fields exist, else ``None``.
        """
        link_element = await self._query_first(card, self.JOB_LINK_SELECTORS)
        if link_element is None:
            return None

        raw_url = await link_element.get_attribute("href")
        if not raw_url:
            return None

        absolute_url = self._to_absolute_url(raw_url)
        external_id = await self._extract_external_id(card=card, job_url=absolute_url)
        if external_id is None:
            logger.bind(scraper=self.__class__.__name__).warning(
                "Skipping card without external identifier"
            )
            return None

        raw_title = await self._extract_first_raw_text(card, self.TITLE_SELECTORS)
        title = normalize_job_title(raw_title)
        company = await self._extract_first_text(card, self.COMPANY_SELECTORS)
        location = await self._extract_first_text(card, self.LOCATION_SELECTORS)

        if raw_title and title and raw_title != title:
            logger.bind(
                scraper=self.__class__.__name__,
                normalization="adjacent_duplicate_phrase",
                changed=True,
                title_raw=title_preview_for_log(raw_title),
                title_normalized=title_preview_for_log(title),
            ).info("Normalized LinkedIn title artifact")

        if not title or not company or not location:
            return None

        card_description = await self._extract_card_description(
            card=card,
            title=title,
            company=company,
            location=location,
        )

        return {
            "external_id": external_id,
            "platform": self.PLATFORM,
            "url": absolute_url,
            "title": title,
            "company": company,
            "location": location,
            "description_short": card_description,
            "description_full": card_description,
            "scraped_at": datetime.now(timezone.utc),
        }

    async def _extract_card_description(
        self,
        card: ElementHandle,
        title: str,
        company: str,
        location: str,
    ) -> str | None:
        """Extract best-effort description snippet from job card content."""
        snippet = await self._extract_first_text(card, self.CARD_SNIPPET_SELECTORS)
        if snippet:
            return snippet

        try:
            card_text = await card.inner_text()
        except Exception:
            return None

        normalized = self._normalize_text(card_text)
        if not normalized:
            return None

        condensed = normalized
        for token in (title, company, location):
            condensed = condensed.replace(token, " ")
        condensed = self._normalize_text(condensed)
        if condensed and len(condensed) >= 30:
            return self._build_short_description(condensed)

        synthetic = self._normalize_text(
            f"Role: {title}. Company: {company}. Location: {location}."
        )
        return synthetic

    async def _extract_external_id(
        self,
        card: ElementHandle,
        job_url: str,
    ) -> str | None:
        """Extract LinkedIn external job identifier from card metadata.

        Args:
            card: Card element handle.
            job_url: Absolute job URL.

        Returns:
            External id string when found, otherwise ``None``.
        """
        entity_urn = await card.get_attribute("data-entity-urn")
        if entity_urn:
            urn_match = re.search(r"jobPosting:(\d+)", entity_urn)
            if urn_match:
                return urn_match.group(1)

        url_match = re.search(r"/view/(\d+)", job_url)
        if url_match:
            return url_match.group(1)

        return None

    async def _extract_text(self, card: ElementHandle, selector: str) -> str | None:
        """Extract and normalize text for a selector within a card.

        Args:
            card: Card element handle.
            selector: CSS selector to query inside card.

        Returns:
            Stripped text value when present, otherwise ``None``.
        """
        element = await card.query_selector(selector)
        if element is None:
            return None

        value = await element.inner_text()
        return self._normalize_text(value)

    async def _extract_raw_text(self, card: ElementHandle, selector: str) -> str | None:
        """Extract unnormalized text for a selector within a card.

        Args:
            card: Card element handle.
            selector: CSS selector to query inside card.

        Returns:
            Raw text when present, otherwise ``None``.
        """
        element = await card.query_selector(selector)
        if element is None:
            return None

        return await element.inner_text()

    async def _extract_first_text(
        self,
        card: ElementHandle,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract first non-empty normalized text from selector fallbacks.

        Args:
            card: Card element handle.
            selectors: Ordered CSS selector fallbacks.

        Returns:
            Normalized text when available, otherwise ``None``.
        """
        return await extract_first_text(
            root=card,
            selectors=selectors,
            normalize_text=self._normalize_text,
        )

    async def _extract_first_raw_text(
        self,
        card: ElementHandle,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract first non-empty raw text from selector fallbacks.

        Args:
            card: Card element handle.
            selectors: Ordered CSS selector fallbacks.

        Returns:
            Raw text when available, otherwise ``None``.
        """
        return await extract_first_raw_text(
            root=card,
            selectors=selectors,
            normalize_raw_text=normalize_title_whitespace,
        )

    async def _query_first(
        self,
        card: ElementHandle,
        selectors: tuple[str, ...],
    ) -> ElementHandle | None:
        """Return first matching element for provided selector fallbacks.

        Args:
            card: Card element handle.
            selectors: Ordered CSS selector fallbacks.

        Returns:
            First matched element or ``None``.
        """
        return await query_first(root=card, selectors=selectors)

    @classmethod
    def _to_absolute_url(cls, raw_url: str) -> str:
        """Ensure a LinkedIn URL is absolute.

        Args:
            raw_url: Relative or absolute URL string.

        Returns:
            Absolute LinkedIn URL.
        """
        return urljoin(f"{cls.BASE_URL}/", raw_url)

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace only.

        Args:
            value: Raw text value.

        Returns:
            Normalized string or ``None`` when the value is empty.
        """
        return normalize_title_whitespace(value)
