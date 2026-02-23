"""Metadata filtering helpers shared by scraper implementations."""

from __future__ import annotations

from typing import Any, Mapping


def filter_non_empty_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Filter out ``None`` and blank-string values from a mapping.

    Args:
        values: Input key/value mapping.

    Returns:
        New dictionary with non-empty values only.
    """
    return {
        key: value
        for key, value in values.items()
        if value is not None and (not isinstance(value, str) or value.strip() != "")
    }


def merge_non_empty(
    base: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge mappings while keeping only non-empty incoming values.

    Args:
        base: Baseline mapping that always remains present.
        incoming: Candidate fields to merge into ``base``.

    Returns:
        New merged dictionary.
    """
    merged = dict(base)
    merged.update(filter_non_empty_values(incoming))
    return merged


__all__ = ["filter_non_empty_values", "merge_non_empty"]
