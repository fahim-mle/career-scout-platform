"""Shared scraper helpers for cross-platform extraction logic."""

from src.scrapers.common.cards import (
    extract_first_raw_text,
    extract_first_text,
    query_first,
)
from src.scrapers.common.metadata import filter_non_empty_values, merge_non_empty
from src.scrapers.common.selectors import (
    extract_html_from_page_selectors,
    extract_text_from_page_selectors,
)
from src.scrapers.common.text import build_short_description, normalize_whitespace

__all__ = [
    "build_short_description",
    "extract_first_raw_text",
    "extract_first_text",
    "extract_html_from_page_selectors",
    "extract_text_from_page_selectors",
    "filter_non_empty_values",
    "merge_non_empty",
    "normalize_whitespace",
    "query_first",
]
