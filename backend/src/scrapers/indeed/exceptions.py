"""Indeed scraper exception hierarchy."""


class IndeedScraperError(RuntimeError):
    """Base Indeed scraper exception type."""


class IndeedTransientError(IndeedScraperError):
    """Raised for retryable Indeed scraper failures."""


class IndeedNonRetryableError(IndeedScraperError):
    """Raised for deterministic Indeed scraper failures."""


__all__ = [
    "IndeedNonRetryableError",
    "IndeedScraperError",
    "IndeedTransientError",
]
