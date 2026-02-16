"""Unit tests for BaseScraper lifecycle and utilities."""

from __future__ import annotations

from typing import Any

import pytest

import src.scrapers.base as base_module
from src.scrapers.base import BaseScraper


pytestmark = pytest.mark.asyncio


class FakePage:
    """Simple fake page that records timeout configuration."""

    def __init__(self) -> None:
        self.default_timeout: int | None = None

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.default_timeout = timeout_ms


class FakeContext:
    """Simple fake browser context with configurable close behavior."""

    def __init__(self, page: FakePage, *, close_raises: bool = False) -> None:
        self.page = page
        self.close_raises = close_raises
        self.new_page_called = False
        self.closed = False

    async def new_page(self) -> FakePage:
        self.new_page_called = True
        return self.page

    async def close(self) -> None:
        self.closed = True
        if self.close_raises:
            raise RuntimeError("context close failed")


class FakeBrowser:
    """Simple fake browser with context creation and close tracking."""

    def __init__(self, context: FakeContext, *, close_raises: bool = False) -> None:
        self.context = context
        self.close_raises = close_raises
        self.new_context_kwargs: dict[str, Any] | None = None
        self.closed = False

    async def new_context(self, **kwargs: Any) -> FakeContext:
        self.new_context_kwargs = kwargs
        return self.context

    async def close(self) -> None:
        self.closed = True
        if self.close_raises:
            raise RuntimeError("browser close failed")


class FakeChromium:
    """Simple fake Chromium launcher."""

    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.launch_headless: bool | None = None

    async def launch(self, *, headless: bool) -> FakeBrowser:
        self.launch_headless = headless
        return self.browser


class FakePlaywright:
    """Simple fake Playwright object with stop tracking."""

    def __init__(self, browser: FakeBrowser, *, stop_raises: bool = False) -> None:
        self.chromium = FakeChromium(browser)
        self.stop_raises = stop_raises
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True
        if self.stop_raises:
            raise RuntimeError("playwright stop failed")


class FakePlaywrightManager:
    """Simple fake async_playwright manager."""

    def __init__(self, playwright: FakePlaywright) -> None:
        self.playwright = playwright
        self.started = False

    async def start(self) -> FakePlaywright:
        self.started = True
        return self.playwright


class ConcreteScraper(BaseScraper):
    """Concrete scraper implementation used only for testing BaseScraper."""

    def __init__(
        self, *args: Any, login_error: Exception | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.login_error = login_error
        self.login_called = False

    async def login(self) -> None:
        self.login_called = True
        if self.login_error is not None:
            raise self.login_error

    async def scrape_jobs(
        self,
        query: str,
        location: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return []


async def test_base_scraper_is_abstract_and_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        BaseScraper()


async def test_aenter_aexit_lifecycle_initializes_and_cleans_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    playwright = FakePlaywright(browser)
    manager = FakePlaywrightManager(playwright)

    monkeypatch.setattr(base_module, "async_playwright", lambda: manager)

    scraper = ConcreteScraper(headless=False)

    async with scraper as entered_scraper:
        assert entered_scraper is scraper
        assert manager.started is True
        assert playwright.chromium.launch_headless is False
        assert browser.new_context_kwargs == {
            "viewport": {
                "width": BaseScraper.DEFAULT_VIEWPORT_WIDTH,
                "height": BaseScraper.DEFAULT_VIEWPORT_HEIGHT,
            },
            "user_agent": BaseScraper.CHROME_WINDOWS_USER_AGENT,
        }
        assert context.new_page_called is True
        assert page.default_timeout == BaseScraper.DEFAULT_TIMEOUT_MS
        assert scraper.login_called is True

    assert context.closed is True
    assert browser.closed is True
    assert playwright.stopped is True
    assert scraper.page is None
    assert scraper.context is None
    assert scraper.browser is None
    assert scraper.playwright is None


async def test_aenter_raises_runtime_error_on_login_failure_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePage()
    context = FakeContext(page)
    browser = FakeBrowser(context)
    playwright = FakePlaywright(browser)
    manager = FakePlaywrightManager(playwright)

    monkeypatch.setattr(base_module, "async_playwright", lambda: manager)

    scraper = ConcreteScraper(login_error=ValueError("bad credentials"))

    with pytest.raises(RuntimeError, match="Failed to start scraper"):
        await scraper.__aenter__()

    assert scraper.login_called is True
    assert context.closed is True
    assert browser.closed is True
    assert playwright.stopped is True
    assert scraper.page is None
    assert scraper.context is None
    assert scraper.browser is None
    assert scraper.playwright is None


async def test_rate_limit_uses_default_delay_and_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(base_module.asyncio, "sleep", fake_sleep)

    scraper = ConcreteScraper(rate_limit_seconds=4.5)

    await scraper.rate_limit()
    await scraper.rate_limit(1.25)

    assert sleep_calls == [4.5, 1.25]


async def test_aexit_swallows_close_and_stop_exceptions() -> None:
    page = FakePage()
    context = FakeContext(page, close_raises=True)
    browser = FakeBrowser(context, close_raises=True)
    playwright = FakePlaywright(browser, stop_raises=True)
    scraper = ConcreteScraper()
    scraper.page = page
    scraper.context = context
    scraper.browser = browser
    scraper.playwright = playwright

    await scraper.__aexit__(None, None, None)

    assert context.closed is True
    assert browser.closed is True
    assert playwright.stopped is True
    assert scraper.page is None
    assert scraper.context is None
    assert scraper.browser is None
    assert scraper.playwright is None
