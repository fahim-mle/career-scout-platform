"""Unit tests for scraper task retry and safety controls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.scrapers.linkedin import LinkedInChallengeError, LinkedInTransientError
from src.scrapers.indeed import IndeedNonRetryableError, IndeedTransientError
from src.scrapers.seek import SeekNonRetryableError, SeekTransientError
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


class DummyAsyncSession:
    """Trivial async-session placeholder for persistence unit tests."""


class DummySessionContext:
    """Async context manager yielding a dummy async DB session."""

    async def __aenter__(self) -> Any:
        return DummyAsyncSession()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc_type, exc, tb


def make_linkedin_scraper_double(
    scraped_jobs: list[dict[str, Any]],
) -> type:
    """Build a lightweight LinkedIn scraper double for a fixed payload."""

    class FakeLinkedInScraper:
        def __init__(self, headless: bool, rate_limit_seconds: float) -> None:
            self.headless = headless
            self.rate_limit_seconds = rate_limit_seconds

        async def __aenter__(self) -> "FakeLinkedInScraper":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            del exc_type, exc, tb

        async def scrape_jobs(
            self,
            query: str,
            location: str,
            limit: int,
        ) -> list[dict[str, Any]]:
            del query, location, limit
            return scraped_jobs

    return FakeLinkedInScraper


def make_seek_scraper_double(
    scraped_jobs: list[dict[str, Any]],
) -> type:
    """Build a lightweight Seek scraper double for a fixed payload."""

    class FakeSeekScraper:
        def __init__(self, headless: bool, rate_limit_seconds: float) -> None:
            self.headless = headless
            self.rate_limit_seconds = rate_limit_seconds

        async def __aenter__(self) -> "FakeSeekScraper":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            del exc_type, exc, tb

        async def scrape_jobs(
            self,
            query: str,
            location: str,
            limit: int,
        ) -> list[dict[str, Any]]:
            del query, location, limit
            return scraped_jobs

    return FakeSeekScraper


SCRAPE_TASK_RUN = scraper_tasks.scrape_linkedin_jobs.run.__func__  # type: ignore[attr-defined]
SEEK_SCRAPE_TASK_RUN = scraper_tasks.scrape_seek_jobs.run.__func__  # type: ignore[attr-defined]
SEEK_PROFILE_SET_TASK_RUN = scraper_tasks.scrape_seek_profile_set.run.__func__  # type: ignore[attr-defined]
INDEED_SCRAPE_TASK_RUN = scraper_tasks.scrape_indeed_jobs.run.__func__  # type: ignore[attr-defined]
INDEED_PROFILE_SET_TASK_RUN = scraper_tasks.scrape_indeed_profile_set.run.__func__  # type: ignore[attr-defined]


def test_record_scraper_result_metrics_increments_jobs_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Result metric helper emits jobs_created_total using created count."""
    created_calls: list[dict[str, Any]] = []

    def fake_increment_jobs_created(platform: str, count: int = 1) -> None:
        created_calls.append({"platform": platform, "count": count})

    monkeypatch.setattr(
        scraper_tasks,
        "increment_jobs_created",
        fake_increment_jobs_created,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "increment_jobs_scraped",
        lambda platform, count=1: None,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "increment_jobs_duplicates",
        lambda platform, count=1: None,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "increment_jobs_errors",
        lambda platform, count=1: None,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "increment_jobs_updated",
        lambda platform, count=1: None,
    )

    scraper_tasks._record_scraper_result_metrics(
        platform="linkedin",
        scraped=5,
        created=2,
        duplicates=1,
        failed=0,
        updated=1,
        jobs_in_database=4,
        task_id="task-123",
    )

    assert created_calls == [{"platform": "linkedin", "count": 2}]


def test_scrape_linkedin_jobs_passes_created_count_to_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LinkedIn task forwards created count into metric recording helper."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "linkedin",
            "query": "python",
            "location": "remote",
            "scraped": 3,
            "created": 2,
            "updated": 0,
            "duplicates": 1,
            "failed": 0,
            "enrichment_job_ids": [],
        }

    metric_payloads: list[dict[str, Any]] = []

    def fake_record_scraper_result_metrics(**kwargs: Any) -> None:
        metric_payloads.append(kwargs)

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "_record_scraper_result_metrics",
        fake_record_scraper_result_metrics,
    )
    monkeypatch.setattr(
        scraper_tasks,
        "_enqueue_enrichment_task",
        lambda **_kwargs: None,
    )

    result = SCRAPE_TASK_RUN(task, query="python", location="remote", limit=5)

    assert result["status"] == "success"
    assert len(metric_payloads) == 1
    assert metric_payloads[0]["created"] == 2


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


def test_scrape_linkedin_jobs_reraises_unexpected_error_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected non-classified errors are re-raised without retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_unexpected(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("unexpected parse shape")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        raise_unexpected,
    )

    with pytest.raises(RuntimeError, match="unexpected parse shape"):
        SCRAPE_TASK_RUN(
            task,
            query="python",
            location="remote",
            limit=5,
        )

    assert task.retry_calls == []


def test_load_linkedin_search_profiles_invalid_priority_falls_back_to_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Invalid profile priority values fallback to profile index."""
    config_path = tmp_path / "linkedin_profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "alpha",
                        "query": "python",
                        "location": "remote",
                        "limit": 3,
                        "priority": "invalid",
                    },
                    {
                        "id": "beta",
                        "query": "backend",
                        "location": "remote",
                        "limit": 4,
                        "priority": 3,
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(scraper_tasks, "LINKEDIN_PROFILE_CONFIG_PATH", config_path)

    profiles = scraper_tasks._load_linkedin_search_profiles()

    assert len(profiles) == 2
    assert profiles[0]["id"] == "alpha"
    assert profiles[0]["priority"] == 1
    assert profiles[1]["id"] == "beta"
    assert profiles[1]["priority"] == 3


def test_load_seek_search_profiles_invalid_priority_falls_back_to_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Seek profile loader falls back to profile index on invalid priority."""
    config_path = tmp_path / "seek_profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "alpha",
                        "query": "python",
                        "location": "brisbane",
                        "limit": 3,
                        "priority": "invalid",
                    },
                    {
                        "id": "beta",
                        "query": "backend",
                        "location": "remote",
                        "limit": 4,
                        "priority": 3,
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(scraper_tasks, "SEEK_PROFILE_CONFIG_PATH", config_path)

    profiles = scraper_tasks._load_seek_search_profiles()

    assert len(profiles) == 2
    assert profiles[0]["id"] == "alpha"
    assert profiles[0]["priority"] == 1
    assert profiles[1]["id"] == "beta"
    assert profiles[1]["priority"] == 3


def test_load_indeed_search_profiles_invalid_priority_falls_back_to_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Indeed profile loader falls back to profile index on invalid priority."""
    config_path = tmp_path / "indeed_profiles.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "alpha",
                        "query": "python",
                        "location": "brisbane",
                        "limit": 3,
                        "priority": "invalid",
                    },
                    {
                        "id": "beta",
                        "query": "backend",
                        "location": "remote",
                        "limit": 4,
                        "priority": 3,
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(scraper_tasks, "INDEED_PROFILE_CONFIG_PATH", config_path)

    profiles = scraper_tasks._load_indeed_search_profiles()

    assert len(profiles) == 2
    assert profiles[0]["id"] == "alpha"
    assert profiles[0]["priority"] == 1
    assert profiles[1]["id"] == "beta"
    assert profiles[1]["priority"] == 3


def test_build_job_update_payload_only_sets_missing_fields() -> None:
    """Existing values must not be overwritten by enrichment update helper."""

    existing = SimpleNamespace(
        description_full="already set",
        description_short=None,
        job_type=None,
        scraped_jobs=None,
        platform_metadata=None,
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
        scraped_jobs="<div>already set</div>",
        platform_metadata={"platform": "linkedin"},
    )
    scraped = {
        "description_full": "candidate",
        "description_short": "candidate",
        "job_type": "Full-Time",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)
    assert result == {}


def test_build_job_update_payload_sets_missing_scraped_jobs_and_metadata() -> None:
    """Update helper should enrich raw html and metadata when missing."""

    existing = SimpleNamespace(
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "scraped_jobs": '<div id="job-details">About the job</div>',
        "platform_metadata": {"platform": "linkedin", "location": "Sydney"},
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {
        "scraped_jobs": '<div id="job-details">About the job</div>',
        "platform_metadata": {"platform": "linkedin", "location": "Sydney"},
    }


def test_build_job_update_payload_sets_meaningful_values_when_existing_is_empty() -> (
    None
):
    """Helper should enrich fields when existing values are present but empty."""

    existing = SimpleNamespace(
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs="",
        platform_metadata={},
    )
    scraped = {
        "scraped_jobs": '<div id="job-details">About the job</div>',
        "platform_metadata": {"platform": "seek", "location": "Brisbane"},
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {
        "scraped_jobs": '<div id="job-details">About the job</div>',
        "platform_metadata": {"platform": "seek", "location": "Brisbane"},
    }


def test_normalize_scraped_payload_maps_metadata_to_platform_metadata() -> None:
    """Normalizer should map generic metadata key for ORM compatibility."""

    normalized = scraper_tasks._normalize_scraped_payload(
        {
            "external_id": "123",
            "metadata": {"platform": "linkedin", "location": "Remote"},
            "scraped_jobs": '<div id="job-details">Role details</div>',
        }
    )

    assert "metadata" not in normalized
    assert normalized["platform_metadata"] == {
        "platform": "linkedin",
        "location": "Remote",
    }
    assert normalized["scraped_jobs"] == '<div id="job-details">Role details</div>'


def test_normalize_scraped_payload_preserves_existing_platform_metadata() -> None:
    """Normalizer should not overwrite explicit platform_metadata values."""

    normalized = scraper_tasks._normalize_scraped_payload(
        {
            "external_id": "123",
            "metadata": {"platform": "linkedin", "location": "Remote"},
            "platform_metadata": {"platform": "linkedin", "location": "Sydney"},
        }
    )

    assert "metadata" not in normalized
    assert normalized["platform_metadata"] == {
        "platform": "linkedin",
        "location": "Sydney",
    }


def test_build_job_update_payload_ignores_empty_new_metadata_values() -> None:
    """Update helper should skip empty enrichment values to avoid noisy writes."""

    existing = SimpleNamespace(
        description_full=None,
        description_short=None,
        job_type=None,
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "scraped_jobs": "   ",
        "platform_metadata": {},
        "description_full": "",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {}


def test_run_linkedin_scrape_and_persist_maps_metadata_and_persists_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestration should map metadata and persist new raw fields on create."""
    fake_scraped_jobs = [
        {
            "external_id": "new-raw-1",
            "platform": "linkedin",
            "url": "https://linkedin.com/jobs/new-raw-1",
            "title": "Backend Engineer",
            "company": "Career Scout",
            "location": "Remote",
            "description_full": "Full description",
            "description_short": "Short description",
            "scraped_jobs": '<div id="job-details"><p>Role</p></div>',
            "metadata": {"platform": "linkedin", "date_posted": "1 day ago"},
        }
    ]

    captured_payloads: list[dict[str, Any]] = []

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return None

        async def create(self, payload: dict[str, Any]) -> Any:
            captured_payloads.append(payload)
            return SimpleNamespace(id=99)

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del job_id, payload
            raise AssertionError("update should not be called in create path")

    monkeypatch.setattr(
        scraper_tasks,
        "LinkedInScraper",
        make_linkedin_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_linkedin_scrape_and_persist(
            query="python",
            location="remote",
            limit=3,
            task_id="task-79",
        )
    )

    assert result["created"] == 1
    assert result["updated"] == 0
    assert captured_payloads
    assert (
        captured_payloads[0]["scraped_jobs"]
        == '<div id="job-details"><p>Role</p></div>'
    )
    assert captured_payloads[0]["platform_metadata"] == {
        "platform": "linkedin",
        "date_posted": "1 day ago",
    }
    assert "metadata" not in captured_payloads[0]


def test_run_seek_scrape_and_persist_maps_metadata_and_persists_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek orchestration maps metadata and persists raw fields on create."""
    fake_scraped_jobs = [
        {
            "external_id": "seek-new-1",
            "platform": "seek",
            "url": "https://seek.com.au/job/seek-new-1",
            "title": "Backend Engineer",
            "company": "Career Scout",
            "location": "Brisbane",
            "description_full": "Full description",
            "description_short": "Short description",
            "scraped_jobs": '<div data-automation="jobAdDetails">Role</div>',
            "metadata": {"platform": "seek", "date_posted": "1 day ago"},
        }
    ]

    captured_payloads: list[dict[str, Any]] = []

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return None

        async def create(self, payload: dict[str, Any]) -> Any:
            captured_payloads.append(payload)
            return SimpleNamespace(id=199)

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del job_id, payload
            raise AssertionError("update should not be called in create path")

    monkeypatch.setattr(
        scraper_tasks,
        "SeekScraper",
        make_seek_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_seek_scrape_and_persist(
            query="python",
            location="brisbane",
            limit=3,
            task_id="task-84",
        )
    )

    assert result["created"] == 1
    assert result["updated"] == 0
    assert captured_payloads
    assert (
        captured_payloads[0]["scraped_jobs"]
        == '<div data-automation="jobAdDetails">Role</div>'
    )
    assert captured_payloads[0]["platform_metadata"] == {
        "platform": "seek",
        "date_posted": "1 day ago",
    }
    assert "metadata" not in captured_payloads[0]


def test_run_seek_scrape_and_persist_updates_empty_fields_with_meaningful_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek update path should enrich empty persisted fields."""
    fake_scraped_jobs = [
        {
            "external_id": "seek-existing-1",
            "platform": "seek",
            "scraped_jobs": '<div data-automation="jobAdDetails">Fresh role details</div>',
            "metadata": {"platform": "seek", "date_posted": "Today"},
        }
    ]

    update_payloads: list[dict[str, Any]] = []

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return SimpleNamespace(
                id=77,
                title="Backend Engineer",
                description_full="existing full",
                description_short="existing short",
                job_type="Full-Time",
                scraped_jobs="",
                platform_metadata={},
            )

        async def create(self, payload: dict[str, Any]) -> Any:
            del payload
            raise AssertionError("create should not be called in update path")

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            update_payloads.append({"job_id": job_id, "payload": payload})
            return SimpleNamespace(id=job_id)

    monkeypatch.setattr(
        scraper_tasks,
        "SeekScraper",
        make_seek_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_seek_scrape_and_persist(
            query="python",
            location="brisbane",
            limit=3,
            task_id="task-84",
        )
    )

    assert result["created"] == 0
    assert result["updated"] == 1
    assert result["duplicates"] == 0
    assert len(update_payloads) == 1
    assert update_payloads[0]["job_id"] == 77
    assert update_payloads[0]["payload"] == {
        "scraped_jobs": '<div data-automation="jobAdDetails">Fresh role details</div>',
        "platform_metadata": {"platform": "seek", "date_posted": "Today"},
    }


def test_run_seek_scrape_and_persist_skips_empty_values_for_non_empty_existing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek update path should not overwrite existing values with empty payloads."""
    fake_scraped_jobs = [
        {
            "external_id": "seek-existing-2",
            "platform": "seek",
            "scraped_jobs": "   ",
            "metadata": {},
        }
    ]

    update_called = False

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return SimpleNamespace(
                id=88,
                title="Backend Engineer",
                description_full="existing full",
                description_short="existing short",
                job_type="Full-Time",
                scraped_jobs='<div data-automation="jobAdDetails">Existing details</div>',
                platform_metadata={"platform": "seek", "date_posted": "Yesterday"},
            )

        async def create(self, payload: dict[str, Any]) -> Any:
            del payload
            raise AssertionError("create should not be called in update path")

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del job_id, payload
            nonlocal update_called
            update_called = True
            raise AssertionError("update should not be called for empty values")

    monkeypatch.setattr(
        scraper_tasks,
        "SeekScraper",
        make_seek_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_seek_scrape_and_persist(
            query="python",
            location="brisbane",
            limit=3,
            task_id="task-84",
        )
    )

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["duplicates"] == 1
    assert update_called is False


def test_run_seek_scrape_and_persist_does_not_overwrite_existing_enriched_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek update path should not overwrite already-populated enrichment fields."""
    fake_scraped_jobs = [
        {
            "external_id": "seek-existing-3",
            "platform": "seek",
            "scraped_jobs": '<div data-automation="jobAdDetails">New details</div>',
            "metadata": {"platform": "seek", "date_posted": "Today"},
            "description_full": "new full description",
        }
    ]

    update_called = False

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return SimpleNamespace(
                id=98,
                title="Backend Engineer",
                description_full="existing full",
                description_short="existing short",
                job_type="Full-Time",
                scraped_jobs='<div data-automation="jobAdDetails">Existing details</div>',
                platform_metadata={"platform": "seek", "date_posted": "Yesterday"},
            )

        async def create(self, payload: dict[str, Any]) -> Any:
            del payload
            raise AssertionError("create should not be called in update path")

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del job_id, payload
            nonlocal update_called
            update_called = True
            raise AssertionError(
                "update should not be called when values already exist"
            )

    monkeypatch.setattr(
        scraper_tasks,
        "SeekScraper",
        make_seek_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_seek_scrape_and_persist(
            query="python",
            location="brisbane",
            limit=3,
            task_id="task-84",
        )
    )

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["duplicates"] == 1
    assert update_called is False


def test_build_job_update_payload_updates_title_when_duplicate_artifact_corrected() -> (
    None
):
    """Existing duplicated title artifact should be corrected from new scrape."""

    existing = SimpleNamespace(
        title="Software Engineer Software Engineer",
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "title": "Software Engineer",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {"title": "Software Engineer"}


def test_build_job_update_payload_persists_normalized_incoming_title() -> None:
    """Duplicate title correction should persist normalized incoming title."""

    existing = SimpleNamespace(
        title="Software Engineer Software Engineer",
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "title": "  Software   Engineer  ",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {"title": "Software Engineer"}


def test_build_job_update_payload_updates_separator_joined_duplicate_title() -> None:
    """Helper should correct separator-joined duplicate title artifacts."""

    existing = SimpleNamespace(
        title="Software Engineer - Software Engineer",
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "title": "Software Engineer",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {"title": "Software Engineer"}


def test_build_job_update_payload_does_not_update_distinct_existing_title() -> None:
    """Distinct titles must not be overwritten by incoming values."""

    existing = SimpleNamespace(
        title="Senior Software Engineer",
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "title": "Software Engineer",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {}


def test_build_job_update_payload_does_not_update_legitimate_repeated_word_title() -> (
    None
):
    """Helper should not treat non-adjacent phrase titles as duplicate artifacts."""

    existing = SimpleNamespace(
        title="Head of People and Culture",
        description_full="full",
        description_short="short",
        job_type="Contract",
        scraped_jobs=None,
        platform_metadata=None,
    )
    scraped = {
        "title": "People and Culture Head",
    }

    result = scraper_tasks._build_job_update_payload(existing, scraped)

    assert result == {}


def test_scrape_linkedin_jobs_triggers_enrichment_when_job_ids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scrape task enqueues enrichment when created/updated ids are returned."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "linkedin",
            "query": "python",
            "location": "remote",
            "scraped": 2,
            "created": 1,
            "updated": 1,
            "duplicates": 0,
            "failed": 0,
            "enrichment_job_ids": [11, 22],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = SCRAPE_TASK_RUN(task, query="python", location="remote", limit=5)

    assert result["status"] == "success"
    assert len(enqueue_calls) == 1
    enqueue_call = enqueue_calls[0]
    assert enqueue_call["name"] == scraper_tasks.ENRICHMENT_TASK_NAME
    assert enqueue_call["kwargs"] == {"platform": "linkedin", "job_ids": [11, 22]}
    assert enqueue_call["countdown"] == 5


def test_scrape_linkedin_jobs_does_not_trigger_enrichment_without_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scrape task skips enrichment enqueue when no candidate ids are present."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "linkedin",
            "query": "python",
            "location": "remote",
            "scraped": 1,
            "created": 0,
            "updated": 0,
            "duplicates": 1,
            "failed": 0,
            "enrichment_job_ids": [],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_run_linkedin_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = SCRAPE_TASK_RUN(task, query="python", location="remote", limit=5)

    assert result["status"] == "success"
    assert enqueue_calls == []


def test_scrape_seek_jobs_returns_skipped_when_scraper_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek task returns skipped status when kill switch is disabled."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", False)

    result = SEEK_SCRAPE_TASK_RUN(
        task,
        query="python",
        location="brisbane",
        limit=5,
    )

    assert result["status"] == "skipped"
    assert result["platform"] == "seek"
    assert task.retry_calls == []


def test_scrape_seek_jobs_retries_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek transient scraper failures trigger Celery retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_transient(**_kwargs: Any) -> dict[str, Any]:
        raise SeekTransientError("seek timeout")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_seek_scrape_and_persist",
        raise_transient,
    )

    with pytest.raises(RetryInvoked, match="retry called"):
        SEEK_SCRAPE_TASK_RUN(
            task,
            query="python",
            location="brisbane",
            limit=5,
        )

    assert len(task.retry_calls) == 1
    retry_payload = task.retry_calls[0]
    assert retry_payload["countdown"] == scraper_tasks.DEFAULT_RETRY_COUNTDOWN_SECONDS
    assert retry_payload["max_retries"] == scraper_tasks.MAX_SCRAPER_TASK_RETRIES
    assert isinstance(retry_payload["exc"], SeekTransientError)


def test_scrape_seek_jobs_raises_non_retryable_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek non-retryable failures should not trigger retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_non_retryable(**_kwargs: Any) -> dict[str, Any]:
        raise SeekNonRetryableError("blocked")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_seek_scrape_and_persist",
        raise_non_retryable,
    )

    with pytest.raises(SeekNonRetryableError, match="blocked"):
        SEEK_SCRAPE_TASK_RUN(
            task,
            query="python",
            location="brisbane",
            limit=5,
        )

    assert task.retry_calls == []


def test_scrape_seek_jobs_triggers_enrichment_when_job_ids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek task enqueues enrichment for created or updated job ids."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "seek",
            "query": "python",
            "location": "brisbane",
            "scraped": 2,
            "created": 1,
            "updated": 1,
            "duplicates": 0,
            "failed": 0,
            "enrichment_job_ids": [31, 41],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_run_seek_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = SEEK_SCRAPE_TASK_RUN(
        task,
        query="python",
        location="brisbane",
        limit=5,
    )

    assert result["status"] == "success"
    assert len(enqueue_calls) == 1
    enqueue_call = enqueue_calls[0]
    assert enqueue_call["name"] == scraper_tasks.ENRICHMENT_TASK_NAME
    assert enqueue_call["kwargs"] == {"platform": "seek", "job_ids": [31, 41]}
    assert enqueue_call["countdown"] == 5


def test_scrape_seek_profile_set_triggers_enrichment_when_job_ids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seek profile-set task enqueues enrichment from aggregated profile ids."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "seek",
            "scraped": 2,
            "created": 1,
            "updated": 1,
            "duplicates": 0,
            "failed": 0,
            "enrichment_job_ids": [131, 141],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_load_seek_search_profiles",
        lambda: [
            {
                "id": "seek-1",
                "query": "python",
                "location": "brisbane",
                "limit": 2,
                "priority": 1,
            }
        ],
    )
    monkeypatch.setattr(
        scraper_tasks,
        "_run_seek_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = SEEK_PROFILE_SET_TASK_RUN(task)

    assert result["status"] == "success"
    assert result["profiles_processed"] == 1
    assert result["enrichment_job_ids"] == [131, 141]
    assert len(enqueue_calls) == 1
    enqueue_call = enqueue_calls[0]
    assert enqueue_call["name"] == scraper_tasks.ENRICHMENT_TASK_NAME
    assert enqueue_call["kwargs"] == {"platform": "seek", "job_ids": [131, 141]}
    assert enqueue_call["countdown"] == 5


def test_scrape_indeed_jobs_returns_skipped_when_scraper_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indeed task returns skipped status when kill switch is disabled."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", False)

    result = INDEED_SCRAPE_TASK_RUN(
        task,
        query="python",
        location="brisbane",
        limit=5,
    )

    assert result["status"] == "skipped"
    assert result["platform"] == "indeed"
    assert task.retry_calls == []


def test_scrape_indeed_jobs_retries_on_transient_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indeed transient scraper failures trigger Celery retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_transient(**_kwargs: Any) -> dict[str, Any]:
        raise IndeedTransientError("indeed timeout")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_indeed_scrape_and_persist",
        raise_transient,
    )

    with pytest.raises(RetryInvoked, match="retry called"):
        INDEED_SCRAPE_TASK_RUN(
            task,
            query="python",
            location="brisbane",
            limit=5,
        )

    assert len(task.retry_calls) == 1
    retry_payload = task.retry_calls[0]
    assert retry_payload["countdown"] == scraper_tasks.DEFAULT_RETRY_COUNTDOWN_SECONDS
    assert retry_payload["max_retries"] == scraper_tasks.MAX_SCRAPER_TASK_RETRIES
    assert isinstance(retry_payload["exc"], IndeedTransientError)


def test_scrape_indeed_jobs_raises_non_retryable_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indeed non-retryable failures should not trigger retry."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def raise_non_retryable(**_kwargs: Any) -> dict[str, Any]:
        raise IndeedNonRetryableError("blocked")

    monkeypatch.setattr(
        scraper_tasks,
        "_run_indeed_scrape_and_persist",
        raise_non_retryable,
    )

    with pytest.raises(IndeedNonRetryableError, match="blocked"):
        INDEED_SCRAPE_TASK_RUN(
            task,
            query="python",
            location="brisbane",
            limit=5,
        )

    assert task.retry_calls == []


def test_scrape_indeed_jobs_triggers_enrichment_when_job_ids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indeed task enqueues enrichment for created or updated job ids."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "indeed",
            "query": "python",
            "location": "brisbane",
            "scraped": 2,
            "created": 1,
            "updated": 1,
            "duplicates": 0,
            "failed": 0,
            "enrichment_job_ids": [81, 91],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_run_indeed_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = INDEED_SCRAPE_TASK_RUN(
        task,
        query="python",
        location="brisbane",
        limit=5,
    )

    assert result["status"] == "success"
    assert len(enqueue_calls) == 1
    enqueue_call = enqueue_calls[0]
    assert enqueue_call["name"] == scraper_tasks.ENRICHMENT_TASK_NAME
    assert enqueue_call["kwargs"] == {"platform": "indeed", "job_ids": [81, 91]}
    assert enqueue_call["countdown"] == 5


def test_scrape_indeed_profile_set_triggers_enrichment_when_job_ids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Indeed profile-set task enqueues enrichment from aggregated profile ids."""
    task = FakeBoundTask()
    monkeypatch.setattr(scraper_tasks.settings, "SCRAPER_ENABLED", True)

    async def fake_scrape_and_persist(**_kwargs: Any) -> dict[str, Any]:
        return {
            "status": "success",
            "platform": "indeed",
            "scraped": 2,
            "created": 1,
            "updated": 1,
            "duplicates": 0,
            "failed": 0,
            "enrichment_job_ids": [231, 241],
        }

    enqueue_calls: list[dict[str, Any]] = []

    def fake_send_task(name: str, kwargs: dict[str, Any], countdown: int) -> None:
        enqueue_calls.append({"name": name, "kwargs": kwargs, "countdown": countdown})

    monkeypatch.setattr(
        scraper_tasks,
        "_load_indeed_search_profiles",
        lambda: [
            {
                "id": "indeed-1",
                "query": "python",
                "location": "brisbane",
                "limit": 2,
                "priority": 1,
            }
        ],
    )
    monkeypatch.setattr(
        scraper_tasks,
        "_run_indeed_scrape_and_persist",
        fake_scrape_and_persist,
    )
    monkeypatch.setattr(scraper_tasks.celery_app, "send_task", fake_send_task)

    result = INDEED_PROFILE_SET_TASK_RUN(task)

    assert result["status"] == "success"
    assert result["profiles_processed"] == 1
    assert result["enrichment_job_ids"] == [231, 241]
    assert len(enqueue_calls) == 1
    enqueue_call = enqueue_calls[0]
    assert enqueue_call["name"] == scraper_tasks.ENRICHMENT_TASK_NAME
    assert enqueue_call["kwargs"] == {"platform": "indeed", "job_ids": [231, 241]}
    assert enqueue_call["countdown"] == 5


def test_run_linkedin_scrape_and_persist_does_not_count_none_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence summary ignores update attempts that return no updated row."""
    fake_scraped_jobs = [
        {
            "external_id": "existing-1",
            "description_full": "new full",
        },
        {
            "external_id": "new-1",
            "description_full": "new job",
        },
    ]

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del platform
            if external_id == "existing-1":
                return SimpleNamespace(
                    id=7,
                    description_full=None,
                    description_short=None,
                    job_type=None,
                    scraped_jobs=None,
                    platform_metadata=None,
                )
            return None

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del job_id, payload
            return None

        async def create(self, payload: dict[str, Any]) -> Any:
            del payload
            return SimpleNamespace(id=19)

    monkeypatch.setattr(
        scraper_tasks,
        "LinkedInScraper",
        make_linkedin_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_linkedin_scrape_and_persist(
            query="python",
            location="remote",
            limit=5,
            task_id="task-123",
        )
    )

    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["enrichment_job_ids"] == [19]


def test_run_linkedin_scrape_and_persist_counts_real_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistence summary counts updates only when repository returns a row."""
    fake_scraped_jobs = [
        {
            "external_id": "existing-1",
            "description_full": "new full",
        }
    ]

    class FakeJobRepository:
        def __init__(self, db_session: Any) -> None:
            self.db_session = db_session

        async def get_by_external_id(self, external_id: str, platform: str) -> Any:
            del external_id, platform
            return SimpleNamespace(
                id=21,
                description_full=None,
                description_short=None,
                job_type=None,
                scraped_jobs=None,
                platform_metadata=None,
            )

        async def update(self, job_id: int, payload: dict[str, Any]) -> Any:
            del payload
            return SimpleNamespace(id=job_id)

        async def create(self, payload: dict[str, Any]) -> Any:
            del payload
            raise AssertionError("create should not be called for existing job")

    monkeypatch.setattr(
        scraper_tasks,
        "LinkedInScraper",
        make_linkedin_scraper_double(fake_scraped_jobs),
    )
    monkeypatch.setattr(scraper_tasks, "get_session", lambda: DummySessionContext())
    monkeypatch.setattr(scraper_tasks, "JobRepository", FakeJobRepository)

    result = asyncio.run(
        scraper_tasks._run_linkedin_scrape_and_persist(
            query="python",
            location="remote",
            limit=5,
            task_id="task-123",
        )
    )

    assert result["created"] == 0
    assert result["updated"] == 1
    assert result["enrichment_job_ids"] == [21]
