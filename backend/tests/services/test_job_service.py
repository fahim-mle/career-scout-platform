"""Unit tests for JobService business logic and error handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.core.exceptions import (
    BusinessLogicError,
    DuplicateJobError,
    NotFoundError,
    RepositoryError,
)
from src.repositories.job import JobRepository
from src.repositories.job_enrichment import JobEnrichmentRepository
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


def make_enrichment(**overrides: Any) -> SimpleNamespace:
    """Build a job enrichment-like object for list enrichment tests."""
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "id": 1,
        "job_id": 1,
        "extractor_version": "heuristic-v1",
        "status": "success",
        "skills": ["Python", "FastAPI"],
        "job_type": "Full-time",
        "salary_min": 120000,
        "salary_max": 160000,
        "salary_currency": "AUD",
        "salary_period": "year",
        "salary_raw": "$120k-$160k AUD",
        "enriched_at": now,
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


@dataclass
class FakeJobEnrichmentRepository:
    """In-memory async repository stub for enrichment reads."""

    enrichments: list[SimpleNamespace] = field(default_factory=list)
    fail_list_by_job_ids: bool = False

    async def list_by_job_ids(self, job_ids: list[int]) -> list[SimpleNamespace]:
        """Return enrichments matching requested job ids.

        Args:
            job_ids: Raw job ids to search.

        Returns:
            Matching enrichment rows.

        Raises:
            RepositoryError: If configured to fail.
        """
        if self.fail_list_by_job_ids:
            raise RepositoryError("repo list_by_job_ids failed")
        job_id_set = set(job_ids)
        return [item for item in self.enrichments if item.job_id in job_id_set]


def make_service(
    repo: FakeJobRepository,
    enrichment_repo: FakeJobEnrichmentRepository | None = None,
) -> JobService:
    """Create JobService with a casted repository test double."""
    cast_enrichment = (
        cast(JobEnrichmentRepository, enrichment_repo)
        if enrichment_repo is not None
        else None
    )
    return JobService(cast(JobRepository, repo), enrichment_repo=cast_enrichment)


@pytest.mark.asyncio
async def test_get_job_returns_response_when_found() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)})
    service = make_service(repo)

    result = await service.get_job(1)

    assert result.id == 1
    assert result.platform == "linkedin"


@pytest.mark.asyncio
async def test_get_job_raises_not_found_when_missing() -> None:
    service = make_service(FakeJobRepository())

    with pytest.raises(NotFoundError, match="not found"):
        await service.get_job(999)


@pytest.mark.asyncio
async def test_create_job_rejects_future_date() -> None:
    service = make_service(FakeJobRepository())
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
async def test_create_job_success_returns_response() -> None:
    service = make_service(FakeJobRepository())
    payload = JobCreate(
        external_id="new-1",
        platform="linkedin",
        url="https://linkedin.com/jobs/new-1",
        title="Backend Engineer",
        company="Acme",
        location="Brisbane",
    )

    result = await service.create_job(payload)

    assert result.id == 1
    assert result.external_id == "new-1"
    assert result.platform == "linkedin"


@pytest.mark.asyncio
async def test_create_job_rejects_url_domain_mismatch() -> None:
    service = make_service(FakeJobRepository())
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
    service = make_service(repo)
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
    service = make_service(repo)

    with pytest.raises(BusinessLogicError, match="external_id cannot be changed"):
        await service.update_job(1, JobUpdate(external_id="other-id"))


@pytest.mark.asyncio
async def test_update_job_rejects_non_growing_description() -> None:
    repo = FakeJobRepository(
        jobs={1: make_job(id=1, description_full="This is a very long description")}
    )
    service = make_service(repo)

    with pytest.raises(BusinessLogicError, match="must be longer"):
        await service.update_job(1, JobUpdate(description_full="short"))


@pytest.mark.asyncio
async def test_update_job_allows_longer_description() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1, description_full="short")})
    service = make_service(repo)

    result = await service.update_job(
        1,
        JobUpdate(description_full="this is now a much longer and richer description"),
    )

    assert result.description_full is not None
    assert result.description_full.startswith("this is now")


@pytest.mark.asyncio
async def test_update_job_allows_clearing_description_with_none() -> None:
    repo = FakeJobRepository(
        jobs={1: make_job(id=1, description_full="This can be cleared")}
    )
    service = make_service(repo)

    result = await service.update_job(1, JobUpdate(description_full=None))

    assert result.description_full is None


@pytest.mark.asyncio
async def test_delete_job_soft_deletes_and_is_idempotent() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1, is_active=True)})
    service = make_service(repo)

    first = await service.delete_job(1)
    second = await service.delete_job(1)

    assert first is True
    assert second is True
    assert repo.jobs[1].is_active is False


@pytest.mark.asyncio
async def test_list_jobs_rejects_invalid_platform_filter() -> None:
    service = make_service(FakeJobRepository())

    with pytest.raises(BusinessLogicError, match="Invalid platform"):
        await service.list_jobs(platform="monster")


@pytest.mark.asyncio
async def test_repository_error_translates_to_business_logic_error() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)}, fail_update=True)
    service = make_service(repo)

    with pytest.raises(BusinessLogicError, match="Failed to update job"):
        await service.update_job(1, JobUpdate(title="New title"))


@pytest.mark.asyncio
async def test_list_enriched_jobs_merges_latest_enrichment_values() -> None:
    repo = FakeJobRepository(
        jobs={
            1: make_job(id=1, external_id="job-1"),
            2: make_job(id=2, external_id="job-2"),
        }
    )
    enrichment_repo = FakeJobEnrichmentRepository(
        enrichments=[
            make_enrichment(
                id=4,
                job_id=1,
                extractor_version="heuristic-v1",
                skills=["Python"],
                enriched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            make_enrichment(
                id=5,
                job_id=1,
                extractor_version="heuristic-v2",
                skills=["Python", "FastAPI"],
                job_type="Contract",
                salary_min=900,
                salary_max=1100,
                salary_period="day",
                enriched_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]
    )
    service = make_service(repo, enrichment_repo)

    result = await service.list_enriched_jobs()

    assert [job.id for job in result] == [2, 1]
    assert result[0].skills is None
    assert result[0].enrichment_status is None
    assert result[1].skills == ["Python", "FastAPI"]
    assert result[1].job_type == "Contract"
    assert result[1].salary_range == {
        "min": 900,
        "max": 1100,
        "currency": "AUD",
        "period": "day",
        "raw": "$120k-$160k AUD",
    }
    assert result[1].enrichment_version == "heuristic-v2"
    assert result[1].enrichment_updated_at == datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_list_enriched_jobs_converts_enrichment_repo_error() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)})
    enrichment_repo = FakeJobEnrichmentRepository(fail_list_by_job_ids=True)
    service = make_service(repo, enrichment_repo)

    with pytest.raises(BusinessLogicError, match="Failed to list jobs"):
        await service.list_enriched_jobs()
