"""Seek scraper exception hierarchy."""


class SeekScraperError(RuntimeError):
    """Base Seek scraper exception type."""


class SeekTransientError(SeekScraperError):
    """Raised for retryable Seek scraper failures."""


class SeekNonRetryableError(SeekScraperError):
    """Raised for deterministic Seek scraper failures."""


__all__ = [
    "SeekNonRetryableError",
    "SeekScraperError",
    "SeekTransientError",
]
