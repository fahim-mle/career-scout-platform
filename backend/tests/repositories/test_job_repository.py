"""Async unit tests for JobRepository."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateJobError, RepositoryError
from src.repositories.job import JobRepository
from tests.factories import JobFactory


def build_job_data(
    *,
    external_id: str,
    platform: str = "linkedin",
    title: str = "Backend Engineer",
    company: str = "Career Scout",
    location: str = "Brisbane",
) -> dict[str, object]:
    """
    Create a valid job payload dictionary for repository create calls.
    
    Parameters:
        external_id (str): Identifier of the job in the external platform.
        platform (str): Source platform name (used to form the job URL); defaults to "linkedin".
    
    Returns:
        dict: A job payload dictionary with keys `external_id`, `platform`, `url`, `title`, `company`, and `location`.
    """
    return {
        "external_id": external_id,
        "platform": platform,
        "url": f"https://{platform}.com/jobs/{external_id}",
        "title": title,
        "company": company,
        "location": location,
    }


@pytest.mark.asyncio
async def test_get_by_id_returns_job_when_found(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create(title="Platform Engineer")
    repo = JobRepository(db_session)

    found = await repo.get_by_id(job.id)

    assert found is not None
    assert found.id == job.id
    assert found.title == "Platform Engineer"


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)

    found = await repo.get_by_id(999_999)

    assert found is None


@pytest.mark.asyncio
async def test_get_all_filters_by_active_platform_and_pagination(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    older = await job_factory.create(platform="linkedin", title="Older")
    newer = await job_factory.create(platform="linkedin", title="Newer")
    await job_factory.create(platform="seek", title="Seek role")
    await job_factory.create(platform="linkedin", title="Inactive", is_active=False)
    repo = JobRepository(db_session)

    linkedin_jobs = await repo.get_all(platform="linkedin", is_active=True)
    page_two = await repo.get_all(skip=1, limit=1, platform="linkedin", is_active=True)

    assert [job.id for job in linkedin_jobs] == [newer.id, older.id]
    assert len(page_two) == 1
    assert page_two[0].id == older.id


@pytest.mark.asyncio
async def test_get_all_rejects_invalid_pagination(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)

    with pytest.raises(ValueError, match="skip"):
        await repo.get_all(skip=-1)
    with pytest.raises(ValueError, match="at least 1"):
        await repo.get_all(limit=0)
    with pytest.raises(ValueError, match="cannot exceed 1000"):
        await repo.get_all(limit=1001)


@pytest.mark.asyncio
async def test_create_persists_job(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)

    created = await repo.create(build_job_data(external_id="create-success"))

    assert created.id is not None
    assert created.external_id == "create-success"


@pytest.mark.asyncio
async def test_create_rejects_protected_fields(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)
    payload = build_job_data(external_id="protected-create")
    payload["id"] = "99"

    with pytest.raises(ValueError, match="protected fields"):
        await repo.create(payload)


@pytest.mark.asyncio
async def test_create_raises_duplicate_error(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    await job_factory.create(external_id="dup-1", platform="linkedin")
    repo = JobRepository(db_session)

    with pytest.raises(DuplicateJobError):
        await repo.create(build_job_data(external_id="dup-1", platform="linkedin"))


@pytest.mark.asyncio
async def test_create_raises_repository_error_for_other_integrity_failures(
    db_session: AsyncSession,
) -> None:
    """
    Verifies that attempting to create a job with a payload that violates a database integrity constraint (for example, a missing required `title`) raises a RepositoryError with a message containing "integrity error".
    """
    repo = JobRepository(db_session)
    invalid_payload: dict[str, object] = build_job_data(external_id="missing-title")
    invalid_payload["title"] = None

    with pytest.raises(RepositoryError, match="integrity error"):
        await repo.create(invalid_payload)


@pytest.mark.asyncio
async def test_create_propagates_model_validation_error(
    db_session: AsyncSession,
) -> None:
    repo = JobRepository(db_session)

    with pytest.raises(ValueError, match="Invalid platform"):
        await repo.create(
            build_job_data(external_id="bad-platform", platform="monster")
        )


@pytest.mark.asyncio
async def test_update_modifies_allowed_fields(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create(title="Old title", company="Old Co")
    repo = JobRepository(db_session)

    updated = await repo.update(job.id, {"title": "New title", "company": "New Co"})

    assert updated is not None
    assert updated.title == "New title"
    assert updated.company == "New Co"


@pytest.mark.asyncio
async def test_update_returns_none_when_missing(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)

    updated = await repo.update(3_333, {"title": "Nope"})

    assert updated is None


@pytest.mark.asyncio
async def test_update_rejects_protected_or_unsafe_fields(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create()
    repo = JobRepository(db_session)

    with pytest.raises(ValueError, match="protected"):
        await repo.update(job.id, {"created_at": "2024-01-01"})
    with pytest.raises(ValueError, match="Unknown or unsafe"):
        await repo.update(job.id, {"_hidden": "bad"})
    with pytest.raises(ValueError, match="Unknown or unsafe"):
        await repo.update(job.id, {"not_a_column": "bad"})


@pytest.mark.asyncio
async def test_update_raises_duplicate_error(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    first = await job_factory.create(external_id="dup-a", platform="linkedin")
    second = await job_factory.create(external_id="dup-b", platform="linkedin")
    repo = JobRepository(db_session)

    with pytest.raises(DuplicateJobError):
        await repo.update(second.id, {"external_id": first.external_id})


@pytest.mark.asyncio
async def test_update_raises_repository_error_for_non_duplicate_integrity(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create(title="Still valid")
    repo = JobRepository(db_session)

    with pytest.raises(RepositoryError, match="integrity error"):
        await repo.update(job.id, {"title": None})


@pytest.mark.asyncio
async def test_update_propagates_model_validation_error(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create()
    repo = JobRepository(db_session)

    with pytest.raises(ValueError, match="salary_range"):
        await repo.update(job.id, {"salary_range": {"min": 100_000, "currency": "AUD"}})


@pytest.mark.asyncio
async def test_delete_removes_existing_job(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create()
    repo = JobRepository(db_session)

    deleted = await repo.delete(job.id)
    still_there = await repo.get_by_id(job.id)

    assert deleted is True
    assert still_there is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)

    deleted = await repo.delete(44_444)

    assert deleted is False


@pytest.mark.asyncio
async def test_get_by_external_id_returns_match(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    job = await job_factory.create(external_id="source-99", platform="indeed")
    repo = JobRepository(db_session)

    found = await repo.get_by_external_id("source-99", "indeed")

    assert found is not None
    assert found.id == job.id


@pytest.mark.asyncio
async def test_get_by_external_id_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    repo = JobRepository(db_session)

    found = await repo.get_by_external_id("missing", "linkedin")

    assert found is None


@pytest.mark.asyncio
async def test_get_by_id_wraps_sqlalchemy_error(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = JobRepository(db_session)

    async def failing_execute(*_args: object, **_kwargs: object) -> object:
        """
        Force a SQLAlchemyError with message "boom".
        
        Raises:
            SQLAlchemyError: Always raised with message "boom".
        """
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "execute", failing_execute)

    with pytest.raises(RepositoryError, match="Failed to fetch job by id"):
        await repo.get_by_id(1)


@pytest.mark.asyncio
async def test_get_all_wraps_sqlalchemy_error(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = JobRepository(db_session)

    async def failing_execute(*_args: object, **_kwargs: object) -> object:
        """
        Force a SQLAlchemyError with message "boom".
        
        Raises:
            SQLAlchemyError: Always raised with message "boom".
        """
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(repo.db, "execute", failing_execute)

    with pytest.raises(RepositoryError, match="Failed to fetch jobs"):
        await repo.get_all()


@pytest.mark.asyncio
async def test_create_accepts_optional_json_and_dates(db_session: AsyncSession) -> None:
    repo = JobRepository(db_session)
    payload = build_job_data(external_id="rich-data")
    payload_with_optional: dict[str, object] = {
        **payload,
        "posted_date": date(2026, 2, 1),
        "skills": ["Python", "SQLAlchemy"],
        "salary_range": {"min": 100000, "max": 140000, "currency": "AUD"},
    }

    created = await repo.create(payload_with_optional)

    assert created.posted_date == date(2026, 2, 1)
    assert created.skills == ["Python", "SQLAlchemy"]
    assert created.salary_range == {"min": 100000, "max": 140000, "currency": "AUD"}