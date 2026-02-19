"""Async unit tests for MatchScoreRepository."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.models.profile import Profile
from src.repositories.match_score import MatchScoreRepository
from tests.factories import JobFactory


def build_payload(
    *,
    relevance_score: int = 82,
    category: str = "Relevant",
    explanation: str = "Strong overlap in backend skills and years of experience.",
) -> dict[str, object]:
    """Build a valid match score payload for repository tests.

    Args:
        relevance_score: Score in the 0-100 range.
        category: Allowed match category.
        explanation: Human-readable rationale.

    Returns:
        Dictionary payload for create/update/upsert calls.
    """
    return {
        "relevance_score": relevance_score,
        "category": category,
        "explanation": explanation,
        "scored_at": datetime.now(timezone.utc),
    }


async def create_profile(db_session: AsyncSession, *, name: str = "Ada") -> Profile:
    """Create and persist a profile row for match score tests.

    Args:
        db_session: Active async SQLAlchemy session.
        name: Profile display name.

    Returns:
        Persisted Profile entity.
    """
    profile = Profile(
        name=name,
        location="Brisbane, QLD",
        experience_years=6,
        skills=["Python", "FastAPI", "SQLAlchemy"],
        preferences={"work_type": "remote"},
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_create_and_get_by_id(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Create persists row and lookup by id returns it."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)

    created = await repo.create(
        {"job_id": job.id, "profile_id": profile.id, **build_payload()}
    )
    found = await repo.get_by_id(created.id)

    assert found is not None
    assert found.id == created.id
    assert found.job_id == job.id
    assert found.profile_id == profile.id


@pytest.mark.asyncio
async def test_get_by_job_and_profile_returns_match(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Lookup by unique key returns existing score row."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)
    await repo.create({"job_id": job.id, "profile_id": profile.id, **build_payload()})

    found = await repo.get_by_job_and_profile(job.id, profile.id)

    assert found is not None
    assert found.job_id == job.id
    assert found.profile_id == profile.id


@pytest.mark.asyncio
async def test_update_success_and_missing_returns_none(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Update mutates existing row and returns None for missing id."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)
    created = await repo.create(
        {"job_id": job.id, "profile_id": profile.id, **build_payload()}
    )

    updated = await repo.update(
        created.id,
        {"relevance_score": 90, "category": "Most Relevant"},
    )
    missing = await repo.update(999_999, {"relevance_score": 50})

    assert updated is not None
    assert updated.relevance_score == 90
    assert updated.category == "Most Relevant"
    assert missing is None


@pytest.mark.asyncio
async def test_duplicate_create_raises_repository_error(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Duplicate (job_id, profile_id) create raises RepositoryError."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)
    await repo.create({"job_id": job.id, "profile_id": profile.id, **build_payload()})

    with pytest.raises(RepositoryError, match="integrity error"):
        await repo.create(
            {
                "job_id": job.id,
                "profile_id": profile.id,
                **build_payload(relevance_score=40, category="Somewhat Relevant"),
            }
        )


@pytest.mark.asyncio
async def test_upsert_creates_when_missing(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert inserts when the unique key does not exist."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)

    upserted = await repo.upsert_by_job_and_profile(
        job_id=job.id,
        profile_id=profile.id,
        payload=build_payload(),
    )

    assert upserted.id is not None
    assert upserted.job_id == job.id
    assert upserted.profile_id == profile.id


@pytest.mark.asyncio
async def test_upsert_fills_missing_fields_without_clobbering(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Upsert preserves existing non-missing values and fills gaps only."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)
    first = await repo.create(
        {
            "job_id": job.id,
            "profile_id": profile.id,
            **build_payload(
                relevance_score=25, category="Somewhat Relevant", explanation=""
            ),
        }
    )

    second = await repo.upsert_by_job_and_profile(
        job_id=job.id,
        profile_id=profile.id,
        payload=build_payload(
            relevance_score=99,
            category="Most Relevant",
            explanation="Now populated explanation.",
        ),
    )

    assert second.id == first.id
    assert second.relevance_score == 25
    assert second.category == "Somewhat Relevant"
    assert second.explanation == "Now populated explanation."


@pytest.mark.asyncio
async def test_list_for_jobs_supports_optional_profile_filter(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """list_for_jobs returns requested jobs and applies profile filter."""
    job_one = await job_factory.create(external_id="ms-job-1")
    job_two = await job_factory.create(external_id="ms-job-2")
    profile_one = await create_profile(db_session, name="Ada")
    profile_two = await create_profile(db_session, name="Grace")
    repo = MatchScoreRepository(db_session)

    await repo.create(
        {
            "job_id": job_one.id,
            "profile_id": profile_one.id,
            **build_payload(relevance_score=70),
        }
    )
    await repo.create(
        {
            "job_id": job_one.id,
            "profile_id": profile_two.id,
            **build_payload(relevance_score=60),
        }
    )
    await repo.create(
        {
            "job_id": job_two.id,
            "profile_id": profile_one.id,
            **build_payload(relevance_score=80),
        }
    )

    all_rows = await repo.list_for_jobs([job_one.id, job_two.id])
    filtered_rows = await repo.list_for_jobs(
        [job_one.id, job_two.id],
        profile_id=profile_one.id,
    )

    assert len(all_rows) == 3
    assert {(row.job_id, row.profile_id) for row in all_rows} == {
        (job_one.id, profile_one.id),
        (job_one.id, profile_two.id),
        (job_two.id, profile_one.id),
    }
    assert len(filtered_rows) == 2
    assert {row.profile_id for row in filtered_rows} == {profile_one.id}


@pytest.mark.asyncio
async def test_update_and_upsert_validate_protected_fields(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Update and upsert reject protected fields in payloads."""
    job = await job_factory.create()
    profile = await create_profile(db_session)
    repo = MatchScoreRepository(db_session)
    score = await repo.create(
        {"job_id": job.id, "profile_id": profile.id, **build_payload()}
    )

    with pytest.raises(ValueError, match="protected"):
        await repo.update(score.id, {"job_id": job.id + 1})

    with pytest.raises(ValueError, match="protected fields"):
        await repo.upsert_by_job_and_profile(
            job_id=job.id,
            profile_id=profile.id,
            payload={"profile_id": profile.id + 1, **build_payload()},
        )
