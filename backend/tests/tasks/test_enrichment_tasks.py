"""Unit tests for enrichment task retry and control flow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.core.exceptions import RepositoryError
from src.tasks import enrichment_tasks


class RetryInvoked(Exception):
    """Sentinel exception raised when fake retry is invoked."""


class FakeBoundTask:
    """Minimal bound-task double implementing request and retry."""

    def __init__(self) -> None:
        self.request = SimpleNamespace(id="task-123")
        self.retry_calls: list[dict[str, Any]] = []

    def retry(self, **kwargs: Any) -> None:
        """Record retry payload and raise sentinel exception.

        Args:
            **kwargs: Celery retry parameters.

        Raises:
            RetryInvoked: Always raised to emulate Celery retry control flow.
        """
        self.retry_calls.append(kwargs)
        raise RetryInvoked("retry called")


ENRICH_BATCH_TASK_RUN = enrichment_tasks.enrich_unstructured_jobs_task.run.__func__  # type: ignore[attr-defined]


def test_enrich_unstructured_jobs_skips_when_scraper_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns skipped status when scraper kill switch is disabled."""
    task = FakeBoundTask()
    monkeypatch.setattr(enrichment_tasks.settings, "SCRAPER_ENABLED", False)

    result = ENRICH_BATCH_TASK_RUN(task, platform="linkedin", limit=5, job_ids=None)

    assert result["status"] == "skipped"
    assert result["reason"] == "SCRAPER_ENABLED is false"
    assert task.retry_calls == []


def test_enrich_unstructured_jobs_success_for_explicit_job_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns successful payload for explicit job_ids mode."""
    task = FakeBoundTask()
    monkeypatch.setattr(enrichment_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_run_batch_enrichment(
        platform: str,
        limit: int,
        job_ids: list[int] | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        assert platform == "linkedin"
        assert limit == 10
        assert job_ids == [101, 202]
        assert task_id == "task-123"
        return {
            "status": "success",
            "platform": "linkedin",
            "mode": "job_ids",
            "processed": 2,
            "enriched": 2,
            "failed": 0,
        }

    monkeypatch.setattr(
        enrichment_tasks,
        "_run_batch_enrichment",
        fake_run_batch_enrichment,
    )

    result = ENRICH_BATCH_TASK_RUN(
        task,
        platform="linkedin",
        limit=10,
        job_ids=[101, 202],
    )

    assert result["status"] == "success"
    assert result["mode"] == "job_ids"
    assert result["enriched"] == 2
    assert task.retry_calls == []


def test_enrich_unstructured_jobs_retries_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient repository failures trigger Celery retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(enrichment_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_transient_error(
        platform: str,
        limit: int,
        job_ids: list[int] | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        del platform, limit, job_ids, task_id
        raise RepositoryError("database timeout")

    monkeypatch.setattr(
        enrichment_tasks,
        "_run_batch_enrichment",
        raise_transient_error,
    )

    with pytest.raises(RetryInvoked, match="retry called"):
        ENRICH_BATCH_TASK_RUN(task, platform="linkedin", limit=10, job_ids=[5])

    assert len(task.retry_calls) == 1
    retry_payload = task.retry_calls[0]
    assert (
        retry_payload["countdown"] == enrichment_tasks.DEFAULT_RETRY_COUNTDOWN_SECONDS
    )
    assert retry_payload["max_retries"] == enrichment_tasks.MAX_ENRICHMENT_TASK_RETRIES
    assert isinstance(retry_payload["exc"], RepositoryError)


def test_enrich_unstructured_jobs_does_not_retry_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation failures raise directly without triggering retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(enrichment_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_non_retryable(
        platform: str,
        limit: int,
        job_ids: list[int] | None,
        task_id: str | None,
    ) -> dict[str, Any]:
        del platform, limit, job_ids, task_id
        raise ValueError("job_ids must be a list of positive integers")

    monkeypatch.setattr(
        enrichment_tasks,
        "_run_batch_enrichment",
        raise_non_retryable,
    )

    with pytest.raises(ValueError, match="job_ids must be a list"):
        ENRICH_BATCH_TASK_RUN(task, platform="linkedin", limit=10, job_ids=[1])

    assert task.retry_calls == []
