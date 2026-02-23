"""Seek detail metadata parsing helpers."""

from __future__ import annotations

from typing import Any

from src.scrapers.common.metadata import merge_non_empty
from src.scrapers.common.text import normalize_whitespace


def extract_classification_parts(value: str | None) -> tuple[str | None, str | None]:
    """Split classification text into classification/subclassification parts.

    Args:
        value: Raw classification text from Seek detail page.

    Returns:
        Tuple ``(classification, subclassification)``.
    """
    normalized = normalize_whitespace(value or "")
    if not normalized:
        return (None, None)

    for delimiter in (" / ", " - ", " | ", ": "):
        if delimiter in normalized:
            left, right = normalized.split(delimiter, maxsplit=1)
            classification = normalize_whitespace(left)
            subclassification = normalize_whitespace(right)
            return (classification, subclassification)

    return (normalized, None)


def build_seek_metadata(
    *,
    platform: str,
    location: str | None,
    date_posted: str | None,
    work_type: str | None,
    classifications_text: str | None,
    salary_text: str | None,
) -> dict[str, Any]:
    """Build normalized Seek metadata payload from extracted fields.

    Args:
        platform: Stable platform key for metadata payload.
        location: Optional location text from detail page.
        date_posted: Optional posting date text from detail page.
        work_type: Optional work type text from detail page.
        classifications_text: Optional classifications text from detail page.
        salary_text: Optional salary text from detail page.

    Returns:
        Metadata dictionary containing available non-empty Seek values.
    """
    classification, subclassification = extract_classification_parts(
        classifications_text
    )

    metadata: dict[str, Any] = {"platform": platform}
    optional_fields = {
        "location": location,
        "date_posted": date_posted,
        "work_type": work_type,
        "classification": classification,
        "subclassification": subclassification,
        "salary_text": salary_text,
    }
    return merge_non_empty(metadata, optional_fields)


__all__ = ["build_seek_metadata", "extract_classification_parts"]
