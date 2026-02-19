"""Unit tests for scoring task orchestration and retry behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.exceptions import RepositoryError
from src.tasks import scoring_tasks


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


SCORE_ALL_TASK_RUN = scoring_tasks.score_all_unscored_jobs_task.run.__func__  # type: ignore[attr-defined]
SCORE_SINGLE_TASK_RUN = scoring_tasks.score_single_job_task.run.__func__  # type: ignore[attr-defined]


def test_score_all_unscored_jobs_skips_when_scraper_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns skipped status when scraper kill switch is disabled."""
    task = FakeBoundTask()
    monkeypatch.setattr(scoring_tasks.settings, "SCRAPER_ENABLED", False)

    result = SCORE_ALL_TASK_RUN(task, platform="linkedin")

    assert result["status"] == "skipped"
    assert result["reason"] == "SCRAPER_ENABLED is false"
    assert task.retry_calls == []


def test_score_all_unscored_jobs_skips_when_no_profile_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns skipped/no_profile when no profile exists."""
    task = FakeBoundTask()
    monkeypatch.setattr(scoring_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_run(
        platform: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        assert platform == "linkedin"
        assert task_id == "task-123"
        return {
            "status": "skipped",
            "platform": "linkedin",
            "profile_id": None,
            "scored": 0,
            "failed": 0,
            "total": 0,
            "reason": "no_profile",
        }

    monkeypatch.setattr(scoring_tasks, "_run_score_all_unscored_jobs", fake_run)

    result = SCORE_ALL_TASK_RUN(task, platform="linkedin")

    assert result["status"] == "skipped"
    assert result["reason"] == "no_profile"
    assert task.retry_calls == []


def test_score_all_unscored_jobs_success_returns_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns structured success payload with scoring counts."""
    task = FakeBoundTask()
    monkeypatch.setattr(scoring_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_run(
        platform: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        assert platform == "linkedin"
        assert task_id == "task-123"
        return {
            "status": "success",
            "platform": "linkedin",
            "profile_id": 7,
            "scored": 3,
            "failed": 1,
            "total": 4,
        }

    monkeypatch.setattr(scoring_tasks, "_run_score_all_unscored_jobs", fake_run)

    result = SCORE_ALL_TASK_RUN(task, platform="linkedin")

    assert result["status"] == "success"
    assert result["scored"] == 3
    assert result["failed"] == 1
    assert result["total"] == 4
    assert task.retry_calls == []


def test_score_all_unscored_jobs_retries_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient repository failures trigger Celery retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scoring_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_transient(
        platform: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        del platform, task_id
        raise RepositoryError("database timeout")

    monkeypatch.setattr(scoring_tasks, "_run_score_all_unscored_jobs", raise_transient)

    with pytest.raises(RetryInvoked, match="retry called"):
        SCORE_ALL_TASK_RUN(task, platform="linkedin")

    assert len(task.retry_calls) == 1
    retry_payload = task.retry_calls[0]
    assert retry_payload["countdown"] == scoring_tasks.DEFAULT_RETRY_COUNTDOWN_SECONDS
    assert retry_payload["max_retries"] == scoring_tasks.MAX_SCORING_TASK_RETRIES
    assert isinstance(retry_payload["exc"], RepositoryError)


def test_score_all_unscored_jobs_does_not_retry_non_retryable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation failures raise directly without triggering retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scoring_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_non_retryable(
        platform: str,
        task_id: str | None,
    ) -> dict[str, Any]:
        del platform, task_id
        raise ValueError("invalid payload")

    monkeypatch.setattr(
        scoring_tasks,
        "_run_score_all_unscored_jobs",
        raise_non_retryable,
    )

    with pytest.raises(ValueError, match="invalid payload"):
        SCORE_ALL_TASK_RUN(task, platform="linkedin")

    assert task.retry_calls == []


def test_score_single_job_task_rejects_non_positive_job_id() -> None:
    """Task validates positive job_id for single-job scoring."""
    with pytest.raises(ValueError, match="job_id must be greater than 0"):
        SCORE_SINGLE_TASK_RUN(
            FakeBoundTask(), job_id=0, profile_id=1, platform="linkedin"
        )


def test_run_score_single_job_falls_back_to_first_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-job helper resolves first profile when profile_id is not provided."""

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

    class FakeProfileRepository:
        def __init__(self, db_session: DummyAsyncSession) -> None:
            self.db_session = db_session

        async def get_first(self) -> Any:
            return SimpleNamespace(id=13)

    class FakeMatchScoreRepository:
        def __init__(self, db_session: DummyAsyncSession) -> None:
            self.db_session = db_session

    class FakeJobEnrichmentRepository:
        def __init__(self, db_session: DummyAsyncSession) -> None:
            self.db_session = db_session

    class FakeScore:
        def model_dump(self, mode: str = "python") -> dict[str, Any]:
            assert mode == "json"
            return {"job_id": 5, "profile_id": 13, "relevance_score": 80}

    class FakeMatchService:
        def __init__(
            self,
            job_repo: Any,
            profile_repo: Any,
            match_repo: Any,
            enrichment_repo: Any,
        ) -> None:
            self.job_repo = job_repo
            self.profile_repo = profile_repo
            self.match_repo = match_repo
            self.enrichment_repo = enrichment_repo

        async def score_job(self, job_id: int, profile_id: int) -> FakeScore:
            assert job_id == 5
            assert profile_id == 13
            return FakeScore()

    monkeypatch.setattr(scoring_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scoring_tasks, "JobRepository", FakeJobRepository)
    monkeypatch.setattr(scoring_tasks, "ProfileRepository", FakeProfileRepository)
    monkeypatch.setattr(scoring_tasks, "MatchScoreRepository", FakeMatchScoreRepository)
    monkeypatch.setattr(
        scoring_tasks,
        "JobEnrichmentRepository",
        FakeJobEnrichmentRepository,
    )
    monkeypatch.setattr(scoring_tasks, "MatchService", FakeMatchService)

    result = asyncio.run(
        scoring_tasks._run_score_single_job(
            job_id=5,
            profile_id=None,
            platform="linkedin",
            task_id="task-123",
        )
    )

    assert result["status"] == "success"
    assert result["profile_id"] == 13
    assert result["score"]["relevance_score"] == 80
