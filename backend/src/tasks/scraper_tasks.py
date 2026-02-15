"""Celery tasks for scraping workflows."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
import json
from pathlib import Path
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
# Fixed retry delay keeps retry timing deterministic.
DEFAULT_RETRY_COUNTDOWN_SECONDS = 60
LINKEDIN_PROFILE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "scrapers"
    / "config"
    / "linkedin_search_profiles.json"
)
MAX_PROFILE_RUNS_PER_TASK = 25


def _build_job_update_payload(
    existing_job: Any,
    scraped_payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a safe update payload for selected LinkedIn enrichments.

    Args:
        existing_job: Existing ORM job entity from repository lookup.
        scraped_payload: Newly scraped payload for the same external id.

    Returns:
        Field map containing only missing description/job-type values.
    """
    enrichable_fields = (
        "description_full",
        "description_short",
        "job_type",
    )
    updates: dict[str, Any] = {}

    for field in enrichable_fields:
        current_value = getattr(existing_job, field, None)
        new_value = scraped_payload.get(field)
        if current_value is None and new_value is not None:
            updates[field] = new_value

    return updates


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
    updated_count = 0
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
                    update_payload = _build_job_update_payload(
                        existing_job=existing_job,
                        scraped_payload=job_payload,
                    )
                    if update_payload:
                        await job_repository.update(existing_job.id, update_payload)
                        updated_count += 1
                        continue

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
        "updated": updated_count,
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
        None.
    """
    logger.info("Executing Celery test task", message=message, task_id=self.request.id)
    response = {"status": "success", "message": message}
    logger.info(
        "Celery test task completed", response=response, task_id=self.request.id
    )
    return response


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


def _load_linkedin_search_profiles() -> list[dict[str, Any]]:
    """Load active LinkedIn search profiles from JSON configuration.

    Returns:
        Ordered list of validated active profile dictionaries.

    Raises:
        ValueError: If configuration file is missing or invalid.
    """
    if not LINKEDIN_PROFILE_CONFIG_PATH.exists():
        raise ValueError(
            f"LinkedIn profile config not found: {LINKEDIN_PROFILE_CONFIG_PATH}"
        )

    try:
        payload = json.loads(LINKEDIN_PROFILE_CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("LinkedIn profile config is not valid JSON") from exc

    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("LinkedIn profile config must include a 'profiles' array")

    validated_profiles: list[dict[str, Any]] = []
    for index, profile in enumerate(profiles, start=1):
        if not isinstance(profile, dict):
            logger.warning("Skipping non-object profile entry", index=index)
            continue

        if not profile.get("active", True):
            continue

        query = str(profile.get("query", "")).strip()
        location = str(profile.get("location", "")).strip()
        requested_limit = profile.get("limit", 5)

        if not query or not location:
            logger.warning(
                "Skipping invalid profile with missing query/location",
                index=index,
                query=query,
                location=location,
            )
            continue

        try:
            limit = int(requested_limit)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid profile limit; defaulting to 5",
                index=index,
                requested_limit=requested_limit,
            )
            limit = 5

        if limit <= 0:
            logger.warning(
                "Invalid non-positive profile limit; defaulting to 5",
                index=index,
                requested_limit=requested_limit,
            )
            limit = 5

        bounded_limit = min(limit, MAX_LINKEDIN_SCRAPE_LIMIT)

        validated_profiles.append(
            {
                "id": str(profile.get("id", f"profile-{index}")),
                "query": query,
                "location": location,
                "limit": bounded_limit,
                "priority": int(profile.get("priority", index)),
            }
        )

    validated_profiles.sort(key=lambda profile: profile["priority"])
    return validated_profiles[:MAX_PROFILE_RUNS_PER_TASK]


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
    name="src.tasks.scraper_tasks.scrape_linkedin_profile_set",
    bind=True,
    base=DatabaseTask,
)
def scrape_linkedin_profile_set(self: DatabaseTask) -> dict[str, Any]:
    """Run LinkedIn scraping across configured role/location profiles.

    Returns:
        Aggregated scrape metrics for all processed profiles.
    """
    if not settings.SCRAPER_ENABLED:
        logger.warning(
            "LinkedIn profile set task skipped because scraper is disabled",
            task_id=self.request.id,
        )
        return {
            "status": "skipped",
            "platform": "linkedin",
            "reason": "SCRAPER_ENABLED is false",
            "profiles_processed": 0,
        }

    profiles = _load_linkedin_search_profiles()
    if not profiles:
        logger.warning(
            "No active LinkedIn profiles found in configuration",
            task_id=self.request.id,
            config_path=str(LINKEDIN_PROFILE_CONFIG_PATH),
        )
        return {
            "status": "skipped",
            "platform": "linkedin",
            "reason": "No active profiles configured",
            "profiles_processed": 0,
        }

    totals = {
        "scraped": 0,
        "created": 0,
        "updated": 0,
        "duplicates": 0,
        "failed": 0,
    }
    per_profile: list[dict[str, Any]] = []

    try:
        for profile in profiles:
            result = asyncio.run(
                _run_linkedin_scrape_and_persist(
                    query=profile["query"],
                    location=profile["location"],
                    limit=profile["limit"],
                    task_id=self.request.id,
                )
            )
            per_profile.append(
                {
                    "id": profile["id"],
                    "query": profile["query"],
                    "location": profile["location"],
                    "limit": profile["limit"],
                    "result": result,
                }
            )
            totals["scraped"] += int(result.get("scraped", 0))
            totals["created"] += int(result.get("created", 0))
            totals["updated"] += int(result.get("updated", 0))
            totals["duplicates"] += int(result.get("duplicates", 0))
            totals["failed"] += int(result.get("failed", 0))

        return {
            "status": "success",
            "platform": "linkedin",
            "profiles_processed": len(per_profile),
            "totals": totals,
            "profiles": per_profile,
        }
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "LinkedIn profile set task failed with non-retryable error",
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "LinkedIn profile set task hit transient error, scheduling retry",
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCRAPER_TASK_RETRIES,
            )

        logger.error(
            "LinkedIn profile set task failed with unexpected non-retryable error",
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise


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
