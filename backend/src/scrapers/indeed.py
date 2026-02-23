"""Indeed Playwright scraper implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlencode, urljoin

from loguru import logger
from playwright.async_api import ElementHandle, TimeoutError as PlaywrightTimeoutError

from src.scrapers.base import BaseScraper


class IndeedScraper(BaseScraper):
    """Scraper for public Indeed Australia job search pages."""

    BASE_URL = "https://au.indeed.com"
    SEARCH_URL = f"{BASE_URL}/jobs"
    PLATFORM = "indeed"
    MAX_LIMIT = 10
    SHORT_DESCRIPTION_MAX_LENGTH = 360
    JOB_CARD_SELECTORS = (
        "div[data-jk]",
        "article[data-jk]",
        "div.job_seen_beacon",
    )
    TITLE_LINK_SELECTORS = (
        "h2.jobTitle a",
        "a.jcs-JobTitle",
        "a[data-jk]",
        "a[href*='/viewjob']",
    )
    COMPANY_SELECTORS = (
        '[data-testid="company-name"]',
        "span.companyName",
        "a[data-testid='company-name']",
    )
    LOCATION_SELECTORS = (
        '[data-testid="job-location"]',
        '[data-testid="text-location"]',
        "div.companyLocation",
    )
    CARD_SNIPPET_SELECTORS = (
        '[data-testid="jobsnippet_footer"]',
        '[data-testid="job-snippet"]',
        "div.job-snippet",
    )
    DESCRIPTION_SELECTORS = (
        "#jobDescriptionText",
        "div#jobDescriptionText",
        "main",
    )
    DESCRIPTION_HTML_SELECTORS = (
        "#jobDescriptionText",
        'div[data-testid="jobsearch-JobComponent-description"]',
        'section[data-testid="jobsearch-jobDescriptionContainer"]',
    )
    DESCRIPTION_HTML_FALLBACK_SELECTORS = (
        "main",
        "article",
        "body",
    )
    SALARY_AND_TYPE_SELECTORS = (
        "#salaryInfoAndJobType",
        '[data-testid="salaryInfoAndJobType"]',
        "div.jobsearch-JobMetadataHeader-item",
    )
    HEADER_JOB_TYPE_SELECTORS = (
        "div.jobsearch-JobMetadataHeader-item",
        '[data-testid="jobsearch-JobMetadataHeader-item"]',
    )
    POPUP_CLOSE_SELECTORS = (
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        '[data-testid="closeButton"]',
        "button.icl-Modal-close",
    )
    JOB_TYPE_HINTS = (
        "full-time",
        "part-time",
        "contract",
        "temporary",
        "casual",
        "internship",
    )

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
            details["description_short"] = description_short
        details["scraped_jobs"] = raw_description_html

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
            except Exception:
                continue

    async def _extract_job_type(self, salary_type_text: str | None) -> str | None:
        """Extract job type from salary/type area and metadata fallback.

        Args:
            salary_type_text: Optional text from salary/type container.

        Returns:
            Inferred job type value when found.
        """
        if salary_type_text:
            parsed = self._extract_job_type_from_text(salary_type_text)
            if parsed:
                return parsed

        metadata_text = await self._extract_text_from_page_selectors(
            selectors=self.HEADER_JOB_TYPE_SELECTORS
        )
        if not metadata_text:
            return None
        return self._extract_job_type_from_text(metadata_text)

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
        """Return first matching child element for selector chain.

        Args:
            root: Parent element handle.
            selectors: Selector fallback chain.

        Returns:
            First matching element or ``None``.
        """
        for selector in selectors:
            element = await root.query_selector(selector)
            if element is not None:
                return element
        return None

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
                    ).info("Extracted Indeed raw description HTML")
                    return raw_html.strip()
            except PlaywrightTimeoutError:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    extraction_label=extraction_label,
                ).debug("Indeed raw HTML extraction timed out")
                continue
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    selector=selector,
                    extraction_label=extraction_label,
                    error=str(exc),
                ).debug("Indeed raw HTML extraction failed for selector")
                continue

        return None

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

        if len(description_full) <= cls.SHORT_DESCRIPTION_MAX_LENGTH:
            return description_full

        cutoff = description_full.rfind(" ", 0, cls.SHORT_DESCRIPTION_MAX_LENGTH)
        if cutoff <= 0:
            cutoff = cls.SHORT_DESCRIPTION_MAX_LENGTH
        return f"{description_full[:cutoff].rstrip()}..."

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

    @classmethod
    def _extract_job_type_from_text(cls, value: str) -> str | None:
        """Infer normalized job type from free text.

        Args:
            value: Raw metadata text.

        Returns:
            Canonicalized job type label when hint is found.
        """
        normalized = cls._normalize_text(value)
        if not normalized:
            return None

        lowered = normalized.lower()
        for hint in cls.JOB_TYPE_HINTS:
            if hint in lowered:
                return hint.title()
        return None

    @classmethod
    def _extract_salary_range(cls, value: str) -> dict[str, Any] | None:
        """Extract salary range from salary metadata text.

        Args:
            value: Raw salary text from detail page.

        Returns:
            Structured salary range dictionary when both bounds are present.
        """
        normalized = cls._normalize_text(value)
        if not normalized:
            return None

        matches = re.findall(r"(?:AUD\s*)?\$\s*([\d,.]+)\s*([kK]?)", normalized)
        if len(matches) < 2:
            return None

        min_value = cls._parse_salary_number(matches[0][0], bool(matches[0][1]))
        max_value = cls._parse_salary_number(matches[1][0], bool(matches[1][1]))
        if min_value is None or max_value is None:
            return None
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        return {
            "min": min_value,
            "max": max_value,
            "currency": "AUD",
            "raw": normalized,
        }

    @staticmethod
    def _parse_salary_number(value: str, has_k_suffix: bool) -> int | None:
        """Parse a salary number token to integer value.

        Args:
            value: Numeric token string.
            has_k_suffix: Whether token had a ``k`` suffix.

        Returns:
            Parsed integer salary value, otherwise ``None``.
        """
        compact = value.replace(",", "").strip()
        if not compact:
            return None

        try:
            number = float(compact)
        except ValueError:
            return None

        if has_k_suffix:
            number *= 1000

        return int(number)

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace.

        Args:
            value: Raw text.

        Returns:
            Normalized string or ``None`` when empty.
        """
        normalized = " ".join(value.split())
        return normalized if normalized else None


class IndeedScraperError(RuntimeError):
    """Base Indeed scraper exception type."""


class IndeedTransientError(IndeedScraperError):
    """Raised for retryable Indeed scraper failures."""


class IndeedNonRetryableError(IndeedScraperError):
    """Raised for deterministic Indeed scraper failures."""


__all__ = [
    "IndeedNonRetryableError",
    "IndeedScraper",
    "IndeedScraperError",
    "IndeedTransientError",
]
