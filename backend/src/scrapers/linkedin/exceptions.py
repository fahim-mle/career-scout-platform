"""LinkedIn scraper exception hierarchy."""


class LinkedInScraperError(RuntimeError):
    """Base LinkedIn scraper exception type."""


class LinkedInTransientError(LinkedInScraperError):
    """Raised for transient LinkedIn scraper failures eligible for retry."""


class LinkedInNonRetryableError(LinkedInScraperError):
    """Raised for deterministic failures that should not be retried."""


class LinkedInChallengeError(LinkedInNonRetryableError):
    """Raised when LinkedIn challenge/captcha flow is detected."""


class LinkedInAuthError(LinkedInNonRetryableError):
    """Raised when LinkedIn authentication configuration or credentials fail."""


__all__ = [
    "LinkedInAuthError",
    "LinkedInChallengeError",
    "LinkedInNonRetryableError",
    "LinkedInScraperError",
    "LinkedInTransientError",
]
