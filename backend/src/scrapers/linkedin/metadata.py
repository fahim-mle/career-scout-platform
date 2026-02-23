"""LinkedIn top-card metadata parsing helpers."""

from __future__ import annotations

import re
from typing import Any

from src.scrapers.linkedin.constants import PLATFORM


def build_default_metadata() -> dict[str, Any]:
    """Build default LinkedIn metadata payload for generic schema storage.

    Returns:
        Metadata object containing stable LinkedIn metadata keys.
    """
    return {
        "platform": PLATFORM,
        "location": None,
        "date_posted": None,
        "number_of_applicants": None,
        "promoted_by_hirer": False,
        "actively_reviewing_applicants": False,
    }


def normalize_metadata_text(value: str | None) -> str | None:
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


def looks_like_relative_date(value: str) -> bool:
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


def parse_top_card_metadata_text(raw_text: str | None) -> dict[str, Any]:
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
    normalized = normalize_metadata_text(raw_text)
    if not normalized:
        return parsed

    segments = [
        segment
        for segment in (
            normalize_metadata_text(part) for part in re.split(r"[·•|]", normalized)
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
        if looks_like_relative_date(segment) and parsed["date_posted"] is None:
            parsed["date_posted"] = segment
            continue
        if parsed["location"] is None:
            parsed["location"] = segment

    return parsed


__all__ = [
    "build_default_metadata",
    "looks_like_relative_date",
    "normalize_metadata_text",
    "parse_top_card_metadata_text",
]
