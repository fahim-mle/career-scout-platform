"""Unit tests for enrichment task retry and control flow."""

from __future__ import annotations

import asyncio
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


def test_run_batch_enrichment_rejects_bool_job_id_values() -> None:
    """Validation rejects bool values in job_ids while preserving message."""
    with pytest.raises(ValueError, match="job_ids must be a list of positive integers"):
        asyncio.run(
            enrichment_tasks._run_batch_enrichment(
                platform="linkedin",
                limit=5,
                job_ids=[True, 2],
                task_id="task-123",
            )
        )


def test_run_batch_enrichment_continues_when_single_job_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """job_ids mode continues and counts failures per job when one enrich call errors."""

    class DummyAsyncSession:
        pass

    class DummySessionContext:
        async def __aenter__(self) -> DummyAsyncSession:
            return DummyAsyncSession()

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            del exc_type, exc, tb

    class FakeJobRepository:
        def __init__(self, db_session: DummyAsyncSession) -> None:
            self.db_session = db_session

    class FakeJobEnrichmentRepository:
        def __init__(self, db_session: DummyAsyncSession) -> None:
            self.db_session = db_session

    class FakeJobEnrichmentService:
        def __init__(self, job_repo: Any, enrichment_repo: Any) -> None:
            self.job_repo = job_repo
            self.enrichment_repo = enrichment_repo

        async def enrich_job(self, job_id: int) -> Any:
            if job_id == 1:
                return {"id": 1}
            if job_id == 2:
                return None
            raise RuntimeError("enrichment crash")

    errors: list[dict[str, Any]] = []

    def fake_error(message: str, **kwargs: Any) -> None:
        errors.append({"message": message, **kwargs})

    fake_logger = SimpleNamespace(info=lambda *_args, **_kwargs: None, error=fake_error)

    monkeypatch.setattr(enrichment_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(enrichment_tasks, "JobRepository", FakeJobRepository)
    monkeypatch.setattr(
        enrichment_tasks,
        "JobEnrichmentRepository",
        FakeJobEnrichmentRepository,
    )
    monkeypatch.setattr(
        enrichment_tasks, "JobEnrichmentService", FakeJobEnrichmentService
    )
    monkeypatch.setattr(enrichment_tasks, "logger", fake_logger)

    result = asyncio.run(
        enrichment_tasks._run_batch_enrichment(
            platform="linkedin",
            limit=5,
            job_ids=[1, 2, 3],
            task_id="task-123",
        )
    )

    assert result["status"] == "success"
    assert result["mode"] == "job_ids"
    assert result["processed"] == 3
    assert result["enriched"] == 1
    assert result["missing"] == 1
    assert result["failed"] == 1
    assert len(errors) == 1
    assert errors[0]["task_id"] == "task-123"
    assert errors[0]["job_id"] == 3
