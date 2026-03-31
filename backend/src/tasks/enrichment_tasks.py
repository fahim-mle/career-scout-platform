"""Celery tasks for job enrichment workflows."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from celery import Task
from loguru import logger

from src.core.config import settings
from src.core.exceptions import BusinessLogicError, RepositoryError
from src.core.metrics import (
    increment_enrichment_errors,
    increment_enrichment_runs,
    increment_jobs_enriched,
    observe_enrichment_duration,
)
from src.celery_app import celery_app
from src.db.session import get_session, run_with_cleanup
from src.repositories.job import JobRepository
from src.repositories.job_enrichment import JobEnrichmentRepository
from src.services.job_enrichment_service import JobEnrichmentService

MAX_ENRICHMENT_TASK_RETRIES = 3
DEFAULT_RETRY_COUNTDOWN_SECONDS = 60
DEFAULT_ENRICHMENT_LIMIT = 200
LINKEDIN_PLATFORM = "linkedin"
SCORING_TASK_NAME = "src.tasks.scoring_tasks.score_all_unscored_jobs_task"


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """Collect linked exception causes and contexts.

    Args:
        exc: Top-level exception to inspect.

    Returns:
        Ordered list of exception chain elements.
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
    """Determine whether the error should trigger retry.

    Args:
        exc: Exception raised during enrichment execution.

    Returns:
        ``True`` when the error chain contains retryable infrastructure failures.
    """
    transient_types: tuple[type[BaseException], ...] = (
        RepositoryError,
        ConnectionError,
        OSError,
        asyncio.TimeoutError,
    )
    return any(isinstance(item, transient_types) for item in _exception_chain(exc))


def _is_non_retryable_error(exc: BaseException) -> bool:
    """Determine whether the error should never trigger retry.

    Args:
        exc: Exception raised during enrichment execution.

    Returns:
        ``True`` when the error chain contains non-retryable validation/logic failures.
    """
    non_retryable_types: tuple[type[BaseException], ...] = (
        ValueError,
        BusinessLogicError,
    )
    return any(isinstance(item, non_retryable_types) for item in _exception_chain(exc))


def _record_enrichment_run_metrics(
    platform: str,
    status: str,
    duration_seconds: float,
    task_id: str | None,
) -> None:
    """Record enrichment run metrics with validation safeguards.

    Args:
        platform: Enrichment source platform label.
        status: Task run status.
        duration_seconds: Runtime duration in seconds.
        task_id: Optional Celery task identifier.

    Returns:
        None.
    """
    try:
        increment_enrichment_runs(platform=platform, status=status)
        observe_enrichment_duration(
            platform=platform, duration_seconds=duration_seconds
        )
    except ValueError as exc:
        logger.warning(
            "Skipped enrichment run metrics due to invalid values",
            platform=platform,
            status=status,
            duration_seconds=duration_seconds,
            task_id=task_id,
            error=str(exc),
        )


def _record_enrichment_result_metrics(
    platform: str,
    *,
    enriched: int = 0,
    failed: int = 0,
    task_id: str | None,
) -> None:
    """Record enrichment result counters with validation safeguards.

    Args:
        platform: Enrichment source platform label.
        enriched: Number of jobs enriched in task execution.
        failed: Number of failed enrichments in task execution.
        task_id: Optional Celery task identifier.

    Returns:
        None.
    """
    try:
        increment_jobs_enriched(platform=platform, count=max(enriched, 0))
        increment_enrichment_errors(platform=platform, count=max(failed, 0))
    except ValueError as exc:
        logger.warning(
            "Skipped enrichment result metrics due to invalid values",
            platform=platform,
            enriched=enriched,
            failed=failed,
            task_id=task_id,
            error=str(exc),
        )


def _enqueue_scoring_task(platform: str, task_id: str | None) -> None:
    """Queue scoring task after successful enrichment.

    Args:
        platform: Source platform label for scoring context.
        task_id: Optional parent Celery task identifier.

    Returns:
        None.
    """
    try:
        celery_app.send_task(
            SCORING_TASK_NAME,
            kwargs={"platform": platform},
            countdown=5,
        )
        logger.info(
            "Queued scoring task after enrichment",
            platform=platform,
            task_id=task_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to queue scoring task after enrichment",
            platform=platform,
            task_id=task_id,
            error=str(exc),
        )


async def _run_batch_enrichment(
    platform: str,
    limit: int,
    job_ids: list[int] | None,
    task_id: str | None,
) -> dict[str, Any]:
    """Execute enrichment with repository/service dependencies.

    Args:
        platform: Source platform label used for batch mode filtering.
        limit: Maximum jobs to process in batch mode.
        job_ids: Optional explicit job IDs to enrich.
        task_id: Optional Celery task identifier.

    Returns:
        Structured enrichment task result payload.

    Raises:
        ValueError: If input validation fails.
        BusinessLogicError: If service-level validation or processing fails.
    """
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    if job_ids is not None:
        if not isinstance(job_ids, list):
            raise ValueError("job_ids must be a list of positive integers")
        if any(
            not isinstance(job_id, int) or isinstance(job_id, bool) or job_id <= 0
            for job_id in job_ids
        ):
            raise ValueError("job_ids must be a list of positive integers")

    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        enrichment_repository = JobEnrichmentRepository(db_session)
        enrichment_service = JobEnrichmentService(
            job_repo=job_repository,
            enrichment_repo=enrichment_repository,
        )

        if job_ids is not None:
            enriched = 0
            missing = 0
            failed = 0
            unique_job_ids = list(dict.fromkeys(job_ids))
            for job_id in unique_job_ids:
                try:
                    enrichment = await enrichment_service.enrich_job(job_id=job_id)
                    if enrichment is None:
                        missing += 1
                    else:
                        enriched += 1
                except Exception as exc:
                    failed += 1
                    logger.error(
                        "Failed enriching job in job_ids mode",
                        task_id=task_id,
                        job_id=job_id,
                        error=str(exc),
                        exc_info=True,
                    )

            result = {
                "status": "success",
                "platform": platform,
                "mode": "job_ids",
                "job_ids": unique_job_ids,
                "processed": len(unique_job_ids),
                "enriched": enriched,
                "missing": missing,
                "failed": failed,
            }
            logger.info(
                "Completed enrichment task in job_ids mode",
                task_id=task_id,
                result=result,
            )
            return result

        summary = await enrichment_service.enrich_jobs_with_missing_skills(
            limit=limit,
            platform=platform,
        )
        result = {
            "status": "success",
            "platform": platform,
            "mode": "batch",
            **summary,
        }
        logger.info(
            "Completed enrichment task in batch mode",
            task_id=task_id,
            result=result,
        )
        return result


@celery_app.task(
    name="src.tasks.enrichment_tasks.enrich_unstructured_jobs_task",
    bind=True,
)
def enrich_unstructured_jobs_task(
    self: Task,
    platform: str = LINKEDIN_PLATFORM,
    limit: int = DEFAULT_ENRICHMENT_LIMIT,
    job_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Enrich a batch of jobs using explicit IDs or repository query mode.

    Args:
        platform: Source platform filter for batch mode.
        limit: Maximum rows to process in batch mode.
        job_ids: Optional explicit list of job IDs to enrich.

    Returns:
        Structured enrichment summary.

    Raises:
        ValueError: If validation fails.
        Exception: Re-raises unexpected errors or retry exceptions.
    """
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Enrichment task skipped because scraper is disabled",
                platform=platform,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": platform,
                "reason": "SCRAPER_ENABLED is false",
            }

        logger.info(
            "Starting enrichment task",
            platform=platform,
            limit=limit,
            job_ids_count=0 if job_ids is None else len(job_ids),
            task_id=self.request.id,
        )

        result = run_with_cleanup(
            _run_batch_enrichment(
                platform=platform,
                limit=limit,
                job_ids=job_ids,
                task_id=self.request.id,
            )
        )

        _record_enrichment_result_metrics(
            platform=platform,
            enriched=int(result.get("enriched", 0)),
            failed=int(result.get("failed", 0)),
            task_id=self.request.id,
        )

        if int(result.get("enriched", 0)) > 0:
            _enqueue_scoring_task(platform=platform, task_id=self.request.id)

        run_status = "success"
        return result
    except Exception as exc:
        _record_enrichment_result_metrics(
            platform=platform,
            enriched=0,
            failed=1,
            task_id=self.request.id,
        )

        if _is_transient_error(exc):
            logger.warning(
                "Enrichment task hit transient error, scheduling retry",
                platform=platform,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_ENRICHMENT_TASK_RETRIES,
            )

        if _is_non_retryable_error(exc):
            logger.error(
                "Enrichment task failed with non-retryable error",
                platform=platform,
                limit=limit,
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        logger.error(
            "Enrichment task failed with unexpected non-retryable error",
            platform=platform,
            limit=limit,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_enrichment_run_metrics(
            platform=platform,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.enrichment_tasks.enrich_single_job_task",
    bind=True,
)
def enrich_single_job_task(
    self: Task,
    job_id: int,
    platform: str = LINKEDIN_PLATFORM,
) -> dict[str, Any]:
    """Enrich a single job by identifier.

    Args:
        job_id: Raw job id to enrich.
        platform: Source platform metric label.

    Returns:
        Structured single-job enrichment result.

    Raises:
        ValueError: If validation fails.
        Exception: Re-raises unexpected errors or retry exceptions.
    """
    if job_id <= 0:
        raise ValueError("job_id must be greater than 0")

    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Single job enrichment task skipped because scraper is disabled",
                job_id=job_id,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": platform,
                "job_id": job_id,
                "reason": "SCRAPER_ENABLED is false",
            }

        async def _run_single() -> dict[str, Any]:
            async with get_session() as db_session:
                job_repository = JobRepository(db_session)
                enrichment_repository = JobEnrichmentRepository(db_session)
                enrichment_service = JobEnrichmentService(
                    job_repo=job_repository,
                    enrichment_repo=enrichment_repository,
                )
                enrichment = await enrichment_service.enrich_job(job_id=job_id)
                return {
                    "status": "success",
                    "platform": platform,
                    "job_id": job_id,
                    "enriched": 1 if enrichment is not None else 0,
                    "missing": 0 if enrichment is not None else 1,
                    "failed": 0,
                }

        result = run_with_cleanup(_run_single())

        _record_enrichment_result_metrics(
            platform=platform,
            enriched=int(result.get("enriched", 0)),
            failed=0,
            task_id=self.request.id,
        )

        if int(result.get("enriched", 0)) > 0:
            _enqueue_scoring_task(platform=platform, task_id=self.request.id)

        run_status = "success"
        return result
    except Exception as exc:
        _record_enrichment_result_metrics(
            platform=platform,
            enriched=0,
            failed=1,
            task_id=self.request.id,
        )

        if _is_transient_error(exc):
            logger.warning(
                "Single job enrichment task hit transient error, scheduling retry",
                job_id=job_id,
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_ENRICHMENT_TASK_RETRIES,
            )

        if _is_non_retryable_error(exc):
            logger.error(
                "Single job enrichment failed with non-retryable error",
                job_id=job_id,
                task_id=self.request.id,
                error=str(exc),
            )
            raise

        logger.error(
            "Single job enrichment failed with unexpected non-retryable error",
            job_id=job_id,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_enrichment_run_metrics(
            platform=platform,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


__all__ = [
    "enrich_single_job_task",
    "enrich_unstructured_jobs_task",
]
