"""Base Playwright scraper abstraction for job platforms."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


class BaseScraper(ABC):
    """Abstract base class for Playwright-powered job scrapers."""

    DEFAULT_TIMEOUT_MS = 30_000
    DEFAULT_VIEWPORT_WIDTH = 1920
    DEFAULT_VIEWPORT_HEIGHT = 1080
    CHROME_WINDOWS_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )

    def __init__(self, headless: bool = True, rate_limit_seconds: float = 3.0) -> None:
        """Initialize scraper runtime configuration.

        Args:
            headless: Whether to run Chromium in headless mode.
            rate_limit_seconds: Delay to apply between network-heavy actions.
        """
        self.headless = headless
        self.rate_limit_seconds = rate_limit_seconds
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> BaseScraper:
        """Start Playwright and browser resources.

        Returns:
            The initialized scraper instance.

        Raises:
            RuntimeError: If scraper startup fails.
        """
        try:
            logger.bind(
                scraper=self.__class__.__name__,
                headless=self.headless,
            ).info("Starting scraper lifecycle")

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context(
                viewport={
                    "width": self.DEFAULT_VIEWPORT_WIDTH,
                    "height": self.DEFAULT_VIEWPORT_HEIGHT,
                },
                user_agent=self.CHROME_WINDOWS_USER_AGENT,
            )
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.DEFAULT_TIMEOUT_MS)

            logger.bind(
                scraper=self.__class__.__name__,
                timeout_ms=self.DEFAULT_TIMEOUT_MS,
            ).info("Scraper browser initialized")

            await self.login()
            logger.bind(scraper=self.__class__.__name__).info(
                "Scraper authentication completed"
            )
            return self
        except Exception as exc:
            logger.bind(
                scraper=self.__class__.__name__,
                error=str(exc),
            ).exception("Failed to initialize scraper")
            await self.__aexit__(None, None, None)
            raise RuntimeError("Failed to start scraper") from exc

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close scraper browser resources safely.

        Args:
            exc_type: Exception type raised in context, if any.
            exc_val: Exception value raised in context, if any.
            exc_tb: Exception traceback raised in context, if any.
        """
        logger.bind(scraper=self.__class__.__name__).info(
            "Shutting down scraper lifecycle"
        )

        if self.context is not None:
            try:
                await self.context.close()
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    error=str(exc),
                ).exception("Failed to close browser context")
            finally:
                self.context = None

        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    error=str(exc),
                ).exception("Failed to close browser")
            finally:
                self.browser = None

        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception as exc:
                logger.bind(
                    scraper=self.__class__.__name__,
                    error=str(exc),
                ).exception("Failed to stop Playwright")
            finally:
                self.playwright = None

        self.page = None
        logger.bind(scraper=self.__class__.__name__).info("Scraper shutdown completed")

    async def rate_limit(self, seconds: float | None = None) -> None:
        """Pause scraper execution to reduce anti-bot triggers.

        Args:
            seconds: Optional override delay in seconds.
        """
        delay_seconds = self.rate_limit_seconds if seconds is None else seconds
        logger.bind(
            scraper=self.__class__.__name__,
            delay_seconds=delay_seconds,
        ).info("Applying scraper rate limit")
        await asyncio.sleep(delay_seconds)

    @abstractmethod
    async def login(self) -> None:
        """Perform platform-specific authentication and setup."""

    @abstractmethod
    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Scrape job listings from a target platform.

        Args:
            query: Search query for job titles or keywords.
            location: Geographic location to target in search.
            limit: Maximum number of jobs to scrape.

        Returns:
            A list of normalized job payload dictionaries.
        """


__all__ = ["BaseScraper"]
