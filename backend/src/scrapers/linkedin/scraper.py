"""LinkedIn Playwright scraper implementation."""

from __future__ import annotations

import random
from typing import Any
from urllib.parse import urlencode

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.core.config import settings
from src.scrapers.base import BaseScraper
from src.scrapers.linkedin.card_parsing import LinkedInCardParsingMixin
from src.scrapers.linkedin.constants import (
    BASE_URL,
    CARD_SNIPPET_SELECTORS,
    CHALLENGE_SELECTORS,
    CHALLENGE_URL_CUES,
    COMPANY_SELECTORS,
    DESCRIPTION_END_MARKERS,
    DESCRIPTION_FALLBACK_SELECTORS,
    DESCRIPTION_HTML_SELECTORS,
    DESCRIPTION_SELECTORS,
    DESCRIPTION_SHOW_MORE_SELECTORS,
    DESCRIPTION_TRAILING_MORE_PATTERN,
    DETAIL_JOB_TYPE_SELECTORS,
    JITTER_MAX_SECONDS,
    JITTER_MIN_SECONDS,
    JOB_CARD_SELECTORS,
    JOB_LINK_SELECTORS,
    JOB_TYPE_HINTS,
    LOCATION_SELECTORS,
    LOGIN_URL,
    MAX_DESCRIPTION_FULL_LENGTH,
    MAX_DETAIL_EXTRACTION_ATTEMPTS,
    MAX_FALLBACK_DESCRIPTION_HTML_LENGTH,
    MAX_LIMIT,
    PLATFORM,
    SEARCH_URL,
    SHORT_DESCRIPTION_MAX_LENGTH,
    TITLE_SELECTORS,
    TOP_CARD_METADATA_SELECTORS,
)
from src.scrapers.linkedin.detail_parsing import LinkedInDetailParsingMixin
from src.scrapers.linkedin.exceptions import (
    LinkedInAuthError,
    LinkedInChallengeError,
    LinkedInNonRetryableError,
    LinkedInTransientError,
)


class LinkedInScraper(
    BaseScraper, LinkedInCardParsingMixin, LinkedInDetailParsingMixin
):
    """Scraper for public LinkedIn job search result pages."""

    BASE_URL = BASE_URL
    LOGIN_URL = LOGIN_URL
    SEARCH_URL = SEARCH_URL
    PLATFORM = PLATFORM
    MAX_LIMIT = MAX_LIMIT
    CHALLENGE_URL_CUES = CHALLENGE_URL_CUES
    CHALLENGE_SELECTORS = CHALLENGE_SELECTORS
    JITTER_MIN_SECONDS = JITTER_MIN_SECONDS
    JITTER_MAX_SECONDS = JITTER_MAX_SECONDS
    DESCRIPTION_SELECTORS = DESCRIPTION_SELECTORS
    DESCRIPTION_SHOW_MORE_SELECTORS = DESCRIPTION_SHOW_MORE_SELECTORS
    DESCRIPTION_HTML_SELECTORS = DESCRIPTION_HTML_SELECTORS
    CARD_SNIPPET_SELECTORS = CARD_SNIPPET_SELECTORS
    DESCRIPTION_FALLBACK_SELECTORS = DESCRIPTION_FALLBACK_SELECTORS
    MAX_DETAIL_EXTRACTION_ATTEMPTS = MAX_DETAIL_EXTRACTION_ATTEMPTS
    SHORT_DESCRIPTION_MAX_LENGTH = SHORT_DESCRIPTION_MAX_LENGTH
    MAX_DESCRIPTION_FULL_LENGTH = MAX_DESCRIPTION_FULL_LENGTH
    MAX_FALLBACK_DESCRIPTION_HTML_LENGTH = MAX_FALLBACK_DESCRIPTION_HTML_LENGTH
    DESCRIPTION_END_MARKERS = DESCRIPTION_END_MARKERS
    DESCRIPTION_TRAILING_MORE_PATTERN = DESCRIPTION_TRAILING_MORE_PATTERN
    JOB_CARD_SELECTORS = JOB_CARD_SELECTORS
    JOB_LINK_SELECTORS = JOB_LINK_SELECTORS
    TITLE_SELECTORS = TITLE_SELECTORS
    COMPANY_SELECTORS = COMPANY_SELECTORS
    LOCATION_SELECTORS = LOCATION_SELECTORS
    DETAIL_JOB_TYPE_SELECTORS = DETAIL_JOB_TYPE_SELECTORS
    TOP_CARD_METADATA_SELECTORS = TOP_CARD_METADATA_SELECTORS
    JOB_TYPE_HINTS = JOB_TYPE_HINTS

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
                else:
                    logger.bind(
                        scraper=self.__class__.__name__,
                        url=job_url,
                        external_id=job_data.get("external_id"),
                    ).warning("No LinkedIn detail fields extracted for job")
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
        if not description_full:
            description_full = await self._extract_description_with_fallback()
        description_full = self._sanitize_description_text(description_full)

        raw_description_html: str | None = None
        try:
            raw_description_html = await self._extract_description_html_with_fallback()
        except Exception as exc:
            logger.bind(
                scraper=self.__class__.__name__,
                url=job_url,
                error=str(exc),
            ).warning("Failed LinkedIn raw description HTML extraction")

        metadata = self._build_default_metadata()
        try:
            metadata = await self._extract_top_card_metadata()
        except Exception as exc:
            logger.bind(
                scraper=self.__class__.__name__,
                url=job_url,
                error=str(exc),
            ).warning("Failed LinkedIn top-card metadata extraction")

        details: dict[str, Any] = {
            "description_full": description_full,
            "description_short": self._build_short_description(description_full),
            "job_type": await self._extract_job_type(),
            "scraped_jobs": raw_description_html,
            "metadata": metadata,
        }

        return {key: value for key, value in details.items() if value is not None}

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
