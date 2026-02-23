"""Card-level selector fallback helpers for scraper implementations."""

from __future__ import annotations

from typing import Any, Callable, Protocol


class _SelectorQueryable(Protocol):
    """Protocol for Playwright-like selector querying roots."""

    async def query_selector(self, selector: str) -> Any | None:
        """Return first matching child for selector."""


class _TextElement(Protocol):
    """Protocol for Playwright-like text elements."""

    async def inner_text(self) -> str:
        """Return element text content."""


async def query_first(
    root: _SelectorQueryable,
    selectors: tuple[str, ...],
) -> Any | None:
    """Return first matching element for a selector fallback chain.

    Args:
        root: Parent query root.
        selectors: Ordered selector list.

    Returns:
        First matching element or ``None`` when no selector matches.
    """
    for selector in selectors:
        element = await root.query_selector(selector)
        if element is not None:
            return element
    return None


async def extract_first_text(
    root: _SelectorQueryable,
    selectors: tuple[str, ...],
    normalize_text: Callable[[str], str | None],
) -> str | None:
    """Extract first non-empty normalized text from fallback selectors.

    Args:
        root: Parent query root.
        selectors: Ordered selector list.
        normalize_text: Text normalizer callable.

    Returns:
        First normalized non-empty string, else ``None``.
    """
    for selector in selectors:
        element = await root.query_selector(selector)
        if element is None:
            continue
        value = normalize_text(await _as_text_element(element).inner_text())
        if value:
            return value
    return None


async def extract_first_raw_text(
    root: _SelectorQueryable,
    selectors: tuple[str, ...],
    normalize_raw_text: Callable[[str | None], str | None],
) -> str | None:
    """Extract first non-empty raw text normalized for storage.

    Args:
        root: Parent query root.
        selectors: Ordered selector list.
        normalize_raw_text: Raw-text normalization callable.

    Returns:
        First normalized non-empty string, else ``None``.
    """
    for selector in selectors:
        element = await root.query_selector(selector)
        if element is None:
            continue
        value = normalize_raw_text(await _as_text_element(element).inner_text())
        if value:
            return value
    return None


def _as_text_element(element: Any) -> _TextElement:
    """Cast dynamic element to text-capable protocol type.

    Args:
        element: Runtime Playwright element.

    Returns:
        Element cast to ``_TextElement`` protocol.
    """
    return element


__all__ = ["extract_first_raw_text", "extract_first_text", "query_first"]
