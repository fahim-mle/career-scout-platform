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
from src.core.title_normalization import (
    normalize_job_title,
    normalize_title_whitespace,
    title_preview_for_log,
)
from src.scrapers.base import BaseScraper
from src.scrapers.common.cards import (
    extract_first_raw_text,
    extract_first_text,
    query_first,
)
from src.scrapers.common.selectors import (
    extract_html_from_page_selectors,
    extract_text_from_page_selectors,
)
from src.scrapers.common.text import build_short_description


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
    DESCRIPTION_SHOW_MORE_SELECTORS = (
        "button.show-more-less-html__button",
        "button[aria-label*='Show more']",
        "button[aria-label*='See more']",
    )
    DESCRIPTION_HTML_SELECTORS = (
        "#job-details",
        "div.jobs-box__html-content",
        "section.show-more-less-html",
        "div.show-more-less-html__markup",
        "div.jobs-description-content__text--stretch",
        "div.jobs-description-content__text",
        "div.jobs-description__content",
    )
    CARD_SNIPPET_SELECTORS = (
        ".job-search-card__snippet",
        ".job-card-list__description",
        ".base-search-card__metadata",
        ".job-search-card__snippet-wrapper",
    )
    DESCRIPTION_FALLBACK_SELECTORS = (
        "main",
        "section",
        "article",
        "body",
    )
    MAX_DETAIL_EXTRACTION_ATTEMPTS = 2
    SHORT_DESCRIPTION_MAX_LENGTH = 360
    MAX_DESCRIPTION_FULL_LENGTH = 3_000
    MAX_FALLBACK_DESCRIPTION_HTML_LENGTH = 100_000
    DESCRIPTION_END_MARKERS = (
        "Set alert for similar jobs",
        "Interested in working with us in the future?",
        "Looking for talent? Post a job",
        "About the company",
    )
    DESCRIPTION_TRAILING_MORE_PATTERN = re.compile(
        r"(?:\.\.\.|…)\s*more\s*$", re.IGNORECASE
    )
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
    TOP_CARD_METADATA_SELECTORS = (
        ".job-details-jobs-unified-top-card__primary-description-container",
        ".job-details-jobs-unified-top-card__tertiary-description-container",
        ".jobs-unified-top-card__primary-description-container",
        ".jobs-unified-top-card__subtitle-primary-grouping",
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
            except Exception:
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
        return {
            "platform": cls.PLATFORM,
            "location": None,
            "date_posted": None,
            "number_of_applicants": None,
            "promoted_by_hirer": False,
            "actively_reviewing_applicants": False,
        }

    @classmethod
    def _parse_top_card_metadata_text(cls, raw_text: str | None) -> dict[str, Any]:
        """Parse LinkedIn top-card tertiary text into metadata keys.

        Args:
            raw_text: Raw top-card text content from LinkedIn detail page.

        Returns:
            Parsed metadata fields excluding the fixed platform key.
        """
        parsed: dict[str, Any] = {
            "location": None,
            "date_posted": None,
            "number_of_applicants": None,
            "promoted_by_hirer": False,
            "actively_reviewing_applicants": False,
        }
        normalized = cls._normalize_metadata_text(raw_text)
        if not normalized:
            return parsed

        segments = [
            segment
            for segment in (
                cls._normalize_metadata_text(part)
                for part in re.split(r"[·•|]", normalized)
            )
            if segment
        ]

        for segment in segments:
            segment_lower = segment.lower()
            if "promoted by hirer" in segment_lower:
                parsed["promoted_by_hirer"] = True
                continue
            if "actively reviewing applicants" in segment_lower:
                parsed["actively_reviewing_applicants"] = True
                continue
            if "applicant" in segment_lower and parsed["number_of_applicants"] is None:
                parsed["number_of_applicants"] = segment
                continue
            if cls._looks_like_relative_date(segment) and parsed["date_posted"] is None:
                parsed["date_posted"] = segment
                continue
            if parsed["location"] is None:
                parsed["location"] = segment

        return parsed

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
        if value is None:
            return None

        compact = re.sub(r"\s+", " ", value).strip()
        return compact or None

    @staticmethod
    def _looks_like_relative_date(value: str) -> bool:
        """Return whether text appears to be LinkedIn relative date wording.

        Args:
            value: Candidate metadata segment.

        Returns:
            ``True`` when segment resembles a relative date value.
        """
        lowered = value.lower()
        if any(token in lowered for token in ("today", "yesterday", "just now")):
            return True

        return bool(
            re.search(
                r"\b\d+\+?\s+(minute|hour|day|week|month|year)s?\s+ago\b",
                lowered,
            )
        )

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

    @staticmethod
    def _normalize_text(value: str) -> str | None:
        """Normalize text by collapsing whitespace only.

        Args:
            value: Raw text value.

        Returns:
            Normalized string or ``None`` when the value is empty.
        """
        return normalize_title_whitespace(value)

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
