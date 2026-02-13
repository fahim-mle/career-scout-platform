"""Unit tests for JobService business logic and error handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.exceptions import (
    BusinessLogicError,
    DuplicateJobError,
    NotFoundError,
    RepositoryError,
)
from src.schemas.job import JobCreate, JobUpdate
from src.services.job_service import JobService


def make_job(**overrides: Any) -> SimpleNamespace:
    """Build a job-like object compatible with JobResponse.from_attributes."""
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "id": 1,
        "created_at": now,
        "updated_at": now,
        "external_id": "ext-1",
        "platform": "linkedin",
        "url": "https://linkedin.com/jobs/ext-1",
        "title": "Backend Engineer",
        "company": "Career Scout",
        "location": "Brisbane",
        "job_type": None,
        "description_short": "Short text",
        "description_full": "Longer full description",
        "posted_date": date.today(),
        "scraped_at": now,
        "is_active": True,
        "skills": ["Python"],
        "salary_range": {"min": 100000, "max": 140000, "currency": "AUD"},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@dataclass
class FakeJobRepository:
    """In-memory async repository stub for JobService tests."""

    jobs: dict[int, SimpleNamespace] = field(default_factory=dict)
    fail_get_by_id: bool = False
    fail_get_all: bool = False
    fail_create: bool = False
    fail_update: bool = False
    duplicate_on_create: bool = False
    duplicate_on_update: bool = False

    async def get_by_id(self, job_id: int) -> SimpleNamespace | None:
        if self.fail_get_by_id:
            raise RepositoryError("repo get_by_id failed")
        return self.jobs.get(job_id)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
    ) -> list[SimpleNamespace]:
        if self.fail_get_all:
            raise RepositoryError("repo get_all failed")
        items = [job for job in self.jobs.values() if job.is_active is is_active]
        if platform is not None:
            items = [job for job in items if job.platform == platform]
        items.sort(key=lambda item: item.id, reverse=True)
        return items[skip : skip + limit]

    async def create(self, job_data: dict[str, Any]) -> SimpleNamespace:
        if self.duplicate_on_create:
            raise DuplicateJobError("duplicate")
        if self.fail_create:
            raise RepositoryError("repo create failed")

        next_id = (max(self.jobs.keys()) + 1) if self.jobs else 1
        created = make_job(id=next_id, **job_data)
        self.jobs[next_id] = created
        return created

    async def update(
        self, job_id: int, job_data: dict[str, Any]
    ) -> SimpleNamespace | None:
        if self.duplicate_on_update:
            raise DuplicateJobError("duplicate")
        if self.fail_update:
            raise RepositoryError("repo update failed")

        existing = self.jobs.get(job_id)
        if existing is None:
            return None

        merged = existing.__dict__.copy()
        merged.update(job_data)
        merged["updated_at"] = datetime.now(timezone.utc)
        updated = SimpleNamespace(**merged)
        self.jobs[job_id] = updated
        return updated


@pytest.mark.asyncio
async def test_get_job_returns_response_when_found() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)})
    service = JobService(repo)

    result = await service.get_job(1)

    assert result.id == 1
    assert result.platform == "linkedin"


@pytest.mark.asyncio
async def test_get_job_raises_not_found_when_missing() -> None:
    service = JobService(FakeJobRepository())

    with pytest.raises(NotFoundError, match="not found"):
        await service.get_job(999)


@pytest.mark.asyncio
async def test_create_job_rejects_future_date() -> None:
    service = JobService(FakeJobRepository())
    payload = JobCreate(
        external_id="future-1",
        platform="linkedin",
        url="https://linkedin.com/jobs/future-1",
        title="Future Job",
        company="Future Co",
        location="Brisbane",
        posted_date=date.today() + timedelta(days=1),
    )

    with pytest.raises(BusinessLogicError, match="future"):
        await service.create_job(payload)


@pytest.mark.asyncio
async def test_create_job_rejects_url_domain_mismatch() -> None:
    service = JobService(FakeJobRepository())
    payload = JobCreate(
        external_id="bad-url-1",
        platform="linkedin",
        url="https://indeed.com/jobs/bad-url-1",
        title="Data Engineer",
        company="Acme",
        location="Brisbane",
    )

    with pytest.raises(BusinessLogicError, match="does not match platform"):
        await service.create_job(payload)


@pytest.mark.asyncio
async def test_create_job_converts_duplicate_error() -> None:
    repo = FakeJobRepository(duplicate_on_create=True)
    service = JobService(repo)
    payload = JobCreate(
        external_id="dup-1",
        platform="linkedin",
        url="https://linkedin.com/jobs/dup-1",
        title="Platform Engineer",
        company="Acme",
        location="Brisbane",
    )

    with pytest.raises(BusinessLogicError, match="already exists"):
        await service.create_job(payload)


@pytest.mark.asyncio
async def test_update_job_rejects_immutable_fields() -> None:
    repo = FakeJobRepository(
        jobs={1: make_job(id=1, external_id="fixed-1", platform="linkedin")}
    )
    service = JobService(repo)

    with pytest.raises(BusinessLogicError, match="external_id cannot be changed"):
        await service.update_job(1, JobUpdate(external_id="other-id"))


@pytest.mark.asyncio
async def test_update_job_rejects_non_growing_description() -> None:
    repo = FakeJobRepository(
        jobs={1: make_job(id=1, description_full="This is a very long description")}
    )
    service = JobService(repo)

    with pytest.raises(BusinessLogicError, match="must be longer"):
        await service.update_job(1, JobUpdate(description_full="short"))


@pytest.mark.asyncio
async def test_update_job_allows_longer_description() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1, description_full="short")})
    service = JobService(repo)

    result = await service.update_job(
        1,
        JobUpdate(description_full="this is now a much longer and richer description"),
    )

    assert result.description_full.startswith("this is now")


@pytest.mark.asyncio
async def test_delete_job_soft_deletes_and_is_idempotent() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1, is_active=True)})
    service = JobService(repo)

    first = await service.delete_job(1)
    second = await service.delete_job(1)

    assert first is True
    assert second is True
    assert repo.jobs[1].is_active is False


@pytest.mark.asyncio
async def test_list_jobs_rejects_invalid_platform_filter() -> None:
    service = JobService(FakeJobRepository())

    with pytest.raises(BusinessLogicError, match="Invalid platform"):
        await service.list_jobs(platform="monster")


@pytest.mark.asyncio
async def test_repository_error_translates_to_business_logic_error() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)}, fail_update=True)
    service = JobService(repo)

    with pytest.raises(BusinessLogicError, match="Failed to update job"):
        await service.update_job(1, JobUpdate(title="New title"))
