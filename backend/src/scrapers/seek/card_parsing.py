"""Seek result-card parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from playwright.async_api import ElementHandle

from src.scrapers.common.cards import extract_first_text, query_first


class SeekCardParsingMixin:
    """Card-level parsing behavior for Seek scraper."""

    async def _collect_job_cards(self) -> list[ElementHandle]:
        """Collect job card elements from search results.

        Returns:
            Matched card elements or an empty list when no cards are found.

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
            await self.page.mouse.wheel(0, 1400)
            await self.rate_limit(seconds=0.8)

        return []

    async def _parse_job_card(self, card: ElementHandle) -> dict[str, Any] | None:
        """Parse an individual Seek card into normalized payload.

        Args:
            card: Card element handle from Seek results.

        Returns:
            Parsed payload when required fields are present, otherwise ``None``.
        """
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

    async def _extract_first_text(
        self,
        root: ElementHandle,
        selectors: tuple[str, ...],
    ) -> str | None:
        """Extract first non-empty normalized text from selector fallback list."""
        return await extract_first_text(
            root=root,
            selectors=selectors,
            normalize_text=self._normalize_text,
        )

    async def _query_first(
        self,
        root: ElementHandle,
        selectors: tuple[str, ...],
    ) -> ElementHandle | None:
        """Return first matching child element for fallback selectors."""
        return await query_first(root=root, selectors=selectors)

    @classmethod
    def _to_absolute_url(cls, raw_url: str) -> str:
        """Ensure URL is absolute Seek URL.

        Args:
            raw_url: Relative or absolute URL value.

        Returns:
            Absolute Seek URL.
        """
        if raw_url.startswith("http"):
            return raw_url
        return f"{cls.BASE_URL}{raw_url}"

    @staticmethod
    def _extract_external_id(job_url: str) -> str | None:
        """Extract numeric external id from Seek job URL.

        Args:
            job_url: Absolute job URL.

        Returns:
            Numeric id string when available, otherwise ``None``.
        """
        match = re.search(r"/job/(\d+)", job_url)
        if not match:
            return None
        return match.group(1)
