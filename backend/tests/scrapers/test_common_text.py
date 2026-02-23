"""Tests for shared scraper text helpers."""

from __future__ import annotations

from src.scrapers.common.text import build_short_description


def test_build_short_description_uses_callable_normalizer() -> None:
    """Helper should call normalizer when callable is provided."""

    def _normalizer(value: str) -> str:
        return value.replace("  ", " ").strip()

    result = build_short_description(
        description_full="  Build  robust APIs  ",
        max_length=360,
        normalizer=_normalizer,
    )

    assert result == "Build robust APIs"


def test_build_short_description_ignores_non_callable_normalizer() -> None:
    """Helper should fallback safely when normalizer is not callable."""
    result = build_short_description(
        description_full="  Build robust APIs  ",
        max_length=360,
        normalizer="not-callable",  # type: ignore[arg-type]
    )

    assert result == "Build robust APIs"
