"""Task package exports for Celery autodiscovery and imports."""

from src.tasks.scraper_tasks import (
    DatabaseTask,
    scrape_indeed_jobs,
    scrape_seek_jobs,
    scrape_linkedin_jobs,
    scrape_linkedin_profile_set,
    test_task,
)
from src.tasks.enrichment_tasks import (
    enrich_single_job_task,
    enrich_unstructured_jobs_task,
)
from src.tasks.scoring_tasks import (
    score_all_unscored_jobs_task,
    score_single_job_task,
)

__all__ = [
    "DatabaseTask",
    "enrich_single_job_task",
    "enrich_unstructured_jobs_task",
    "score_all_unscored_jobs_task",
    "score_single_job_task",
    "scrape_indeed_jobs",
    "scrape_linkedin_jobs",
    "scrape_linkedin_profile_set",
    "scrape_seek_jobs",
    "test_task",
]
