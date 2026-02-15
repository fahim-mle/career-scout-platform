"""Celery tasks for scraping workflows."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any

from celery import Task
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_app import celery_app
from src.db.session import get_session


class DatabaseTask(Task):
    """Base Celery task with lightweight DB session helper."""

    abstract = True

    def get_db_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return async DB session context manager for future task usage.

        Returns:
            Async context manager yielding an ``AsyncSession``.
        """
        return get_session()


@celery_app.task(name="src.tasks.scraper_tasks.test_task", bind=True, base=DatabaseTask)
def test_task(self: DatabaseTask, message: str = "Celery is working") -> dict[str, str]:
    """Execute a simple task to validate Celery worker availability.

    Args:
        message: Optional message payload for test execution.

    Returns:
        Dictionary containing execution status and message.

    Raises:
        Exception: Re-raises unexpected task execution exceptions.
    """
    try:
        logger.info(
            "Executing Celery test task", message=message, task_id=self.request.id
        )
        response = {"status": "success", "message": message}
        logger.info(
            "Celery test task completed", response=response, task_id=self.request.id
        )
        return response
    except Exception as exc:
        logger.error(
            "Celery test task failed",
            message=message,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_linkedin_jobs",
    bind=True,
    base=DatabaseTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def scrape_linkedin_jobs(
    self: DatabaseTask,
    query: str,
    location: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Placeholder task for LinkedIn scraping orchestration.

    Args:
        query: Search query for role title.
        location: Geographic location for search.
        limit: Maximum number of jobs to scrape.

    Returns:
        Dictionary with placeholder execution metadata.

    Raises:
        ValueError: If the limit is not positive.
        Exception: Re-raises unexpected errors to trigger Celery retries.
    """
    try:
        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        logger.info(
            "Starting placeholder LinkedIn scrape task",
            query=query,
            location=location,
            limit=limit,
            task_id=self.request.id,
        )

        result = {
            "status": "queued",
            "platform": "linkedin",
            "query": query,
            "location": location,
            "limit": limit,
            "message": "Placeholder task executed. Scraper integration pending.",
        }

        logger.info("Completed placeholder LinkedIn scrape task", result=result)
        return result
    except Exception as exc:
        logger.error(
            "LinkedIn scrape task failed",
            query=query,
            location=location,
            limit=limit,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
