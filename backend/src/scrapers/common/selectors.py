"""Page-level selector fallback extraction helpers for scrapers."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from loguru import logger


class _PageSelectorQueryable(Protocol):
    """Protocol for Playwright-like page selector queries."""

    async def query_selector(self, selector: str) -> Any | None:
        """Return first matching page element for selector."""


class _ElementTextReadable(Protocol):
    """Protocol for elements exposing text extraction."""

    async def inner_text(self) -> str:
        """Return element text content."""


class _ElementHtmlReadable(Protocol):
    """Protocol for elements exposing JS evaluate extraction."""

    async def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript expression on element."""


async def extract_text_from_page_selectors(
    page: _PageSelectorQueryable,
    selectors: tuple[str, ...],
    normalize_text: Callable[[str], str | None],
    timeout_errors: tuple[type[BaseException], ...],
) -> str | None:
    """Extract normalized text from first matching selector.

    Args:
        page: Playwright-like page object.
        selectors: Ordered CSS selector fallbacks.
        normalize_text: Text normalizer callable.
        timeout_errors: Exceptions to ignore as timeout-like failures.

    Returns:
        Normalized text when found, otherwise ``None``.

    Notes:
        This helper intentionally only suppresses timeout-like errors. Unexpected
        selector errors are allowed to bubble so text extraction regressions are
        visible during scraping and tests. The HTML helper is more permissive
        because it runs as a best-effort enrichment path.
    """
    for selector in selectors:
        element = await page.query_selector(selector)
        if element is None:
            continue
        try:
            raw_text = await _as_text_element(element).inner_text()
            normalized = normalize_text(raw_text)
            if normalized:
                return normalized
        except timeout_errors as exc:
            logger.bind(selector=selector, error=str(exc)).debug(
                "Text extraction selector timed out"
            )
            continue
    return None


async def extract_html_from_page_selectors(
    page: _PageSelectorQueryable,
    selectors: tuple[str, ...],
    extraction_label: str,
    scraper_name: str,
    success_message: str,
    timeout_message: str,
    failure_message: str,
    timeout_errors: tuple[type[BaseException], ...],
) -> str | None:
    """Extract raw outer HTML from first matching selector.

    Args:
        page: Playwright-like page object.
        selectors: Ordered CSS selector fallbacks.
        extraction_label: Log label for extraction context.
        scraper_name: Scraper class name for logs.
        success_message: Log message on successful extraction.
        timeout_message: Log message on timeout-like failures.
        failure_message: Log message on non-timeout failures.
        timeout_errors: Exceptions to ignore as timeout-like failures.

    Returns:
        Raw outer HTML when found, otherwise ``None``.
    """
    for selector in selectors:
        element = await page.query_selector(selector)
        if element is None:
            continue

        try:
            raw_html = await _as_html_element(element).evaluate(
                "node => node.outerHTML"
            )
            if isinstance(raw_html, str) and raw_html.strip():
                logger.bind(
                    scraper=scraper_name,
                    selector=selector,
                    extraction_label=extraction_label,
                ).info(success_message)
                return raw_html.strip()
        except timeout_errors:
            logger.bind(
                scraper=scraper_name,
                selector=selector,
                extraction_label=extraction_label,
            ).debug(timeout_message)
            continue
        except Exception as exc:
            logger.bind(
                scraper=scraper_name,
                selector=selector,
                extraction_label=extraction_label,
                error=str(exc),
            ).debug(failure_message)
            continue

    return None


def _as_text_element(element: Any) -> _ElementTextReadable:
    """Cast a dynamic element to text-capable protocol type."""
    return element


def _as_html_element(element: Any) -> _ElementHtmlReadable:
    """Cast a dynamic element to HTML-capable protocol type."""
    return element


__all__ = ["extract_html_from_page_selectors", "extract_text_from_page_selectors"]
