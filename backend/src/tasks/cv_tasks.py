"""Celery tasks for CV summarisation via LLM."""

from __future__ import annotations

import asyncio

from celery import Task
from loguru import logger

from src.celery_app import celery_app
from src.db.session import get_session
from src.repositories.profile import ProfileRepository

MAX_CV_TASK_RETRIES = 3
DEFAULT_RETRY_COUNTDOWN_SECONDS = 30


async def _run_cv_summarisation(profile_id: int, raw_text: str) -> None:
    """Run LLM summarisation and persist result.

    Args:
        profile_id: ID of the profile to update.
        raw_text: Raw CV text to summarise.
    """
    from src.ai.cv_parser import parse_cv_with_llm
    from src.ai.llm_client import get_llm_client

    llm_client = get_llm_client()
    try:
        summary = await parse_cv_with_llm(raw_text, llm_client)
    finally:
        if hasattr(llm_client, "aclose"):
            await llm_client.aclose()

    async with get_session() as db_session:
        repo = ProfileRepository(db_session)
        await repo.update(profile_id, {"resume_text": summary})

    logger.bind(profile_id=profile_id).info("CV summarisation persisted")


@celery_app.task(
    name="src.tasks.cv_tasks.summarise_cv_task",
    bind=True,
)
def summarise_cv_task(
    self: Task,
    profile_id: int,
    raw_text: str,
) -> dict[str, object]:
    """Summarise raw CV text with LLM and update profile resume_text.

    Args:
        profile_id: ID of the profile to update.
        raw_text: Plain text extracted from the uploaded CV file.

    Returns:
        Result payload with status and profile_id.

    Raises:
        Exception: Re-raises unexpected errors or retry exceptions.
    """
    log = logger.bind(profile_id=profile_id, task_id=self.request.id)
    log.info("Starting CV summarisation task")

    try:
        asyncio.run(_run_cv_summarisation(profile_id, raw_text))
        log.info("CV summarisation task completed")
        return {"status": "success", "profile_id": profile_id}
    except Exception as exc:
        log.bind(error=str(exc)).error(
            "CV summarisation task failed", exc_info=True
        )
        raise self.retry(
            exc=exc,
            countdown=DEFAULT_RETRY_COUNTDOWN_SECONDS,
            max_retries=MAX_CV_TASK_RETRIES,
        )


__all__ = ["summarise_cv_task"]
