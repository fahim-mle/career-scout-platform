"""Text normalization and summary helpers for scrapers."""

from __future__ import annotations

from typing import Callable


def normalize_whitespace(value: str) -> str | None:
    """Normalize text by collapsing all whitespace sequences.

    Args:
        value: Raw text value.

    Returns:
        Normalized text when non-empty, otherwise ``None``.
    """
    normalized = " ".join(value.split())
    return normalized if normalized else None


def build_short_description(
    description_full: str | None,
    max_length: int,
    normalizer: Callable[[str], str | None] | None = None,
) -> str | None:
    """Build a short description from full text.

    Args:
        description_full: Full normalized description text.
        max_length: Maximum allowed length before truncation.
        normalizer: Optional text normalizer applied before truncation.

    Returns:
        Truncated summary string or ``None`` when input is empty.
    """
    if not description_full:
        return None

    summary_text = (
        normalizer(description_full)
        if callable(normalizer)
        else normalize_whitespace(description_full)
    )
    if not summary_text:
        return None

    if len(summary_text) <= max_length:
        return summary_text

    cutoff = summary_text.rfind(" ", 0, max_length)
    if cutoff <= 0:
        cutoff = max_length
    return f"{summary_text[:cutoff].rstrip()}..."


__all__ = ["build_short_description", "normalize_whitespace"]
