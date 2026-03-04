"""Async unit tests for JobEnrichmentRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.repositories.job_enrichment import JobEnrichmentRepository
from tests.factories import JobFactory


def build_payload(*, status: str = "pending") -> dict[str, object]:
    """Build a valid enrichment payload for repository tests.

    Args:
        status: Enrichment status value.

    Returns:
        Dictionary payload for create/update calls.
    """
    return {
        "status": status,
        "skills": ["Python", "FastAPI"],
        "job_type": "Full-Time",
        "salary_min": 100000,
        "salary_max": 140000,
        "salary_currency": "AUD",
        "salary_period": "year",
        "salary_raw": "$100000 - $140000",
        "location_normalized": "brisbane,qld,au",
        "confidence_overall": 0.88,
        "confidence_by_field": {"skills": 0.9, "job_type": 0.8},
    }


@pytest.mark.asyncio
async def test_create_persists_enrichment(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Create stores a new job enrichment row."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)

    created = await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v1",
            **build_payload(),
        }
    )

    assert created.id is not None
    assert created.job_id == job.id
    assert created.extractor_version == "heuristic-v1"
    assert created.status == "pending"


@pytest.mark.asyncio
async def test_update_modifies_allowed_fields(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Update changes mutable enrichment fields."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)
    created = await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v1",
            **build_payload(status="failed"),
        }
    )

    updated = await repo.update(
        created.id, {"status": "completed", "skills": ["Python"]}
    )

    assert updated is not None
    assert updated.status == "completed"
    assert updated.skills == ["Python"]


@pytest.mark.asyncio
async def test_get_by_job_and_version_returns_match(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Lookup by (job_id, extractor_version) returns row when present."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)
    await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v1",
            **build_payload(),
        }
    )

    found = await repo.get_by_job_and_version(job.id, "heuristic-v1")

    assert found is not None
    assert found.job_id == job.id


@pytest.mark.asyncio
async def test_get_latest_by_job_id_returns_most_recent(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Latest lookup returns the most recent enrichment for a job."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)
    first = await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v1",
            **build_payload(status="pending"),
        }
    )

    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    second = await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v2",
            **build_payload(status="completed"),
            "enriched_at": later,
        }
    )

    latest = await repo.get_latest_by_job_id(job.id)

    assert latest is not None
    assert latest.id == second.id
    assert latest.id != first.id


@pytest.mark.asyncio
async def test_upsert_by_job_and_version_creates_when_missing(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert inserts a new row when key does not exist."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)

    upserted = await repo.upsert_by_job_and_version(
        job_id=job.id,
        extractor_version="heuristic-v1",
        payload=build_payload(status="pending"),
    )

    assert upserted.id is not None
    assert upserted.status == "pending"


@pytest.mark.asyncio
async def test_upsert_by_job_and_version_fills_missing_without_clobbering(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert preserves populated fields and only fills missing fields."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)
    first = await repo.upsert_by_job_and_version(
        job_id=job.id,
        extractor_version="heuristic-v1",
        payload={
            "status": "pending",
            "skills": ["Python"],
            "salary_min": 120000,
            "salary_max": 150000,
            "salary_currency": "AUD",
        },
    )

    second = await repo.upsert_by_job_and_version(
        job_id=job.id,
        extractor_version="heuristic-v1",
        payload={
            "status": "completed",
            "skills": ["Go"],
            "job_type": "Full-Time",
            "salary_min": 1,
            "salary_max": 2,
            "salary_currency": "USD",
        },
    )

    assert second.id == first.id
    assert second.status == "pending"
    assert second.skills == ["Python"]
    assert second.job_type == "Full-Time"
    assert second.salary_min == 120000
    assert second.salary_max == 150000
    assert second.salary_currency == "AUD"


@pytest.mark.asyncio
async def test_upsert_by_job_and_version_recovers_from_create_race(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert refetches and returns row when create loses a race."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)
    recovered = await repo.create(
        {
            "job_id": job.id,
            "extractor_version": "heuristic-v1",
            **build_payload(status="completed"),
        }
    )

    with (
        patch.object(
            repo,
            "get_by_job_and_version",
            new=AsyncMock(side_effect=[None, recovered]),
        ) as mock_get,
        patch.object(
            repo,
            "create",
            new=AsyncMock(side_effect=RepositoryError("create failed")),
        ) as mock_create,
    ):
        result = await repo.upsert_by_job_and_version(
            job_id=job.id,
            extractor_version="heuristic-v1",
            payload=build_payload(status="pending"),
        )

    assert result.id == recovered.id
    assert mock_create.await_count == 1
    assert mock_get.await_count == 2


@pytest.mark.asyncio
async def test_upsert_by_job_and_version_reraises_create_error_when_refetch_missing(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert re-raises create error when refetch cannot recover row."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)

    with (
        patch.object(
            repo,
            "get_by_job_and_version",
            new=AsyncMock(side_effect=[None, None]),
        ) as mock_get,
        patch.object(
            repo,
            "create",
            new=AsyncMock(side_effect=RepositoryError("create failed")),
        ) as mock_create,
    ):
        with pytest.raises(RepositoryError, match="create failed"):
            await repo.upsert_by_job_and_version(
                job_id=job.id,
                extractor_version="heuristic-v1",
                payload=build_payload(status="pending"),
            )

    assert mock_create.await_count == 1
    assert mock_get.await_count == 2


@pytest.mark.asyncio
async def test_upsert_rejects_job_id_inside_payload(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert rejects payload attempts to override protected job_id."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)

    with pytest.raises(ValueError, match="protected fields"):
        await repo.upsert_by_job_and_version(
            job_id=job.id,
            extractor_version="heuristic-v1",
            payload={"job_id": job.id + 1, **build_payload()},
        )


@pytest.mark.asyncio
async def test_upsert_rejects_extractor_version_inside_payload(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert rejects payload attempts to override protected extractor version."""
    job = await job_factory.create()
    repo = JobEnrichmentRepository(db_session)

    with pytest.raises(ValueError, match="protected fields"):
        await repo.upsert_by_job_and_version(
            job_id=job.id,
            extractor_version="heuristic-v1",
            payload={"extractor_version": "heuristic-v999", **build_payload()},
        )


@pytest.mark.asyncio
async def test_list_by_job_ids_returns_rows_for_requested_jobs(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """List query returns enrichments for provided job ids."""
    job_one = await job_factory.create(external_id="job-1")
    job_two = await job_factory.create(external_id="job-2")
    repo = JobEnrichmentRepository(db_session)
    await repo.create(
        {
            "job_id": job_one.id,
            "extractor_version": "heuristic-v1",
            **build_payload(),
        }
    )
    await repo.create(
        {
            "job_id": job_two.id,
            "extractor_version": "heuristic-v1",
            **build_payload(status="failed"),
        }
    )

    rows = await repo.list_by_job_ids([job_one.id, job_two.id])

    assert len(rows) == 2
    assert {row.job_id for row in rows} == {job_one.id, job_two.id}


@pytest.mark.asyncio
async def test_create_raises_repository_error_for_invalid_fk(
    db_session: AsyncSession,
) -> None:
    """Create wraps foreign key violations as RepositoryError."""
    repo = JobEnrichmentRepository(db_session)

    with pytest.raises(RepositoryError, match="integrity error"):
        await repo.create(
            {
                "job_id": 999999,
                "extractor_version": "heuristic-v1",
                **build_payload(),
            }
        )
