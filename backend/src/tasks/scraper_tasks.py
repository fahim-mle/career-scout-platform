"""Celery tasks for scraping workflows."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import Any

from celery import Task
from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import DuplicateJobError, RepositoryError
from src.celery_app import celery_app
from src.db.session import get_session
from src.repositories.job import JobRepository
from src.scrapers.linkedin import (
    LinkedInNonRetryableError,
    LinkedInScraper,
    LinkedInTransientError,
)

MAX_LINKEDIN_SCRAPE_LIMIT = 10
MAX_SCRAPER_TASK_RETRIES = 3
DEFAULT_RETRY_COUNTDOWN_SECONDS = 60


async def _run_linkedin_scrape_and_persist(
    query: str,
    location: str,
    limit: int,
    task_id: str | None,
) -> dict[str, Any]:
    """Scrape LinkedIn jobs and persist new rows.

    Args:
        query: Search query for LinkedIn jobs.
        location: Search location for LinkedIn jobs.
        limit: Maximum number of jobs to scrape.
        task_id: Celery task id for structured logging.

    Returns:
        Structured scrape and persistence metrics.

    Raises:
        RuntimeError: If scraper execution fails before persistence loop.
    """
    logger.info(
        "Starting LinkedIn scrape orchestration",
        query=query,
        location=location,
        limit=limit,
        task_id=task_id,
    )

    async with LinkedInScraper(headless=True, rate_limit_seconds=3.0) as scraper:
        scraped_jobs = await scraper.scrape_jobs(
            query=query,
            location=location,
            limit=limit,
        )

    created_count = 0
    duplicate_count = 0
    failed_count = 0

    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        for job_payload in scraped_jobs:
            external_id = str(job_payload.get("external_id", ""))

            if not external_id:
                failed_count += 1
                logger.warning(
                    "Skipping scraped job without external_id",
                    task_id=task_id,
                )
                continue

            try:
                existing_job = await job_repository.get_by_external_id(
                    external_id=external_id,
                    platform="linkedin",
                )
                if existing_job is not None:
                    duplicate_count += 1
                    continue

                await job_repository.create(job_payload)
                created_count += 1
            except DuplicateJobError:
                duplicate_count += 1
            except RepositoryError as exc:
                failed_count += 1
                logger.error(
                    "Failed to persist scraped LinkedIn job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                )
            except Exception as exc:
                failed_count += 1
                logger.error(
                    "Unexpected persistence error for scraped LinkedIn job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                    exc_info=True,
                )

    result = {
        "status": "success",
        "platform": "linkedin",
        "query": query,
        "location": location,
        "scraped": len(scraped_jobs),
        "created": created_count,
        "duplicates": duplicate_count,
        "failed": failed_count,
    }
    logger.info(
        "Completed LinkedIn scrape orchestration", task_id=task_id, result=result
    )
    return result


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


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Collect the linked exception chain for classification.

    Args:
        exc: Top-level exception to inspect.

    Returns:
        Ordered list including root exception and causes/contexts.
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        next_exc = (
            current.__cause__ if current.__cause__ is not None else current.__context__
        )
        current = next_exc

    return chain


def _is_transient_error(exc: BaseException) -> bool:
    """Check if an exception should trigger a retry.

    Args:
        exc: Exception raised during scrape execution.

    Returns:
        ``True`` when failure is transient and retryable.
    """
    transient_types: tuple[type[BaseException], ...] = (
        LinkedInTransientError,
        PlaywrightTimeoutError,
        asyncio.TimeoutError,
        ConnectionError,
        OSError,
    )
    return any(isinstance(item, transient_types) for item in _exception_chain(exc))


def _is_non_retryable_error(exc: BaseException) -> bool:
    """Check if an exception should never trigger a retry.

    Args:
        exc: Exception raised during scrape execution.

    Returns:
        ``True`` for deterministic non-retryable failures.
    """
    non_retryable_types: tuple[type[BaseException], ...] = (
        LinkedInNonRetryableError,
        ValueError,
    )
    return any(isinstance(item, non_retryable_types) for item in _exception_chain(exc))


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_linkedin_jobs",
    bind=True,
    base=DatabaseTask,
)
def scrape_linkedin_jobs(
    self: DatabaseTask,
    query: str,
    location: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Scrape LinkedIn jobs and persist non-duplicate records.

    Args:
        query: Search query for role title.
        location: Geographic location for search.
        limit: Maximum number of jobs to scrape.

    Returns:
        Dictionary with scrape and persistence counters.

    Raises:
        ValueError: If the limit is not positive.
        Exception: Re-raises unexpected errors and transient retry exceptions.
    """
    try:
        if not settings.SCRAPER_ENABLED:
            logger.warning(
                "LinkedIn scrape task skipped because scraper is disabled",
                query=query,
                location=location,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": "linkedin",
                "query": query,
                "location": location,
                "reason": "SCRAPER_ENABLED is false",
            }

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        bounded_limit = min(limit, MAX_LINKEDIN_SCRAPE_LIMIT)
        if bounded_limit != limit:
            logger.warning(
                "LinkedIn scrape limit exceeded max, capping to safe value",
                requested_limit=limit,
                bounded_limit=bounded_limit,
                task_id=self.request.id,
            )

        result = asyncio.run(
            _run_linkedin_scrape_and_persist(
                query=query,
                location=location,
                limit=bounded_limit,
                task_id=self.request.id,
            )
        )
        return result
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "LinkedIn scrape task failed with non-retryable error",
                query=query,
                location=location,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "LinkedIn scrape task hit transient error, scheduling retry",
                query=query,
                location=location,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCRAPER_TASK_RETRIES,
            )

        logger.error(
            "LinkedIn scrape task failed with unexpected non-retryable error",
            query=query,
            location=location,
            limit=limit,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
