"""Unit tests for JobEnrichmentService skills extraction and enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.core.exceptions import BusinessLogicError, RepositoryError
from src.models.job import Job
from src.repositories.job import JobRepository
from src.services.job_enrichment_service import JobEnrichmentService


def make_job(**overrides: Any) -> SimpleNamespace:
    """Build a minimal job-like object for enrichment tests.

    Args:
        **overrides: Field overrides for the generated job object.

    Returns:
        Job-like namespace with fields used by JobEnrichmentService.
    """
    now = datetime.now(timezone.utc)
    data: dict[str, Any] = {
        "id": 1,
        "created_at": now,
        "updated_at": now,
        "external_id": "ext-1",
        "platform": "linkedin",
        "title": "Backend Engineer",
        "company": "Career Scout",
        "location": "Brisbane",
        "description_short": None,
        "description_full": None,
        "skills": None,
        "job_type": None,
        "salary_range": None,
        "is_active": True,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@dataclass
class FakeJobRepository:
    """In-memory async repository stub for JobEnrichmentService tests."""

    jobs: dict[int, SimpleNamespace] = field(default_factory=dict)
    fail_get_by_id: bool = False
    fail_get_all: bool = False
    fail_update_ids: set[int] = field(default_factory=set)
    update_calls: list[tuple[int, dict[str, Any]]] = field(default_factory=list)

    async def get_by_id(self, job_id: int) -> SimpleNamespace | None:
        """Fetch one fake job by id."""
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
        """Return filtered fake jobs for batch enrichment."""
        if self.fail_get_all:
            raise RepositoryError("repo get_all failed")

        items = [job for job in self.jobs.values() if job.is_active is is_active]
        if platform is not None:
            items = [job for job in items if job.platform == platform]
        items.sort(key=lambda item: item.id)
        return items[skip : skip + limit]

    async def update(
        self,
        job_id: int,
        job_data: dict[str, Any],
    ) -> SimpleNamespace | None:
        """Persist fake updates into the in-memory dictionary."""
        self.update_calls.append((job_id, job_data.copy()))
        if job_id in self.fail_update_ids:
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


def make_service(repo: FakeJobRepository) -> JobEnrichmentService:
    """Create JobEnrichmentService with a casted repository test double."""
    return JobEnrichmentService(cast(JobRepository, repo))


def test_extract_skills_from_description_finds_canonical_from_aliases() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)
    description = (
        "We need PYTHON and strong React.js UI skills, plus nodejs APIs, "
        "Postgres tuning, docker workflows, and aws cloud operations."
    )

    result = service.extract_skills_from_description(description)

    assert result == ["Python", "React", "Node.js", "PostgreSQL", "Docker", "AWS"]


def test_extract_skills_from_description_deduplicates_and_preserves_order() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)
    description = "React reactjs PYTHON py node.js NodeJS SQL and postgres SQL"

    result = service.extract_skills_from_description(description)

    assert result == ["React", "Python", "Node.js", "SQL", "PostgreSQL"]


def test_extract_skills_from_description_returns_empty_for_blank_text() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)

    assert service.extract_skills_from_description("") == []
    assert service.extract_skills_from_description("   ") == []


def test_build_enrichment_payload_returns_empty_when_skills_already_present() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)
    job = make_job(skills=["Python"], description_full="FastAPI and SQL")

    result = service.build_enrichment_payload(cast(Job, job))

    assert result == {}


def test_extract_job_type_from_text_detects_and_normalizes() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)

    result = service.extract_job_type_from_text(
        "Senior Backend Engineer (full-time) with async Python experience."
    )

    assert result == "Full-Time"


def test_extract_salary_range_from_text_parses_explicit_hourly_amount() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)

    result = service.extract_salary_range_from_text(
        "Compensation is $45/hr plus superannuation."
    )

    assert result == {
        "min": 45,
        "max": 45,
        "currency": "AUD",
        "period": "hour",
        "raw": "$45",
    }


def test_extract_salary_range_from_text_parses_explicit_yearly_range() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)

    result = service.extract_salary_range_from_text(
        "Salary: AUD 120000 to 150000 per annum based on experience."
    )

    assert result == {
        "min": 120000,
        "max": 150000,
        "currency": "AUD",
        "period": "year",
        "raw": "AUD 120000 to 150000",
    }


def test_extract_salary_range_from_text_infers_period_when_missing() -> None:
    repo = FakeJobRepository()
    service = make_service(repo)

    result = service.extract_salary_range_from_text("Day-rate equivalent: $800 - $1000")

    assert result == {
        "min": 800,
        "max": 1000,
        "currency": "AUD",
        "period": "day",
        "raw": "$800 - $1000",
    }


def test_build_enrichment_payload_preserves_existing_job_type_and_salary_range() -> (
    None
):
    repo = FakeJobRepository()
    service = make_service(repo)
    job = make_job(
        skills=None,
        job_type="Contract",
        salary_range={"min": 100, "max": 120, "currency": "AUD", "period": "hour"},
        description_full=(
            "Full-time role requiring Python and fast api. Pay is $45/hr."
        ),
    )

    result = service.build_enrichment_payload(cast(Job, job))

    assert result == {"skills": ["Python"]}


@pytest.mark.asyncio
async def test_enrich_job_updates_only_when_skills_missing() -> None:
    repo = FakeJobRepository(
        jobs={
            1: make_job(id=1, skills=None, description_full="Python and fast api"),
            2: make_job(id=2, skills=["AWS"], description_full="Python and React"),
        }
    )
    service = make_service(repo)

    updated = await service.enrich_job(1)
    untouched = await service.enrich_job(2)

    assert updated is not None
    assert updated.skills == ["Python", "FastAPI"]
    assert untouched is not None
    assert untouched.skills == ["AWS"]
    assert [job_id for job_id, _ in repo.update_calls] == [1]


@pytest.mark.asyncio
async def test_enrich_job_updates_missing_fields_alongside_skills() -> None:
    repo = FakeJobRepository(
        jobs={
            1: make_job(
                id=1,
                title="Backend Engineer - Full-Time",
                skills=None,
                job_type=None,
                salary_range=None,
                description_full=(
                    "We need Python and fast api experience. Compensation is $45/hr."
                ),
            )
        }
    )
    service = make_service(repo)

    updated = await service.enrich_job(1)

    assert updated is not None
    assert updated.skills == ["Python", "FastAPI"]
    assert updated.job_type == "Full-Time"
    assert updated.salary_range == {
        "min": 45,
        "max": 45,
        "currency": "AUD",
        "period": "hour",
        "raw": "$45",
    }
    assert repo.update_calls == [
        (
            1,
            {
                "skills": ["Python", "FastAPI"],
                "job_type": "Full-Time",
                "salary_range": {
                    "min": 45,
                    "max": 45,
                    "currency": "AUD",
                    "period": "hour",
                    "raw": "$45",
                },
            },
        )
    ]


@pytest.mark.asyncio
async def test_enrich_jobs_with_missing_skills_returns_summary_counts() -> None:
    repo = FakeJobRepository(
        jobs={
            1: make_job(id=1, skills=None, description_full="Python and FastAPI"),
            2: make_job(id=2, skills=["Git"], description_full="Python and SQL"),
            3: make_job(id=3, skills=None, description_full="Strong communication"),
            4: make_job(id=4, skills=None, description_full="Docker and Redis"),
        },
        fail_update_ids={4},
    )
    service = make_service(repo)

    result = await service.enrich_jobs_with_missing_skills(limit=10)

    assert result == {"processed": 4, "enriched": 1, "skipped": 2, "failed": 1}


@pytest.mark.asyncio
async def test_repository_failure_maps_to_business_logic_error() -> None:
    repo = FakeJobRepository(jobs={1: make_job(id=1)}, fail_get_by_id=True)
    service = make_service(repo)

    with pytest.raises(BusinessLogicError, match="Failed to enrich job"):
        await service.enrich_job(1)
