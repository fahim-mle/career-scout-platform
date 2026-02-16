"""LinkedIn Playwright scraper implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import random
import re
from typing import Any
from urllib.parse import urlencode, urljoin

from loguru import logger
from playwright.async_api import ElementHandle, TimeoutError as PlaywrightTimeoutError

from src.core.config import settings
from src.scrapers.base import BaseScraper


class LinkedInScraper(BaseScraper):
    """Scraper for public LinkedIn job search result pages."""

    BASE_URL = "https://www.linkedin.com"
    LOGIN_URL = f"{BASE_URL}/login"
    SEARCH_URL = f"{BASE_URL}/jobs/search/"
    PLATFORM = "linkedin"
    MAX_LIMIT = 10
    CHALLENGE_URL_CUES = ("checkpoint", "challenge", "captcha")
    CHALLENGE_SELECTORS = (
        "form[action*='checkpoint/challenge']",
        "iframe[src*='captcha']",
        "input[name='captcha']",
        "#captcha-internal",
        "[data-test-id*='challenge']",
    )
    JITTER_MIN_SECONDS = 0.2
    JITTER_MAX_SECONDS = 0.8
    DESCRIPTION_SELECTORS = (
        ".show-more-less-html__markup",
        ".jobs-description-content__text",
        ".jobs-description__content",
        "div.jobs-description-content__text--stretch",
        "#job-details",
        ".description__text",
        ".jobs-box__html-content",
        ".jobs-description__container",
    )
    SHORT_DESCRIPTION_MAX_LENGTH = 360
    JOB_CARD_SELECTORS = (
        "ul.jobs-search__results-list li",
        "ul.scaffold-layout__list-container li.jobs-search-results__list-item",
        "li.jobs-search-results__list-item",
        "[data-occludable-job-id]",
        "li.scaffold-layout__list-item",
        "div.scaffold-layout__list-container li",
    )
    JOB_LINK_SELECTORS = (
        "a.base-card__full-link",
        "a.job-card-container__link",
        "a.job-card-list__title--link",
        "a[data-control-name='job_card_click']",
    )
    TITLE_SELECTORS = (
        "h3.base-search-card__title",
        "a.job-card-list__title--link",
        ".job-card-list__title",
        "h3 a",
    )
    COMPANY_SELECTORS = (
        "h4.base-search-card__subtitle",
        ".job-card-container__company-name",
        "a.job-card-container__company-name",
        ".artdeco-entity-lockup__subtitle span",
    )
    LOCATION_SELECTORS = (
        "span.job-search-card__location",
        ".job-card-container__metadata-item",
        ".artdeco-entity-lockup__caption span",
    )
    DETAIL_JOB_TYPE_SELECTORS = (
        ".job-details-jobs-unified-top-card__job-insight",
        ".jobs-unified-top-card__job-insight",
        ".jobs-unified-top-card__workplace-type",
    )
    JOB_TYPE_HINTS = (
        "full-time",
        "part-time",
        "contract",
        "internship",
        "temporary",
        "freelance",
        "casual",
    )

    async def login(self) -> None:
        """Authenticate into LinkedIn using configured credentials.

        Raises:
            LinkedInAuthError: If credentials are missing or rejected.
            LinkedInChallengeError: If LinkedIn presents anti-bot challenge flow.
            LinkedInTransientError: If login fails due to transient browser/network issues.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        email = settings.LINKEDIN_EMAIL.strip()
        password = settings.resolved_linkedin_password

        if not email or not password:
            logger.bind(
                scraper=self.__class__.__name__,
                has_email=bool(email),
                has_password=bool(password),
            ).error("LinkedIn credentials are not configured")
            raise LinkedInAuthError("Missing LinkedIn credentials")

        logger.bind(
            scraper=self.__class__.__name__,
            email_domain=self._email_domain(email),
        ).info("Starting LinkedIn login flow")

        try:
            await self.page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
            await self._assert_no_challenge(stage="login_page")
            await self._rate_limit_with_jitter()
            await self.page.fill("#username", email)
            await self.page.fill("#password", password)
            await self.page.click('button[type="submit"]')
            await self.page.wait_for_load_state("domcontentloaded")
            await self._assert_no_challenge(stage="post_login")

            if "login" in self.page.url.lower():
                raise LinkedInAuthError(
                    "LinkedIn login failed. Check credentials or account restrictions."
                )

            logger.bind(scraper=self.__class__.__name__).info(
                "LinkedIn login flow completed"
            )
        except (LinkedInChallengeError, LinkedInAuthError):
            raise
        except PlaywrightTimeoutError as exc:
            logger.bind(scraper=self.__class__.__name__, error=str(exc)).error(
                "Timed out during LinkedIn login"
            )
            raise LinkedInTransientError("Timed out during LinkedIn login") from exc
        except Exception as exc:
            logger.bind(scraper=self.__class__.__name__, error=str(exc)).error(
                "Failed LinkedIn login flow"
            )
            raise LinkedInTransientError("LinkedIn login failed") from exc

    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Scrape job cards from LinkedIn search results.

        Args:
            query: Search keyword string.
            location: Search location string.
            limit: Maximum number of cards to collect.

        Returns:
            List of normalized job dictionaries.

        Raises:
            RuntimeError: If scraper page is not initialized.
            LinkedInNonRetryableError: If LinkedIn returns deterministic auth/challenge flow.
            LinkedInTransientError: If search loading fails due to retryable conditions.
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
        ).info("Starting LinkedIn jobs scrape")

        try:
            await self.page.goto(search_url, wait_until="domcontentloaded")
            await self._assert_no_challenge(stage="search_page")
            await self._rate_limit_with_jitter()
        except PlaywrightTimeoutError:
            logger.bind(
                scraper=self.__class__.__name__,
                query=query,
                location=location,
            ).warning("No LinkedIn job cards found before timeout")
            return []
        except LinkedInNonRetryableError:
            raise
        except Exception as exc:
            logger.bind(scraper=self.__class__.__name__, error=str(exc)).error(
                "Failed to load LinkedIn jobs search page"
            )
            raise LinkedInTransientError(
                "Failed to load LinkedIn jobs search page"
            ) from exc

        cards = await self._collect_job_cards()
        if not cards:
            logger.bind(
                scraper=self.__class__.__name__,
                query=query,
                location=location,
            ).warning("No LinkedIn job cards found before timeout")
            return []

        jobs: list[dict[str, Any]] = []

        for card in cards:
            if len(jobs) >= safe_limit:
                break

            try:
                await self._rate_limit_with_jitter(base_seconds=0.35)
                parsed_job = await self._parse_job_card(card)
                if parsed_job is None:
                    continue
                jobs.append(parsed_job)
            except Exception as exc:
                logger.bind(scraper=self.__class__.__name__, error=str(exc)).warning(
                    "Skipping LinkedIn card due to parse error"
                )
                continue

        for job_data in jobs:
            job_url = str(job_data.get("url", "")).strip()
            if not job_url:
                continue

            try:
                details = await self.scrape_job_details(job_url=job_url)
                if details:
                    job_data.update(details)
            except LinkedInNonRetryableError as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    url=job_url,
                    error=str(exc),
                    collected_jobs=len(jobs),
                ).warning(
                    "LinkedIn detail enrichment stopped due to non-retryable error; returning collected jobs"
                )
                break
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    url=job_url,
                    error=str(exc),
                ).warning("Failed to enrich LinkedIn job with detail page data")

        logger.bind(scraper=self.__class__.__name__, scraped_count=len(jobs)).info(
            "Completed LinkedIn jobs scrape"
        )
        return jobs

    async def scrape_job_details(self, job_url: str) -> dict[str, Any]:
        """Scrape selected LinkedIn detail fields from a job detail page.

        Args:
            job_url: Absolute LinkedIn job detail URL.

        Returns:
            Dictionary containing optional enrichable fields.

        Raises:
            RuntimeError: If scraper page is not initialized.
            LinkedInNonRetryableError: If LinkedIn challenge/auth state is detected.
            LinkedInTransientError: If detail page cannot be loaded reliably.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        logger.bind(scraper=self.__class__.__name__, url=job_url).info(
            "Scraping LinkedIn job details"
        )

        try:
            await self.page.goto(job_url, wait_until="domcontentloaded")
            await self._assert_no_challenge(stage="detail_page")
            await self._rate_limit_with_jitter()
        except LinkedInNonRetryableError:
            raise
        except PlaywrightTimeoutError as exc:
            raise LinkedInTransientError(
                "Timed out loading LinkedIn detail page"
            ) from exc
        except Exception as exc:
            raise LinkedInTransientError("Failed loading LinkedIn detail page") from exc

        description_full = await self._extract_text_from_page_selectors(
            selectors=self.DESCRIPTION_SELECTORS
        )

        details: dict[str, Any] = {
            "description_full": description_full,
            "description_short": self._build_short_description(description_full),
            "job_type": await self._extract_job_type(),
        }

        return {key: value for key, value in details.items() if value is not None}

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

        title = await self._extract_first_text(card, self.TITLE_SELECTORS)
        company = await self._extract_first_text(card, self.COMPANY_SELECTORS)
        location = await self._extract_first_text(card, self.LOCATION_SELECTORS)

        if not title or not company or not location:
            return None

        return {
            "external_id": external_id,
            "platform": self.PLATFORM,
            "url": absolute_url,
            "title": title,
            "company": company,
            "location": location,
            "scraped_at": datetime.now(timezone.utc),
        }

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

        if len(description_full) <= cls.SHORT_DESCRIPTION_MAX_LENGTH:
            return description_full

        cutoff = description_full.rfind(" ", 0, cls.SHORT_DESCRIPTION_MAX_LENGTH)
        if cutoff <= 0:
            cutoff = cls.SHORT_DESCRIPTION_MAX_LENGTH
        return f"{description_full[:cutoff].rstrip()}..."

    @classmethod
    def _build_search_url(cls, query: str, location: str) -> str:
        """Construct a LinkedIn search URL with encoded query parameters.

        Args:
            query: Search keyword.
            location: Search location.

        Returns:
            Fully encoded LinkedIn search URL.
        """
        params = {
            "keywords": query,
            "location": location,
            "f_TPR": "r86400",
        }
        return f"{cls.SEARCH_URL}?{urlencode(params)}"

    @classmethod
    def _to_absolute_url(cls, raw_url: str) -> str:
        """Ensure a LinkedIn URL is absolute.

        Args:
            raw_url: Relative or absolute URL string.

        Returns:
            Absolute LinkedIn URL.
        """
        return urljoin(f"{cls.BASE_URL}/", raw_url)

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
        for selector in selectors:
            value = await self._extract_text(card, selector)
            if value:
                return value

        return None

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
        for selector in selectors:
            element = await card.query_selector(selector)
            if element is not None:
                return element

        return None

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace.

        Args:
            value: Raw text value.

        Returns:
            Normalized string or ``None`` when the value is empty.
        """
        normalized = " ".join(value.split())
        return normalized if normalized else None

    async def _assert_no_challenge(self, stage: str) -> None:
        """Raise when LinkedIn challenge/captcha cues are detected.

        Args:
            stage: Logical flow stage where challenge check runs.

        Raises:
            LinkedInChallengeError: If challenge URL or selectors are detected.
        """
        if self.page is None:
            raise RuntimeError("Scraper page is not initialized")

        current_url = self.page.url.lower()
        if any(cue in current_url for cue in self.CHALLENGE_URL_CUES):
            logger.bind(
                scraper=self.__class__.__name__, stage=stage, url=self.page.url
            ).warning("LinkedIn challenge detected via URL cue")
            raise LinkedInChallengeError("LinkedIn challenge/checkpoint detected")

        for selector in self.CHALLENGE_SELECTORS:
            challenge_node = await self.page.query_selector(selector)
            if challenge_node is not None:
                logger.bind(
                    scraper=self.__class__.__name__,
                    stage=stage,
                    selector=selector,
                    url=self.page.url,
                ).warning("LinkedIn challenge detected via page selector")
                raise LinkedInChallengeError("LinkedIn captcha/challenge detected")

    async def _rate_limit_with_jitter(self, base_seconds: float | None = None) -> None:
        """Apply scraper pacing delay with randomized jitter.

        Args:
            base_seconds: Optional base delay before jitter.
        """
        delay_base = self.rate_limit_seconds if base_seconds is None else base_seconds
        jitter = random.uniform(self.JITTER_MIN_SECONDS, self.JITTER_MAX_SECONDS)
        await self.rate_limit(seconds=delay_base + jitter)

    @staticmethod
    def _email_domain(email: str) -> str:
        """Extract and return a safe email domain token for logs.

        Args:
            email: Raw email string.

        Returns:
            Email domain token or ``"unknown"`` when unavailable.
        """
        if "@" not in email:
            return "unknown"
        return email.split("@", maxsplit=1)[1].lower()


class LinkedInScraperError(RuntimeError):
    """Base LinkedIn scraper exception type."""


class LinkedInTransientError(LinkedInScraperError):
    """Raised for transient LinkedIn scraper failures eligible for retry."""


class LinkedInNonRetryableError(LinkedInScraperError):
    """Raised for deterministic failures that should not be retried."""


class LinkedInChallengeError(LinkedInNonRetryableError):
    """Raised when LinkedIn challenge/captcha flow is detected."""


class LinkedInAuthError(LinkedInNonRetryableError):
    """Raised when LinkedIn authentication configuration or credentials fail."""


__all__ = [
    "LinkedInAuthError",
    "LinkedInChallengeError",
    "LinkedInNonRetryableError",
    "LinkedInScraper",
    "LinkedInScraperError",
    "LinkedInTransientError",
]
