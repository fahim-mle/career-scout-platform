"""Public LinkedIn scraper exports with backward-compatible import path."""

from src.scrapers.linkedin.exceptions import (
    LinkedInAuthError,
    LinkedInChallengeError,
    LinkedInNonRetryableError,
    LinkedInScraperError,
    LinkedInTransientError,
)
from src.scrapers.linkedin.scraper import LinkedInScraper

__all__ = [
    "LinkedInAuthError",
    "LinkedInChallengeError",
    "LinkedInNonRetryableError",
    "LinkedInScraper",
    "LinkedInScraperError",
    "LinkedInTransientError",
]
