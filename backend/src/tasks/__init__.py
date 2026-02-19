"""Task package exports for Celery autodiscovery and imports."""

from src.tasks.scraper_tasks import (
    DatabaseTask,
    scrape_linkedin_jobs,
    scrape_linkedin_profile_set,
    test_task,
)
from src.tasks.enrichment_tasks import (
    enrich_single_job_task,
    enrich_unstructured_jobs_task,
)

__all__ = [
    "DatabaseTask",
    "enrich_single_job_task",
    "enrich_unstructured_jobs_task",
    "scrape_linkedin_jobs",
    "scrape_linkedin_profile_set",
    "test_task",
]
