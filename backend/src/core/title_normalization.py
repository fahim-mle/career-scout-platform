"""Helpers for conservative job title normalization."""

from __future__ import annotations

import re


def normalize_title_whitespace(value: str | None) -> str | None:
    """Collapse title whitespace and return ``None`` when empty.

    Args:
        value: Raw title value.

    Returns:
        Whitespace-collapsed title text when non-empty, otherwise ``None``.
    """
    if value is None:
        return None

    normalized = " ".join(value.split())
    return normalized or None


def collapse_adjacent_duplicate_title_phrase(value: str) -> str:
    """Collapse exact adjacent repeated title phrases conservatively.

    Args:
        value: Whitespace-normalized title text.

    Returns:
        Deduplicated title when an exact adjacent duplicate phrase artifact is
        detected, otherwise the original value.
    """
    compact = " ".join(value.split())
    if not compact:
        return value

    tokens = compact.split(" ")
    if len(tokens) < 4:
        return compact

    midpoint = len(tokens) // 2
    if len(tokens) % 2 == 0:
        left_tokens = tokens[:midpoint]
        right_tokens = tokens[midpoint:]
        if _tokens_match_exact_phrase(left_tokens, right_tokens):
            return " ".join(left_tokens)

    separator_match = re.match(
        r"^(?P<left>.+?)\s*(?:\||/|-|,|:)\s*(?P<right>.+)$",
        compact,
    )
    if separator_match is None:
        return compact

    left = " ".join(separator_match.group("left").split())
    right = " ".join(separator_match.group("right").split())
    if not left or not right:
        return compact

    left_tokens = left.split(" ")
    right_tokens = right.split(" ")
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return compact

    if _tokens_match_exact_phrase(left_tokens, right_tokens):
        return left

    return compact


def normalize_job_title(value: str | None) -> str | None:
    """Normalize a job title using conservative duplicate-phrase collapse.

    Args:
        value: Raw title value.

    Returns:
        Normalized title text, or ``None`` when input is empty.
    """
    compact = normalize_title_whitespace(value)
    if compact is None:
        return None
    return collapse_adjacent_duplicate_title_phrase(compact)


def title_preview_for_log(value: str | None, limit: int = 120) -> str | None:
    """Create a bounded log-safe title preview.

    Args:
        value: Title text value.
        limit: Maximum preview length.

    Returns:
        Truncated single-line preview suitable for structured logs.
    """
    compact = normalize_title_whitespace(value)
    if compact is None:
        return None
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _tokens_match_exact_phrase(left_tokens: list[str], right_tokens: list[str]) -> bool:
    """Check whether token lists match exactly in a case-insensitive way.

    Args:
        left_tokens: Tokenized left phrase.
        right_tokens: Tokenized right phrase.

    Returns:
        ``True`` when phrase tokens are equal after case-fold normalization.
    """
    if len(left_tokens) != len(right_tokens):
        return False
    return [token.casefold() for token in left_tokens] == [
        token.casefold() for token in right_tokens
    ]
