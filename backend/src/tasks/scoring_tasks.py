"""Celery tasks for automated job scoring workflows."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from celery import Task
from loguru import logger

from src.core.config import settings
from src.core.exceptions import RepositoryError
from src.core.metrics import (
    increment_jobs_scored,
    increment_scoring_errors,
    increment_scoring_runs,
    observe_scoring_duration,
)
from src.celery_app import celery_app
from src.db.session import get_session
from src.repositories.job import JobRepository
from src.repositories.job_enrichment import JobEnrichmentRepository
from src.repositories.match_score import MatchScoreRepository
from src.repositories.profile import ProfileRepository
from src.services.match_service import MatchService

MAX_SCORING_TASK_RETRIES = 3
DEFAULT_RETRY_COUNTDOWN_SECONDS = 60
LINKEDIN_PLATFORM = "linkedin"


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
    """Determine whether task failure should trigger retry.

    Args:
        exc: Exception raised during scoring execution.

    Returns:
        ``True`` when the error chain contains retryable infra failures.
    """
    transient_types: tuple[type[BaseException], ...] = (
        RepositoryError,
        ConnectionError,
        OSError,
        asyncio.TimeoutError,
    )
    return any(isinstance(item, transient_types) for item in _exception_chain(exc))


def _record_scoring_run_metrics(
    platform: str,
    status: str,
    duration_seconds: float,
    task_id: str | None,
) -> None:
    """Record scoring run metrics with validation safeguards.

    Args:
        platform: Scoring source platform label.
        status: Task run status.
        duration_seconds: Runtime duration in seconds.
        task_id: Optional Celery task identifier.

    Returns:
        None.
    """
    try:
        increment_scoring_runs(platform=platform, status=status)
        observe_scoring_duration(platform=platform, duration_seconds=duration_seconds)
    except ValueError as exc:
        logger.warning(
            "Skipped scoring run metrics due to invalid values",
            platform=platform,
            status=status,
            duration_seconds=duration_seconds,
            task_id=task_id,
            error=str(exc),
        )


def _record_scoring_result_metrics(
    platform: str,
    *,
    scored: int = 0,
    failed: int = 0,
    task_id: str | None,
) -> None:
    """Record scoring output counters with validation safeguards.

    Args:
        platform: Scoring source platform label.
        scored: Number of jobs scored in task execution.
        failed: Number of scoring failures in task execution.
        task_id: Optional Celery task identifier.

    Returns:
        None.
    """
    try:
        increment_jobs_scored(platform=platform, count=max(scored, 0))
        increment_scoring_errors(platform=platform, count=max(failed, 0))
    except ValueError as exc:
        logger.warning(
            "Skipped scoring result metrics due to invalid values",
            platform=platform,
            scored=scored,
            failed=failed,
            task_id=task_id,
            error=str(exc),
        )


async def _run_score_all_unscored_jobs(
    platform: str,
    task_id: str | None,
) -> dict[str, Any]:
    """Resolve dependencies and score all currently unscored jobs.

    Args:
        platform: Source platform label.
        task_id: Optional Celery task id for logs.

    Returns:
        Structured summary payload for the batch scoring run.
    """
    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        profile_repository = ProfileRepository(db_session)
        match_score_repository = MatchScoreRepository(db_session)
        enrichment_repository = JobEnrichmentRepository(db_session)
        match_service = MatchService(
            job_repo=job_repository,
            profile_repo=profile_repository,
            match_repo=match_score_repository,
            enrichment_repo=enrichment_repository,
        )

        profile = await profile_repository.get_first()
        if profile is None:
            logger.warning(
                "Scoring task skipped because no profile was found",
                platform=platform,
                task_id=task_id,
            )
            return {
                "status": "skipped",
                "platform": platform,
                "profile_id": None,
                "scored": 0,
                "failed": 0,
                "total": 0,
                "reason": "no_profile",
            }

        logger.info(
            "Scoring all unscored jobs",
            platform=platform,
            profile_id=profile.id,
            task_id=task_id,
            progress="started",
        )
        scored = await match_service.score_all_unscored_jobs(profile_id=profile.id)
        failed = 0
        total = scored + failed
        result = {
            "status": "success",
            "platform": platform,
            "profile_id": profile.id,
            "scored": scored,
            "failed": failed,
            "total": total,
        }
        logger.info(
            "Completed scoring all unscored jobs",
            platform=platform,
            profile_id=profile.id,
            task_id=task_id,
            progress="completed",
            result=result,
        )
        return result


async def _run_score_single_job(
    job_id: int,
    profile_id: int | None,
    platform: str,
    task_id: str | None,
) -> dict[str, Any]:
    """Resolve dependencies and score one job.

    Args:
        job_id: Job identifier to score.
        profile_id: Optional profile identifier.
        platform: Source platform label for metrics/logging.
        task_id: Optional Celery task id for logs.

    Returns:
        Structured single job scoring result payload.

    Raises:
        ValueError: If no profile can be resolved.
    """
    async with get_session() as db_session:
        job_repository = JobRepository(db_session)
        profile_repository = ProfileRepository(db_session)
        match_score_repository = MatchScoreRepository(db_session)
        enrichment_repository = JobEnrichmentRepository(db_session)
        match_service = MatchService(
            job_repo=job_repository,
            profile_repo=profile_repository,
            match_repo=match_score_repository,
            enrichment_repo=enrichment_repository,
        )

        resolved_profile_id = profile_id
        if resolved_profile_id is None:
            profile = await profile_repository.get_first()
            if profile is None:
                logger.warning(
                    "Single job scoring skipped because no profile was found",
                    platform=platform,
                    job_id=job_id,
                    task_id=task_id,
                )
                return {
                    "status": "skipped",
                    "platform": platform,
                    "job_id": job_id,
                    "profile_id": None,
                    "reason": "no_profile",
                }
            resolved_profile_id = profile.id

        logger.info(
            "Scoring single job",
            platform=platform,
            job_id=job_id,
            profile_id=resolved_profile_id,
            task_id=task_id,
            progress="started",
        )
        score = await match_service.score_job(
            job_id=job_id,
            profile_id=resolved_profile_id,
        )
        payload = score.model_dump(mode="json")
        logger.info(
            "Completed single job scoring",
            platform=platform,
            job_id=job_id,
            profile_id=resolved_profile_id,
            task_id=task_id,
            progress="completed",
        )
        return {
            "status": "success",
            "platform": platform,
            "job_id": job_id,
            "profile_id": resolved_profile_id,
            "score": payload,
        }


@celery_app.task(
    name="src.tasks.scoring_tasks.score_all_unscored_jobs_task",
    bind=True,
)
def score_all_unscored_jobs_task(
    self: Task,
    platform: str = LINKEDIN_PLATFORM,
) -> dict[str, Any]:
    """Score all unscored jobs for the first available profile.

    Args:
        platform: Source platform label for metrics and logs.

    Returns:
        Structured batch scoring summary payload.

    Raises:
        Exception: Re-raises non-retryable errors and retry exceptions.
    """
    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Scoring task skipped because scraper is disabled",
                platform=platform,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": platform,
                "profile_id": None,
                "scored": 0,
                "failed": 0,
                "total": 0,
                "reason": "SCRAPER_ENABLED is false",
            }

        result = asyncio.run(
            _run_score_all_unscored_jobs(
                platform=platform,
                task_id=self.request.id,
            )
        )
        run_status = str(result.get("status", "success"))
        _record_scoring_result_metrics(
            platform=platform,
            scored=int(result.get("scored", 0)),
            failed=int(result.get("failed", 0)),
            task_id=self.request.id,
        )
        return result
    except Exception as exc:
        _record_scoring_result_metrics(
            platform=platform,
            scored=0,
            failed=1,
            task_id=self.request.id,
        )
        if _is_transient_error(exc):
            logger.warning(
                "Scoring task hit transient error, scheduling retry",
                platform=platform,
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCORING_TASK_RETRIES,
            )

        logger.error(
            "Scoring task failed with non-retryable error",
            platform=platform,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scoring_run_metrics(
            platform=platform,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


@celery_app.task(
    name="src.tasks.scoring_tasks.score_single_job_task",
    bind=True,
)
def score_single_job_task(
    self: Task,
    job_id: int,
    profile_id: int | None = None,
    platform: str = LINKEDIN_PLATFORM,
) -> dict[str, Any]:
    """Score one job for a profile or fallback to the first profile.

    Args:
        job_id: Job identifier to score.
        profile_id: Optional profile identifier.
        platform: Source platform label for metrics and logs.

    Returns:
        Structured single-job scoring result payload.

    Raises:
        ValueError: If ``job_id`` is invalid.
        Exception: Re-raises non-retryable errors and retry exceptions.
    """
    if job_id <= 0:
        raise ValueError("job_id must be greater than 0")

    started_at = time.perf_counter()
    run_status = "failure"
    try:
        if not settings.SCRAPER_ENABLED:
            run_status = "skipped"
            logger.warning(
                "Single job scoring task skipped because scraper is disabled",
                platform=platform,
                job_id=job_id,
                profile_id=profile_id,
                task_id=self.request.id,
            )
            return {
                "status": "skipped",
                "platform": platform,
                "job_id": job_id,
                "profile_id": profile_id,
                "reason": "SCRAPER_ENABLED is false",
            }

        result = asyncio.run(
            _run_score_single_job(
                job_id=job_id,
                profile_id=profile_id,
                platform=platform,
                task_id=self.request.id,
            )
        )
        run_status = str(result.get("status", "success"))
        _record_scoring_result_metrics(
            platform=platform,
            scored=1 if result.get("status") == "success" else 0,
            failed=0,
            task_id=self.request.id,
        )
        return result
    except Exception as exc:
        _record_scoring_result_metrics(
            platform=platform,
            scored=0,
            failed=1,
            task_id=self.request.id,
        )
        if _is_transient_error(exc):
            logger.warning(
                "Single job scoring task hit transient error, scheduling retry",
                platform=platform,
                job_id=job_id,
                profile_id=profile_id,
                task_id=self.request.id,
                error=str(exc),
            )
            raise self.retry(
                exc=exc,
                countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
                max_retries=MAX_SCORING_TASK_RETRIES,
            )

        logger.error(
            "Single job scoring failed with non-retryable error",
            platform=platform,
            job_id=job_id,
            profile_id=profile_id,
            task_id=self.request.id,
            error=str(exc),
            exc_info=True,
        )
        raise
    finally:
        _record_scoring_run_metrics(
            platform=platform,
            status=run_status,
            duration_seconds=time.perf_counter() - started_at,
            task_id=self.request.id,
        )


__all__ = [
    "score_all_unscored_jobs_task",
    "score_single_job_task",
]
