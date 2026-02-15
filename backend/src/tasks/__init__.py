"""Task package exports for Celery autodiscovery and imports."""

from src.tasks.scraper_tasks import (
    DatabaseTask,
    scrape_linkedin_jobs,
    scrape_linkedin_profile_set,
    test_task,
)

__all__ = [
    "DatabaseTask",
    "scrape_linkedin_jobs",
    "scrape_linkedin_profile_set",
    "test_task",
]
