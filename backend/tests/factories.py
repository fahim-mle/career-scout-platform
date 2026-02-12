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
        """Create and persist a Job model with sensible defaults."""
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
    """Provide a JobFactory bound to the current DB session."""
    return JobFactory(db=db_session)
