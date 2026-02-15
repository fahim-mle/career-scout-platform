"""Task package exports for Celery autodiscovery and imports."""

from src.tasks.scraper_tasks import DatabaseTask, scrape_linkedin_jobs, test_task

__all__ = ["DatabaseTask", "scrape_linkedin_jobs", "test_task"]
