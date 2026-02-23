"""Indeed result-card parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urljoin

from loguru import logger
from playwright.async_api import ElementHandle

from src.scrapers.common.cards import extract_first_text, query_first


class IndeedCardParsingMixin:
    """Card-level parsing behavior for Indeed scraper."""

    async def _collect_job_cards(self) -> list[ElementHandle]:
        """Collect list card elements from the Indeed search page.

        Returns:
            List of card handles when selectors match.

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
            await self.page.mouse.wheel(0, 1300)
            await self.rate_limit(seconds=0.8)

        return []

    async def _parse_job_card(self, card: ElementHandle) -> dict[str, Any] | None:
        """Parse an Indeed result card into normalized payload.

        Args:
            card: Card element handle.

        Returns:
            Normalized job payload or ``None`` when required fields are absent.
        """
        link = await self._query_first(card, self.TITLE_LINK_SELECTORS)
        if link is None:
            return None

        raw_url = await link.get_attribute("href")
        card_data_jk = await card.get_attribute("data-jk")
        link_data_jk = await link.get_attribute("data-jk")
        job_url = self._to_absolute_url(raw_url=raw_url or "", data_jk=card_data_jk)
        external_id = self._extract_external_id(
            job_url=job_url,
            card_data_jk=card_data_jk,
            link_data_jk=link_data_jk,
        )

        if not external_id or not job_url:
            logger.bind(scraper=self.__class__.__name__).warning(
                "Skipping Indeed card without external identifier"
            )
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
        """Extract first non-empty normalized text from selector fallbacks.

        Args:
            root: Parent element handle.
            selectors: Selector fallback chain.

        Returns:
            First normalized text value or ``None``.
        """
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
        """Return first matching child element for selector chain.

        Args:
            root: Parent element handle.
            selectors: Selector fallback chain.

        Returns:
            First matching element or ``None``.
        """
        return await query_first(root=root, selectors=selectors)

    @classmethod
    def _to_absolute_url(cls, raw_url: str, data_jk: str | None) -> str | None:
        """Ensure a job URL is absolute and resilient to missing href values.

        Args:
            raw_url: Relative or absolute job URL.
            data_jk: Optional card-level Indeed job key.

        Returns:
            Absolute detail URL when recoverable, otherwise ``None``.
        """
        raw = raw_url.strip()
        if raw:
            return urljoin(f"{cls.BASE_URL}/", raw)
        if data_jk:
            return f"{cls.BASE_URL}/viewjob?jk={data_jk}"
        return None

    @staticmethod
    def _extract_external_id(
        job_url: str | None,
        card_data_jk: str | None,
        link_data_jk: str | None,
    ) -> str | None:
        """Extract the external id from data-jk attributes or URL fallback.

        Args:
            job_url: Absolute Indeed URL.
            card_data_jk: ``data-jk`` value from card element.
            link_data_jk: ``data-jk`` value from title link element.

        Returns:
            External identifier string, when available.
        """
        for token in (card_data_jk, link_data_jk):
            normalized = token.strip() if token else ""
            if normalized:
                return normalized

        if not job_url:
            return None

        match = re.search(r"[?&]jk=([a-zA-Z0-9_-]+)", job_url)
        if not match:
            return None
        return match.group(1)
