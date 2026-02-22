"""Unit tests for JobEnrichmentService extraction and persistence orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.core.exceptions import BusinessLogicError, RepositoryError
from src.models.job import Job
from src.models.job_enrichment import JobEnrichment
from src.repositories.job import JobRepository
from src.repositories.job_enrichment import JobEnrichmentRepository
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
    """In-memory async repository stub for raw job reads."""

    jobs: dict[int, SimpleNamespace] = field(default_factory=dict)
    fail_get_by_id: bool = False
    fail_get_all: bool = False

    async def get_by_id(self, job_id: int) -> SimpleNamespace | None:
        """Fetch one fake job by id.

        Args:
            job_id: Target job id.

        Returns:
            Job object when found, otherwise None.

        Raises:
            RepositoryError: If configured to fail.
        """
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
        """Return filtered fake jobs for batch enrichment.

        Args:
            skip: Pagination offset.
            limit: Pagination size.
            platform: Optional platform filter.
            is_active: Active status filter.

        Returns:
            Matching fake jobs.

        Raises:
            RepositoryError: If configured to fail.
        """
        if self.fail_get_all:
            raise RepositoryError("repo get_all failed")

        items = [job for job in self.jobs.values() if job.is_active is is_active]
        if platform is not None:
            items = [job for job in items if job.platform == platform]
        items.sort(key=lambda item: item.id)
        return items[skip : skip + limit]


@dataclass
class FakeJobEnrichmentRepository:
    """In-memory async repository stub for processed enrichment writes."""

    rows: dict[tuple[int, str], SimpleNamespace] = field(default_factory=dict)
    fail_upsert_ids: set[int] = field(default_factory=set)
    upsert_calls: list[tuple[int, str, dict[str, Any]]] = field(default_factory=list)
    _counter: int = 0

    async def upsert_by_job_and_version(
        self,
        job_id: int,
        extractor_version: str,
        payload: dict[str, Any],
    ) -> SimpleNamespace:
        """Insert or merge enrichment by job/version key.

        Args:
            job_id: Target raw job id.
            extractor_version: Extractor version key.
            payload: Candidate enrichment payload.

        Returns:
            Persisted enrichment row.

        Raises:
            RepositoryError: If configured to fail.
        """
        self.upsert_calls.append((job_id, extractor_version, payload.copy()))
        if job_id in self.fail_upsert_ids:
            raise RepositoryError("repo upsert failed")

        key = (job_id, extractor_version)
        current = self.rows.get(key)
        if current is None:
            self._counter += 1
            now = datetime.now(timezone.utc)
            record_data = {
                "id": self._counter,
                "job_id": job_id,
                "extractor_version": extractor_version,
                "created_at": now,
                "updated_at": now,
                "enriched_at": now,
                **payload,
            }
            row = SimpleNamespace(**record_data)
            self.rows[key] = row
            return row

        merged = current.__dict__.copy()
        for field_name, value in payload.items():
            if self._is_missing(
                merged.get(field_name), field_name
            ) and not self._is_missing(value, field_name):
                merged[field_name] = value

        merged["updated_at"] = datetime.now(timezone.utc)
        row = SimpleNamespace(**merged)
        self.rows[key] = row
        return row

    @staticmethod
    def _is_missing(value: object, field: str) -> bool:
        """Determine whether a test value is considered missing.

        Args:
            value: Candidate value.
            field: Field name for type-aware checks.

        Returns:
            True when value is missing.
        """
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if field == "skills" and isinstance(value, list):
            return len(value) == 0
        if field == "confidence_by_field" and isinstance(value, dict):
            return len(value) == 0
        return False


def make_service(
    job_repo: FakeJobRepository,
    enrichment_repo: FakeJobEnrichmentRepository,
) -> JobEnrichmentService:
    """Create service with casted repository test doubles.

    Args:
        job_repo: Fake raw jobs repository.
        enrichment_repo: Fake enrichment repository.

    Returns:
        Configured service instance.
    """
    return JobEnrichmentService(
        cast(JobRepository, job_repo),
        cast(JobEnrichmentRepository, enrichment_repo),
        extractor_version="test-v1",
    )


def test_extract_skills_from_description_finds_canonical_from_aliases() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())
    description = (
        "We need PYTHON and strong React.js UI skills, plus nodejs APIs, "
        "Postgres tuning, docker workflows, and aws cloud operations."
    )

    result = service.extract_skills_from_description(description)

    assert result == ["Python", "React", "Node.js", "PostgreSQL", "Docker", "AWS"]


def test_extract_skills_from_description_avoids_punctuation_false_positives() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_skills_from_description(
        "Experience with react-native and node_js wrappers is preferred."
    )

    assert result == []


def test_extract_job_type_from_text_detects_and_normalizes() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_job_type_from_text(
        "Senior Backend Engineer (full-time) with async Python experience."
    )

    assert result == "Full-Time"


def test_extract_salary_range_from_text_parses_explicit_yearly_range() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

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


def test_extract_salary_range_preserves_raw_text_for_whitespace_heavy_ranges() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_salary_range_from_text(
        "Salary: AUD   120000 to 150000 per annum based on experience."
    )

    assert result is not None
    assert result["raw"] == "AUD   120000 to 150000"


def test_extract_salary_range_preserves_raw_text_for_single_salary() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_salary_range_from_text(
        "Compensation is AUD   45 per hour for this role."
    )

    assert result is not None
    assert result["raw"] == "AUD   45"


def test_extract_description_sections_groups_headings_and_bullets() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_description_sections(
        """
        About the job
        Build and scale backend services.

        Requirements
        - Python
        - FastAPI
        """
    )

    assert result == [
        {
            "title": "About",
            "items": ["Build and scale backend services."],
        },
        {
            "title": "Requirements",
            "items": ["Python", "FastAPI"],
        },
    ]


def test_extract_description_sections_returns_empty_for_blank_input() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_description_sections("   \n\t  ")

    assert result == []


def test_extract_description_sections_drops_empty_heading_section() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_description_sections(
        """
        About the job
        Requirements
        - Python
        """
    )

    assert result == [
        {
            "title": "Requirements",
            "items": ["Python"],
        }
    ]


def test_extract_description_sections_deduplicates_adjacent_items_case_insensitive() -> (
    None
):
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service.extract_description_sections(
        """
        Requirements
        - Python
        - python
        - FastAPI
        - FASTAPI
        """
    )

    assert result == [
        {
            "title": "Requirements",
            "items": ["Python", "FastAPI"],
        }
    ]


def test_build_enrichment_payload_maps_salary_range_to_processed_columns() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())
    job = make_job(
        title="Backend Engineer - Full-Time",
        description_full="Python and FastAPI required. Compensation is $45/hr.",
    )

    result = service.build_enrichment_payload(cast(Job, job))

    assert result["skills"] == ["Python", "FastAPI"]
    assert result["job_type"] == "Full-Time"
    assert result["salary_min"] == 45
    assert result["salary_max"] == 45
    assert result["salary_currency"] == "AUD"
    assert result["salary_period"] == "hour"
    assert result["salary_raw"] == "$45"
    assert isinstance(result.get("description_sections"), list)
    assert result["description_sections"][0]["title"] == "Overview"
    assert result["status"] == "success"


def test_salary_range_to_enrichment_fields_keeps_salary_period_nullable() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = service._salary_range_to_enrichment_fields(
        {
            "min": 120000,
            "max": 150000,
            "currency": "AUD",
            "raw": "AUD 120000 to 150000",
        }
    )

    assert result["salary_period"] is None


def test_build_enrichment_payload_marks_failed_when_no_text() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())
    job = make_job(description_full=None, description_short=None, title="")

    result = service.build_enrichment_payload(cast(Job, job))

    assert result == {"status": "failed"}


@pytest.mark.asyncio
async def test_enrich_job_writes_processed_row_and_returns_enrichment_record() -> None:
    job_repo = FakeJobRepository(
        jobs={
            1: make_job(
                id=1,
                title="Backend Engineer - Full-Time",
                description_full=(
                    "We need Python and FastAPI experience. Compensation is $45/hr."
                ),
            )
        }
    )
    enrichment_repo = FakeJobEnrichmentRepository()
    service = make_service(job_repo, enrichment_repo)

    enrichment = await service.enrich_job(1)

    assert enrichment is not None
    assert enrichment.job_id == 1
    assert enrichment.extractor_version == "test-v1"
    assert enrichment.skills == ["Python", "FastAPI"]
    assert enrichment.job_type == "Full-Time"
    assert enrichment.salary_min == 45
    assert enrichment.status == "success"


@pytest.mark.asyncio
async def test_enrich_job_is_idempotent_and_does_not_clobber_populated_fields() -> None:
    job_repo = FakeJobRepository(
        jobs={
            1: make_job(
                id=1,
                title="Backend Engineer - Full-Time",
                description_full="Python role. Compensation is $45/hr.",
            )
        }
    )
    enrichment_repo = FakeJobEnrichmentRepository()
    service = make_service(job_repo, enrichment_repo)

    first = await service.enrich_job(1)
    assert first is not None

    job_repo.jobs[1] = make_job(
        id=1,
        title="Backend Engineer",
        description_full="General role with no compensation details.",
    )
    second = await service.enrich_job(1)

    assert second is not None
    assert second.skills == ["Python"]
    assert second.salary_min == 45
    assert second.job_type == "Full-Time"


@pytest.mark.asyncio
async def test_enrich_jobs_with_missing_skills_returns_summary_counts() -> None:
    job_repo = FakeJobRepository(
        jobs={
            1: make_job(id=1, description_full="Python and FastAPI"),
            2: make_job(id=2, description_full="Strong communication only"),
            3: make_job(id=3, description_full="Salary is $55/hr and AWS required"),
            4: make_job(id=4, description_full="Docker and Redis"),
        }
    )
    enrichment_repo = FakeJobEnrichmentRepository(fail_upsert_ids={4})
    service = make_service(job_repo, enrichment_repo)

    result = await service.enrich_jobs_with_missing_skills(limit=10)

    assert result == {"processed": 4, "enriched": 2, "skipped": 1, "failed": 1}


@pytest.mark.asyncio
async def test_repository_failure_maps_to_business_logic_error() -> None:
    job_repo = FakeJobRepository(jobs={1: make_job(id=1)}, fail_get_by_id=True)
    enrichment_repo = FakeJobEnrichmentRepository()
    service = make_service(job_repo, enrichment_repo)

    with pytest.raises(BusinessLogicError, match="Failed to enrich job"):
        await service.enrich_job(1)


@pytest.mark.asyncio
async def test_enrich_job_returns_none_when_job_missing() -> None:
    service = make_service(FakeJobRepository(), FakeJobEnrichmentRepository())

    result = await service.enrich_job(999)

    assert result is None
