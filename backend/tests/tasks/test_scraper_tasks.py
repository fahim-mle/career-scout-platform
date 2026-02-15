"""Unit tests for scraper task retry and safety controls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.scrapers.linkedin import LinkedInChallengeError, LinkedInTransientError
from src.tasks import scraper_tasks


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


SCRAPE_TASK_RUN = scraper_tasks.scrape_linkedin_jobs.run.__func__  # type: ignore[attr-defined]


def test_scrape_linkedin_jobs_returns_skipped_when_scraper_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task returns skipped status when kill switch is disabled."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", False)

    result = SCRAPE_TASK_RUN(
        task,
        query="python",
        location="remote",
        limit=5,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "SCRAPER_ENABLED is false"
    assert task.retry_calls == []


def test_scrape_linkedin_jobs_raises_non_retryable_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-retryable challenge errors are re-raised without retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_non_retryable(**_kwargs: Any) -> dict[str, Any]:
        raise LinkedInChallengeError("captcha detected")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        raise_non_retryable,
    )

    with pytest.raises(LinkedInChallengeError, match="captcha"):
        SCRAPE_TASK_RUN(
            task,
            query="python",
            location="remote",
            limit=5,
        )

    assert task.retry_calls == []


def test_scrape_linkedin_jobs_retries_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transient scraper failures trigger Celery retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_transient(**_kwargs: Any) -> dict[str, Any]:
        raise LinkedInTransientError("timeout during navigation")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        raise_transient,
    )

    with pytest.raises(RetryInvoked, match="retry called"):
        SCRAPE_TASK_RUN(
            task,
            query="python",
            location="remote",
            limit=5,
        )

    assert len(task.retry_calls) == 1
    retry_payload = task.retry_calls[0]
    assert retry_payload["countdown"] == scraper_tasks.DEFAULT_RETRY_COUNTDOWN_SECONDS
    assert retry_payload["max_retries"] == scraper_tasks.MAX_SCRAPER_TASK_RETRIES
    assert isinstance(retry_payload["exc"], LinkedInTransientError)


def test_build_job_update_payload_only_sets_missing_fields() -> None:
    """Existing values must not be overwritten by enrichment update helper."""

    existing = SimpleNamespace(
        description_full="already set",
        description_short=None,
        job_type=None,
    )
    scraped = {
        "description_full": "new full",
        "description_short": "new short",
        "job_type": "Full-Time",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {
        "description_short": "new short",
        "job_type": "Full-Time",
    }


def test_build_job_update_payload_empty_when_no_new_values() -> None:
    """Update helper should return empty payload when nothing enriches row."""

    existing = SimpleNamespace(
        description_full="full",
        description_short="short",
        job_type="Contract",
    )
    scraped = {
        "description_full": "candidate",
        "description_short": "candidate",
        "job_type": "Full-Time",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)
    assert result == {}
