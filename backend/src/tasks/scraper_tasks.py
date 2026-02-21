"""Celery tasks for scraping workflows."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
import json
from pathlib import Path
import time
from typing import Any

from celery import Task
from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import DuplicateJobError, RepositoryError
from src.core.metrics import (
    increment_jobs_created,
    increment_jobs_duplicates,
    increment_jobs_errors,
    increment_jobs_scraped,
    increment_jobs_updated,
    increment_scraper_runs,
    observe_scraper_duration,
    set_jobs_in_database,
)
from src.celery_app import celery_app
from src.db.session import get_session
from src.repositories.job import JobRepository
from src.scrapers.indeed import (
    IndeedNonRetryableError,
    IndeedScraper,
    IndeedTransientError,
)
from src.scrapers.linkedin import (
    LinkedInNonRetryableError,
    LinkedInScraper,
    LinkedInTransientError,
)
from src.scrapers.seek import SeekNonRetryableError, SeekScraper, SeekTransientError

MAX_LINKEDIN_SCRAPE_LIMIT = 10
MAX_SEEK_SCRAPE_LIMIT = 10
MAX_INDEED_SCRAPE_LIMIT = 10
MAX_SCRAPER_TASK_RETRIES = 3
# Fixed retry delay keeps retry timing deterministic.
DEFAULT_RETRY_COUNTDOWN_SECONDS = 60
LINKEDIN_PROFILE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "scrapers"
    / "config"
    / "linkedin_search_profiles.json"
)
SEEK_PROFILE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "scrapers"
    / "config"
    / "seek_search_profiles.json"
)
INDEED_PROFILE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "scrapers"
    / "config"
    / "indeed_search_profiles.json"
)
MAX_PROFILE_RUNS_PER_TASK = 25
LINKEDIN_PLATFORM = "linkedin"
SEEK_PLATFORM = "seek"
INDEED_PLATFORM = "indeed"
ENRICHMENT_TASK_NAME = "src.tasks.enrichment_tasks.enrich_unstructured_jobs_task"


def _record_scraper_result_metrics(
    platform: str,
    *,
    scraped: int = 0,
    created: int = 0,
    duplicates: int = 0,
    failed: int = 0,
    updated: int = 0,
    jobs_in_database: int | None = None,
    task_id: str | None = None,
) -> None:
    """Record scraper result metrics with safe validation handling.

    Args:
        platform: Scraper platform label.
        scraped: Number of scraped jobs.
        created: Number of newly created jobs.
        duplicates: Number of duplicate jobs.
        failed: Number of persistence failures.
        updated: Number of enriched existing jobs.
        jobs_in_database: Optional known jobs currently in DB for this run.
        task_id: Optional Celery task id for structured logs.

    Returns:
        None.
    """
    try:
        increment_jobs_scraped(platform=platform, count=max(scraped, 0))
        increment_jobs_created(platform=platform, count=max(created, 0))
        increment_jobs_duplicates(platform=platform, count=max(duplicates, 0))
        increment_jobs_errors(platform=platform, count=max(failed, 0))
        increment_jobs_updated(platform=platform, count=max(updated, 0))

        if jobs_in_database is not None:
            set_jobs_in_database(platform=platform, total=max(jobs_in_database, 0))
    except ValueError as exc:
        logger.warning(
            "Skipped scraper result metrics due to invalid values",
            platform=platform,
            scraped=scraped,
            created=created,
            duplicates=duplicates,
            failed=failed,
            updated=updated,
            jobs_in_database=jobs_in_database,
            task_id=task_id,
            error=str(exc),
        )


def _record_scraper_run_metrics(
    platform: str,
    status: str,
    duration_seconds: float,
    task_id: str | None,
) -> None:
    """Record scraper run status and duration metrics.

    Args:
        platform: Scraper platform label.
        status: Run status label (success/failure/skipped).
        duration_seconds: Runtime in seconds.
        task_id: Optional Celery task id for structured logs.

    Returns:
        None.
    """
    try:
        increment_scraper_runs(platform=platform, status=status)
        observe_scraper_duration(platform=platform, duration_seconds=duration_seconds)
    except ValueError as exc:
        logger.warning(
            "Skipped scraper run metrics due to invalid values",
            platform=platform,
            status=status,
            duration_seconds=duration_seconds,
            task_id=task_id,
            error=str(exc),
        )


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
    enrichment_job_ids: set[int] = set()

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
                        updated_job = await job_repository.update(
                            existing_job.id, update_payload
                        )
                        if updated_job is not None:
                            enrichment_job_ids.add(updated_job.id)
                            updated_count += 1
                        continue

                    duplicate_count += 1
                    continue

                created_job = await job_repository.create(job_payload)
                enrichment_job_ids.add(created_job.id)
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
        "enrichment_job_ids": sorted(enrichment_job_ids),
    }
    logger.info(
        "Completed LinkedIn scrape orchestration", task_id=task_id, result=result
    )
    return result


async def _run_seek_scrape_and_persist(
    query: str,
    location: str,
    limit: int,
    task_id: str | None,
) -> dict[str, Any]:
    """Scrape Seek jobs and persist new or enriched rows."""
    logger.info(
        "Starting Seek scrape orchestration",
        query=query,
        location=location,
        limit=limit,
        task_id=task_id,
    )

    async with SeekScraper(headless=True, rate_limit_seconds=3.0) as scraper:
        scraped_jobs = await scraper.scrape_jobs(
            query=query,
            location=location,
            limit=limit,
        )

    created_count = 0
    updated_count = 0
    duplicate_count = 0
    failed_count = 0
    enrichment_job_ids: set[int] = set()

    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        for job_payload in scraped_jobs:
            external_id = str(job_payload.get("external_id", ""))

            if not external_id:
                failed_count += 1
                logger.warning(
                    "Skipping scraped Seek job without external_id",
                    task_id=task_id,
                )
                continue

            try:
                existing_job = await job_repository.get_by_external_id(
                    external_id=external_id,
                    platform=SEEK_PLATFORM,
                )
                if existing_job is not None:
                    update_payload = _build_job_update_payload(
                        existing_job=existing_job,
                        scraped_payload=job_payload,
                    )
                    if update_payload:
                        updated_job = await job_repository.update(
                            existing_job.id, update_payload
                        )
                        if updated_job is not None:
                            enrichment_job_ids.add(updated_job.id)
                            updated_count += 1
                        continue

                    duplicate_count += 1
                    continue

                created_job = await job_repository.create(job_payload)
                enrichment_job_ids.add(created_job.id)
                created_count += 1
            except DuplicateJobError:
                duplicate_count += 1
            except RepositoryError as exc:
                failed_count += 1
                logger.error(
                    "Failed to persist scraped Seek job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                )
            except Exception as exc:
                failed_count += 1
                logger.error(
                    "Unexpected persistence error for scraped Seek job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                    exc_info=True,
                )

    result = {
        "status": "success",
        "platform": SEEK_PLATFORM,
        "query": query,
        "location": location,
        "scraped": len(scraped_jobs),
        "created": created_count,
        "updated": updated_count,
        "duplicates": duplicate_count,
        "failed": failed_count,
        "enrichment_job_ids": sorted(enrichment_job_ids),
    }
    logger.info("Completed Seek scrape orchestration", task_id=task_id, result=result)
    return result


async def _run_indeed_scrape_and_persist(
    query: str,
    location: str,
    limit: int,
    task_id: str | None,
) -> dict[str, Any]:
    """Scrape Indeed jobs and persist new or enriched rows."""
    logger.info(
        "Starting Indeed scrape orchestration",
        query=query,
        location=location,
        limit=limit,
        task_id=task_id,
    )

    async with IndeedScraper(headless=True, rate_limit_seconds=5.0) as scraper:
        scraped_jobs = await scraper.scrape_jobs(
            query=query,
            location=location,
            limit=limit,
        )

    created_count = 0
    updated_count = 0
    duplicate_count = 0
    failed_count = 0
    enrichment_job_ids: set[int] = set()

    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        for job_payload in scraped_jobs:
            external_id = str(job_payload.get("external_id", ""))

            if not external_id:
                failed_count += 1
                logger.warning(
                    "Skipping scraped Indeed job without external_id",
                    task_id=task_id,
                )
                continue

            try:
                existing_job = await job_repository.get_by_external_id(
                    external_id=external_id,
                    platform=INDEED_PLATFORM,
                )
                if existing_job is not None:
                    update_payload = _build_job_update_payload(
                        existing_job=existing_job,
                        scraped_payload=job_payload,
                    )
                    if update_payload:
                        updated_job = await job_repository.update(
                            existing_job.id, update_payload
                        )
                        if updated_job is not None:
                            enrichment_job_ids.add(updated_job.id)
                            updated_count += 1
                        continue

                    duplicate_count += 1
                    continue

                created_job = await job_repository.create(job_payload)
                enrichment_job_ids.add(created_job.id)
                created_count += 1
            except DuplicateJobError:
                duplicate_count += 1
            except RepositoryError as exc:
                failed_count += 1
                logger.error(
                    "Failed to persist scraped Indeed job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                )
            except Exception as exc:
                failed_count += 1
                logger.error(
                    "Unexpected persistence error for scraped Indeed job",
                    external_id=external_id,
                    error=str(exc),
                    task_id=task_id,
                    exc_info=True,
                )

    result = {
        "status": "success",
        "platform": INDEED_PLATFORM,
        "query": query,
        "location": location,
        "scraped": len(scraped_jobs),
        "created": created_count,
        "updated": updated_count,
        "duplicates": duplicate_count,
        "failed": failed_count,
        "enrichment_job_ids": sorted(enrichment_job_ids),
    }
    logger.info("Completed Indeed scrape orchestration", task_id=task_id, result=result)
    return result


def _enqueue_enrichment_task(
    *,
    platform: str,
    job_ids: list[int],
    task_id: str | None,
) -> None:
    """Queue enrichment task for scraped jobs when ids are available.

    Args:
        platform: Source platform for enrichment context.
        job_ids: Job identifiers eligible for enrichment.
        task_id: Parent scraper task identifier.

    Returns:
        None.
    """
    unique_job_ids = sorted(
        {
            job_id
            for job_id in job_ids
            if isinstance(job_id, int) and not isinstance(job_id, bool) and job_id > 0
        }
    )
    if not unique_job_ids:
        return

    try:
        celery_app.send_task(
            ENRICHMENT_TASK_NAME,
            kwargs={"platform": platform, "job_ids": unique_job_ids},
            countdown=5,
        )
        logger.info(
            "Queued enrichment task for scraped jobs",
            platform=platform,
            job_ids_count=len(unique_job_ids),
            task_id=task_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to queue enrichment task after scrape",
            platform=platform,
            task_id=task_id,
            error=str(exc),
        )


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


def _load_search_profiles(
    *,
    config_path: Path,
    platform: str,
    max_limit: int,
) -> list[dict[str, Any]]:
    """Load active search profiles from JSON configuration.

    Args:
        config_path: JSON config path for profile definitions.
        platform: Platform label for logging and validation messaging.
        max_limit: Max scrape limit allowed per profile.

    Returns:
        Ordered list of validated active profile dictionaries.

    Raises:
        ValueError: If configuration file is missing or invalid.
    """
    platform_label = platform.capitalize()
    if not config_path.exists():
        raise ValueError(f"{platform_label} profile config not found: {config_path}")

    try:
        payload = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{platform_label} profile config is not valid JSON") from exc

    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError(
            f"{platform_label} profile config must include a 'profiles' array"
        )

    validated_profiles: list[dict[str, Any]] = []
    for index, profile in enumerate(profiles, start=1):
        if not isinstance(profile, dict):
            logger.warning(
                "Skipping non-object profile entry",
                index=index,
                platform=platform,
            )
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
                platform=platform,
            )
            continue

        try:
            limit = int(requested_limit)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid profile limit; defaulting to 5",
                index=index,
                requested_limit=requested_limit,
                platform=platform,
            )
            limit = 5

        if limit <= 0:
            logger.warning(
                "Invalid non-positive profile limit; defaulting to 5",
                index=index,
                requested_limit=requested_limit,
                platform=platform,
            )
            limit = 5

        bounded_limit = min(limit, max_limit)

        requested_priority = profile.get("priority", index)
        try:
            priority = int(requested_priority)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid profile priority; defaulting to profile order index",
                index=index,
                requested_priority=requested_priority,
                platform=platform,
            )
            priority = index

        if priority <= 0:
            logger.warning(
                "Invalid non-positive profile priority; defaulting to profile order index",
                index=index,
                requested_priority=requested_priority,
                platform=platform,
            )
            priority = index

        validated_profiles.append(
            {
                "id": str(profile.get("id", f"profile-{index}")),
                "query": query,
                "location": location,
                "limit": bounded_limit,
                "priority": priority,
            }
        )

    validated_profiles.sort(key=lambda profile: profile["priority"])
    return validated_profiles[:MAX_PROFILE_RUNS_PER_TASK]


def _load_linkedin_search_profiles() -> list[dict[str, Any]]:
    """Load active LinkedIn search profiles from JSON configuration."""
    return _load_search_profiles(
        config_path=LINKEDIN_PROFILE_CONFIG_PATH,
        platform=LINKEDIN_PLATFORM,
        max_limit=MAX_LINKEDIN_SCRAPE_LIMIT,
    )


def _load_seek_search_profiles() -> list[dict[str, Any]]:
    """Load active Seek search profiles from JSON configuration."""
    return _load_search_profiles(
        config_path=SEEK_PROFILE_CONFIG_PATH,
        platform=SEEK_PLATFORM,
        max_limit=MAX_SEEK_SCRAPE_LIMIT,
    )


def _load_indeed_search_profiles() -> list[dict[str, Any]]:
    """Load active Indeed search profiles from JSON configuration."""
    return _load_search_profiles(
        config_path=INDEED_PROFILE_CONFIG_PATH,
        platform=INDEED_PLATFORM,
        max_limit=MAX_INDEED_SCRAPE_LIMIT,
    )


def _is_transient_error(exc: BaseException) -> bool:
    """Check if an exception should trigger a retry.

    Args:
        exc: Exception raised during scrape execution.

    Returns:
        ``True`` when failure is transient and retryable.
    """
    transient_types: tuple[type[BaseException], ...] = (
        LinkedInTransientError,
        SeekTransientError,
        IndeedTransientError,
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
        SeekNonRetryableError,
        IndeedNonRetryableError,
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
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "LinkedIn profile set task skipped because scraper is disabled",
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": LINKEDIN_PLATFORM,
                "reason": "SCRAPER_ENABLED is false",
                "profiles_processed": 0,
            }

        profiles = _load_linkedin_search_profiles()
        if not profiles:
            run_status = "skipped"
            logger.warning(
                "No active LinkedIn profiles found in configuration",
                task_id=self.request.id,
                config_path=str(LINKEDIN_PROFILE_CONFIG_PATH),
            )
            return {
                "status": "skipped",
                "platform": LINKEDIN_PLATFORM,
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
        enrichment_job_ids: list[int] = []

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
            enrichment_job_ids.extend(
                [job_id for job_id in result.get("enrichment_job_ids", [])]
            )

        _record_scraper_result_metrics(
            platform=LINKEDIN_PLATFORM,
            scraped=totals["scraped"],
            created=totals["created"],
            duplicates=totals["duplicates"],
            failed=totals["failed"],
            updated=totals["updated"],
            jobs_in_database=(
                totals["created"] + totals["duplicates"] + totals["updated"]
            ),
            task_id=self.request.id,
        )

        run_status = "success"
        _enqueue_enrichment_task(
            platform=LINKEDIN_PLATFORM,
            job_ids=enrichment_job_ids,
            task_id=self.request.id,
        )
        return {
            "status": "success",
            "platform": LINKEDIN_PLATFORM,
            "profiles_processed": len(per_profile),
            "totals": totals,
            "profiles": per_profile,
            "enrichment_job_ids": sorted({job_id for job_id in enrichment_job_ids}),
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
    finally:
        _record_scraper_run_metrics(
            platform=LINKEDIN_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_seek_profile_set",
    bind=True,
    base=DatabaseTask,
)
def scrape_seek_profile_set(self: DatabaseTask) -> dict[str, Any]:
    """Run Seek scraping across configured role/location profiles.

    Returns:
        Aggregated scrape metrics for all processed profiles.
    """
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Seek profile set task skipped because scraper is disabled",
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": SEEK_PLATFORM,
                "reason": "SCRAPER_ENABLED is false",
                "profiles_processed": 0,
            }

        profiles = _load_seek_search_profiles()
        if not profiles:
            run_status = "skipped"
            logger.warning(
                "No active Seek profiles found in configuration",
                task_id=self.request.id,
                config_path=str(SEEK_PROFILE_CONFIG_PATH),
            )
            return {
                "status": "skipped",
                "platform": SEEK_PLATFORM,
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
        enrichment_job_ids: list[int] = []

        for profile in profiles:
            result = asyncio.run(
                _run_seek_scrape_and_persist(
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
            enrichment_job_ids.extend(
                [job_id for job_id in result.get("enrichment_job_ids", [])]
            )

        _record_scraper_result_metrics(
            platform=SEEK_PLATFORM,
            scraped=totals["scraped"],
            created=totals["created"],
            duplicates=totals["duplicates"],
            failed=totals["failed"],
            updated=totals["updated"],
            jobs_in_database=(
                totals["created"] + totals["duplicates"] + totals["updated"]
            ),
            task_id=self.request.id,
        )

        run_status = "success"
        _enqueue_enrichment_task(
            platform=SEEK_PLATFORM,
            job_ids=enrichment_job_ids,
            task_id=self.request.id,
        )
        return {
            "status": "success",
            "platform": SEEK_PLATFORM,
            "profiles_processed": len(per_profile),
            "totals": totals,
            "profiles": per_profile,
            "enrichment_job_ids": sorted({job_id for job_id in enrichment_job_ids}),
        }
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "Seek profile set task failed with non-retryable error",
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "Seek profile set task hit transient error, scheduling retry",
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCRAPER_TASK_RETRIES,
            )

        logger.error(
            "Seek profile set task failed with unexpected non-retryable error",
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scraper_run_metrics(
            platform=SEEK_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_indeed_profile_set",
    bind=True,
    base=DatabaseTask,
)
def scrape_indeed_profile_set(self: DatabaseTask) -> dict[str, Any]:
    """Run Indeed scraping across configured role/location profiles.

    Returns:
        Aggregated scrape metrics for all processed profiles.
    """
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Indeed profile set task skipped because scraper is disabled",
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": INDEED_PLATFORM,
                "reason": "SCRAPER_ENABLED is false",
                "profiles_processed": 0,
            }

        profiles = _load_indeed_search_profiles()
        if not profiles:
            run_status = "skipped"
            logger.warning(
                "No active Indeed profiles found in configuration",
                task_id=self.request.id,
                config_path=str(INDEED_PROFILE_CONFIG_PATH),
            )
            return {
                "status": "skipped",
                "platform": INDEED_PLATFORM,
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
        enrichment_job_ids: list[int] = []

        for profile in profiles:
            result = asyncio.run(
                _run_indeed_scrape_and_persist(
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
            enrichment_job_ids.extend(
                [job_id for job_id in result.get("enrichment_job_ids", [])]
            )

        _record_scraper_result_metrics(
            platform=INDEED_PLATFORM,
            scraped=totals["scraped"],
            created=totals["created"],
            duplicates=totals["duplicates"],
            failed=totals["failed"],
            updated=totals["updated"],
            jobs_in_database=(
                totals["created"] + totals["duplicates"] + totals["updated"]
            ),
            task_id=self.request.id,
        )

        run_status = "success"
        _enqueue_enrichment_task(
            platform=INDEED_PLATFORM,
            job_ids=enrichment_job_ids,
            task_id=self.request.id,
        )
        return {
            "status": "success",
            "platform": INDEED_PLATFORM,
            "profiles_processed": len(per_profile),
            "totals": totals,
            "profiles": per_profile,
            "enrichment_job_ids": sorted({job_id for job_id in enrichment_job_ids}),
        }
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "Indeed profile set task failed with non-retryable error",
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "Indeed profile set task hit transient error, scheduling retry",
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCRAPER_TASK_RETRIES,
            )

        logger.error(
            "Indeed profile set task failed with unexpected non-retryable error",
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scraper_run_metrics(
            platform=INDEED_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


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
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "LinkedIn scrape task skipped because scraper is disabled",
                query=query,
                location=location,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": LINKEDIN_PLATFORM,
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

        _record_scraper_result_metrics(
            platform=LINKEDIN_PLATFORM,
            scraped=int(result.get("scraped", 0)),
            created=int(result.get("created", 0)),
            duplicates=int(result.get("duplicates", 0)),
            failed=int(result.get("failed", 0)),
            updated=int(result.get("updated", 0)),
            jobs_in_database=(
                int(result.get("created", 0))
                + int(result.get("duplicates", 0))
                + int(result.get("updated", 0))
            ),
            task_id=self.request.id,
        )
        _enqueue_enrichment_task(
            platform=LINKEDIN_PLATFORM,
            job_ids=[job_id for job_id in result.get("enrichment_job_ids", [])],
            task_id=self.request.id,
        )
        run_status = "success"
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
    finally:
        _record_scraper_run_metrics(
            platform=LINKEDIN_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_seek_jobs",
    bind=True,
    base=DatabaseTask,
)
def scrape_seek_jobs(
    self: DatabaseTask,
    query: str,
    location: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Scrape Seek jobs and persist non-duplicate records."""
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Seek scrape task skipped because scraper is disabled",
                query=query,
                location=location,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": SEEK_PLATFORM,
                "query": query,
                "location": location,
                "reason": "SCRAPER_ENABLED is false",
            }

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        bounded_limit = min(limit, MAX_SEEK_SCRAPE_LIMIT)
        if bounded_limit != limit:
            logger.warning(
                "Seek scrape limit exceeded max, capping to safe value",
                requested_limit=limit,
                bounded_limit=bounded_limit,
                task_id=self.request.id,
            )

        result = asyncio.run(
            _run_seek_scrape_and_persist(
                query=query,
                location=location,
                limit=bounded_limit,
                task_id=self.request.id,
            )
        )

        _record_scraper_result_metrics(
            platform=SEEK_PLATFORM,
            scraped=int(result.get("scraped", 0)),
            created=int(result.get("created", 0)),
            duplicates=int(result.get("duplicates", 0)),
            failed=int(result.get("failed", 0)),
            updated=int(result.get("updated", 0)),
            jobs_in_database=(
                int(result.get("created", 0))
                + int(result.get("duplicates", 0))
                + int(result.get("updated", 0))
            ),
            task_id=self.request.id,
        )
        _enqueue_enrichment_task(
            platform=SEEK_PLATFORM,
            job_ids=[job_id for job_id in result.get("enrichment_job_ids", [])],
            task_id=self.request.id,
        )
        run_status = "success"
        return result
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "Seek scrape task failed with non-retryable error",
                query=query,
                location=location,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "Seek scrape task hit transient error, scheduling retry",
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
            "Seek scrape task failed with unexpected non-retryable error",
            query=query,
            location=location,
            limit=limit,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scraper_run_metrics(
            platform=SEEK_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.scraper_tasks.scrape_indeed_jobs",
    bind=True,
    base=DatabaseTask,
)
def scrape_indeed_jobs(
    self: DatabaseTask,
    query: str,
    location: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Scrape Indeed jobs and persist non-duplicate records."""
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Indeed scrape task skipped because scraper is disabled",
                query=query,
                location=location,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": INDEED_PLATFORM,
                "query": query,
                "location": location,
                "reason": "SCRAPER_ENABLED is false",
            }

        if limit <= 0:
            raise ValueError("limit must be greater than 0")

        bounded_limit = min(limit, MAX_INDEED_SCRAPE_LIMIT)
        if bounded_limit != limit:
            logger.warning(
                "Indeed scrape limit exceeded max, capping to safe value",
                requested_limit=limit,
                bounded_limit=bounded_limit,
                task_id=self.request.id,
            )

        result = asyncio.run(
            _run_indeed_scrape_and_persist(
                query=query,
                location=location,
                limit=bounded_limit,
                task_id=self.request.id,
            )
        )

        _record_scraper_result_metrics(
            platform=INDEED_PLATFORM,
            scraped=int(result.get("scraped", 0)),
            created=int(result.get("created", 0)),
            duplicates=int(result.get("duplicates", 0)),
            failed=int(result.get("failed", 0)),
            updated=int(result.get("updated", 0)),
            jobs_in_database=(
                int(result.get("created", 0))
                + int(result.get("duplicates", 0))
                + int(result.get("updated", 0))
            ),
            task_id=self.request.id,
        )
        _enqueue_enrichment_task(
            platform=INDEED_PLATFORM,
            job_ids=[job_id for job_id in result.get("enrichment_job_ids", [])],
            task_id=self.request.id,
        )
        run_status = "success"
        return result
    except Exception as exc:
        if _is_non_retryable_error(exc):
            logger.error(
                "Indeed scrape task failed with non-retryable error",
                query=query,
                location=location,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        if _is_transient_error(exc):
            logger.warning(
                "Indeed scrape task hit transient error, scheduling retry",
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
            "Indeed scrape task failed with unexpected non-retryable error",
            query=query,
            location=location,
            limit=limit,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scraper_run_metrics(
            platform=INDEED_PLATFORM,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )
