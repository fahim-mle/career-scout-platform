"""Test factories for creating persisted model instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.job import Job


@dataclass(slots=True)
class JobFactory:
    """Factory helper for creating Job records in tests."""

    db: AsyncSession
    _counter: int = field(default=0, init=False)

    async def create(
        self,
        *,
        external_id: str | None = None,
        platform: str = "linkedin",
        title: str = "Software Engineer",
        company: str = "Tech Corp",
        location: str = "Brisbane, QLD",
        is_active: bool = True,
        posted_date: date | None = None,
    ) -> Job:
        """
        Create and persist a Job model using sensible defaults.
        
        Parameters:
            external_id (str | None): External identifier to use for the job. If None, a unique value of the form
                "test-job-{n}" is generated where `n` is an internal counter.
            posted_date (date | None): Date the job was posted; pass `None` to leave the field unset.
        
        Returns:
            job (Job): The persisted Job instance with its database state refreshed.
        """
        self._counter += 1
        job_external_id = external_id or f"test-job-{self._counter}"

        job = Job(
            external_id=job_external_id,
            platform=platform,
            url=f"https://{platform}.com/jobs/{job_external_id}",
            title=title,
            company=company,
            location=location,
            posted_date=posted_date,
            is_active=is_active,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job


@pytest_asyncio.fixture
async def job_factory(db_session: AsyncSession) -> JobFactory:
    """
    Provide a JobFactory bound to the current database session.
    
    Returns:
        JobFactory: A JobFactory instance bound to the provided AsyncSession.
    """
    return JobFactory(db=db_session)