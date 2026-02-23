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
async def test_create_rejects_raw_metadata_field_alias(
    db_session: AsyncSession,
) -> None:
    """Repository create should reject raw DB metadata field name."""
    repo = JobRepository(db_session)
    payload = build_job_data(external_id="metadata-alias-create")
    payload["metadata"] = {"platform": "linkedin"}

    with pytest.raises(ValueError, match="Unknown or unsafe"):
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
async def test_update_persists_raw_html_and_metadata_fields(
    db_session: AsyncSession,
    job_factory: JobFactory,
) -> None:
    """Repository update should persist raw scraped payload fields."""
    job = await job_factory.create()
    repo = JobRepository(db_session)

    updated = await repo.update(
        job.id,
        {
            "scraped_jobs": "<main><p>About the job</p></main>",
            "platform_metadata": {
                "platform": "linkedin",
                "location": "Sydney",
                "date_posted": "1 day ago",
            },
        },
    )

    assert updated is not None
    assert updated.scraped_jobs == "<main><p>About the job</p></main>"
    assert updated.platform_metadata == {
        "platform": "linkedin",
        "location": "Sydney",
        "date_posted": "1 day ago",
    }


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
    with pytest.raises(ValueError, match="Unknown or unsafe"):
        await repo.update(job.id, {"metadata": {"platform": "linkedin"}})


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
        "scraped_jobs": "raw linkedin payload",
        "platform_metadata": {
            "posted_date_text": "2 days ago",
            "number_of_applicants": "37 applicants",
            "promoted_by_hirer": True,
            "actively_reviewing_applicants": False,
            "platform": "linkedin",
        },
    }

    created = await repo.create(payload_with_optional)

    assert created.posted_date == date(2026, 2, 1)
    assert created.skills == ["Python", "SQLAlchemy"]
    assert created.salary_range == {"min": 100000, "max": 140000, "currency": "AUD"}
    assert created.scraped_jobs == "raw linkedin payload"
    assert created.platform_metadata == {
        "posted_date_text": "2 days ago",
        "number_of_applicants": "37 applicants",
        "promoted_by_hirer": True,
        "actively_reviewing_applicants": False,
        "platform": "linkedin",
    }


# ── New filter tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_all_filters_by_job_type(
    db_session: AsyncSession,
) -> None:
    """get_all should return only jobs matching the job_type filter (case-insensitive)."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "jt-fulltime-1",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/jt-fulltime-1",
            "title": "Full-time Dev",
            "company": "Corp A",
            "location": "Sydney",
            "job_type": "Full-time (Permanent)",
        }
    )
    await repo.create(
        {
            "external_id": "jt-contract-1",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/jt-contract-1",
            "title": "Contract Dev",
            "company": "Corp B",
            "location": "Melbourne",
            "job_type": "Contract",
        }
    )

    results = await repo.get_all(job_type="full-time")

    titles = [j.title for j in results]
    assert "Full-time Dev" in titles
    assert "Contract Dev" not in titles


@pytest.mark.asyncio
async def test_get_all_filters_job_type_case_insensitive(
    db_session: AsyncSession,
) -> None:
    """job_type filter should match regardless of casing."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "jt-ci-1",
            "platform": "linkedin",
            "url": "https://linkedin.com/jobs/jt-ci-1",
            "title": "CI Job",
            "company": "Corp",
            "location": "Brisbane",
            "job_type": "Full-time",
        }
    )

    upper = await repo.get_all(job_type="FULL-TIME")
    lower = await repo.get_all(job_type="full-time")

    assert any(j.title == "CI Job" for j in upper)
    assert any(j.title == "CI Job" for j in lower)


@pytest.mark.asyncio
async def test_get_all_search_matches_title(
    db_session: AsyncSession,
) -> None:
    """search param should filter by title substring (case-insensitive)."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "srch-eng-1",
            "platform": "indeed",
            "url": "https://indeed.com/jobs/srch-eng-1",
            "title": "Senior Python Engineer",
            "company": "Acme",
            "location": "Remote",
        }
    )
    await repo.create(
        {
            "external_id": "srch-des-1",
            "platform": "indeed",
            "url": "https://indeed.com/jobs/srch-des-1",
            "title": "UI Designer",
            "company": "Acme",
            "location": "Sydney",
        }
    )

    results = await repo.get_all(search="python")

    titles = [j.title for j in results]
    assert "Senior Python Engineer" in titles
    assert "UI Designer" not in titles


@pytest.mark.asyncio
async def test_get_all_search_matches_company(
    db_session: AsyncSession,
) -> None:
    """search param should also match on company name."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "srch-corp-1",
            "platform": "linkedin",
            "url": "https://linkedin.com/jobs/srch-corp-1",
            "title": "Engineer",
            "company": "Globex Corporation",
            "location": "Springfield",
        }
    )
    await repo.create(
        {
            "external_id": "srch-corp-2",
            "platform": "linkedin",
            "url": "https://linkedin.com/jobs/srch-corp-2",
            "title": "Engineer",
            "company": "Initech",
            "location": "Miami",
        }
    )

    results = await repo.get_all(search="globex")

    companies = [j.company for j in results]
    assert "Globex Corporation" in companies
    assert "Initech" not in companies


@pytest.mark.asyncio
async def test_get_all_search_matches_location(
    db_session: AsyncSession,
) -> None:
    """search param should also match on location."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "srch-loc-1",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/srch-loc-1",
            "title": "Data Analyst",
            "company": "Corp",
            "location": "Gold Coast, QLD",
        }
    )
    await repo.create(
        {
            "external_id": "srch-loc-2",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/srch-loc-2",
            "title": "Data Analyst",
            "company": "Corp",
            "location": "Sydney, NSW",
        }
    )

    results = await repo.get_all(search="Gold Coast")

    locations = [j.location for j in results]
    assert "Gold Coast, QLD" in locations
    assert "Sydney, NSW" not in locations


@pytest.mark.asyncio
async def test_get_all_no_results_when_search_matches_nothing(
    db_session: AsyncSession,
) -> None:
    """search param that matches nothing should return an empty list."""
    repo = JobRepository(db_session)

    results = await repo.get_all(search="xyzzy-guaranteed-no-match")

    assert results == []


@pytest.mark.asyncio
async def test_get_all_ignores_blank_search_and_job_type(
    db_session: AsyncSession,
) -> None:
    """Blank search and job_type values should be treated as no filters."""
    repo = JobRepository(db_session)
    await repo.create(
        {
            "external_id": "blank-filter-1",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/blank-filter-1",
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Brisbane",
            "job_type": "Contract",
        }
    )
    await repo.create(
        {
            "external_id": "blank-filter-2",
            "platform": "seek",
            "url": "https://seek.com.au/jobs/blank-filter-2",
            "title": "Data Engineer",
            "company": "Acme",
            "location": "Sydney",
            "job_type": "Full-time",
        }
    )

    results = await repo.get_all(job_type="   ", search="   ")

    assert len(results) == 2
