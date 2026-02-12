"""Data access repository for Job entities."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DuplicateJobError, RepositoryError
from src.models.job import Job
from src.repositories.base import BaseRepository

PROTECTED_UPDATE_FIELDS = frozenset({"id", "created_at", "updated_at"})
PROTECTED_CREATE_FIELDS = frozenset({"id", "created_at"})


class JobRepository(BaseRepository[Job]):
    """Repository responsible for job table persistence operations."""

    def __init__(self, db: AsyncSession):
        """Initialize JobRepository.

        Args:
            db: Active asynchronous SQLAlchemy session.
        """
        super().__init__(db=db, model_type=Job)
        self._column_names = {column.key for column in Job.__table__.columns}

    async def get_by_id(self, job_id: int) -> Job | None:
        """Fetch a single job by primary key.

        Args:
            job_id: Job primary key.

        Returns:
            The matching Job when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(repository=self.__class__.__name__, job_id=job_id)
        log.debug("Fetching job by id")

        try:
            result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            log.bind(found=job is not None).debug("Fetched job by id")
            return job
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job by id")
            raise RepositoryError("Failed to fetch job by id.") from exc

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
    ) -> list[Job]:
        """Fetch paginated jobs.

        Args:
            skip: Number of rows to offset.
            limit: Maximum rows to return (max 1000).
            platform: Optional platform filter.
            is_active: Active status filter.

        Returns:
            List of jobs ordered by descending id.

        Raises:
            ValueError: If pagination values are invalid.
            RepositoryError: If database query fails.
        """
        if skip < 0:
            raise ValueError("skip must be greater than or equal to 0")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if limit > 1000:
            raise ValueError("limit cannot exceed 1000")

        log = logger.bind(
            repository=self.__class__.__name__,
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
        )
        log.debug("Fetching jobs with pagination")

        try:
            query = select(Job).where(Job.is_active == is_active)
            if platform is not None:
                query = query.where(Job.platform == platform)

            result = await self.db.execute(
                query.order_by(Job.id.desc()).offset(skip).limit(limit)
            )
            jobs = self._to_list(result.scalars().all())
            log.bind(count=len(jobs)).debug("Fetched paginated jobs")
            return jobs
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch paginated jobs")
            raise RepositoryError("Failed to fetch jobs.") from exc

    async def create(self, job_data: dict[str, Any]) -> Job:
        """Create a new job record.

        Args:
            job_data: Field-value mapping for a new Job.

        Returns:
            Persisted Job entity.

        Raises:
            DuplicateJobError: If external_id + platform already exists.
            RepositoryError: If database write fails.
        """
        log = logger.bind(repository=self.__class__.__name__, operation="create")
        log.info("Creating job")

        try:
            invalid = PROTECTED_CREATE_FIELDS & job_data.keys()
            if invalid:
                blocked = ", ".join(sorted(invalid))
                raise ValueError(f"Cannot set protected fields: {blocked}")
            job = Job(**job_data)
            self.db.add(job)
            created_job = await self._commit_and_refresh(job)
            log.bind(job_id=created_job.id).info("Created job")
            return created_job
        except IntegrityError as exc:
            await self._rollback_safely()
            if self._is_duplicate_job_error(exc):
                log.bind(error=str(exc)).error("Duplicate job detected during create")
                raise DuplicateJobError(
                    "A job with this external_id and platform already exists."
                ) from exc
            log.bind(error=str(exc)).error("Integrity error during job create")
            raise RepositoryError(
                "Failed to create job due to integrity error."
            ) from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during job create")
            raise RepositoryError("Failed to create job.") from exc

    async def update(self, job_id: int, job_data: dict[str, Any]) -> Job | None:
        """Update an existing job record.

        Args:
            job_id: Existing job primary key.
            job_data: Field-value mapping to update on the entity.

        Returns:
            Updated Job entity when found, otherwise ``None``.

        Raises:
            DuplicateJobError: If update violates external_id + platform uniqueness.
            RepositoryError: If database write fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="update",
            job_id=job_id,
        )
        log.info("Updating job")

        try:
            result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job for update")
            raise RepositoryError("Failed to fetch job for update.") from exc

        if job is None:
            log.info("Job not found for update")
            return None

        for field, value in job_data.items():
            if field in PROTECTED_UPDATE_FIELDS:
                raise ValueError(f"Cannot update protected field: {field}")
            if field.startswith("_") or field not in self._column_names:
                raise ValueError(f"Unknown or unsafe update field: {field}")
            setattr(job, field, value)

        try:
            updated_job = await self._commit_and_refresh(job)
            log.info("Updated job")
            return updated_job
        except IntegrityError as exc:
            await self._rollback_safely()
            if self._is_duplicate_job_error(exc):
                log.bind(error=str(exc)).error("Duplicate job detected during update")
                raise DuplicateJobError(
                    "A job with this external_id and platform already exists."
                ) from exc
            log.bind(error=str(exc)).error("Integrity error during job update")
            raise RepositoryError(
                "Failed to update job due to integrity error."
            ) from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during job update")
            raise RepositoryError("Failed to update job.") from exc

    async def delete(self, job_id: int) -> bool:
        """Delete an existing job record.

        Args:
            job_id: Existing job primary key.

        Returns:
            ``True`` when deleted, ``False`` when not found.

        Raises:
            RepositoryError: If database delete fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="delete",
            job_id=job_id,
        )
        log.info("Deleting job")

        try:
            result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job for delete")
            raise RepositoryError("Failed to fetch job for delete.") from exc

        if job is None:
            log.info("Job not found for delete")
            return False

        try:
            await self.db.delete(job)
            await self.db.commit()
            log.info("Deleted job")
            return True
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Failed to delete job")
            raise RepositoryError("Failed to delete job.") from exc

    async def get_by_external_id(self, external_id: str, platform: str) -> Job | None:
        """Fetch one job by upstream external identifier and platform.

        Args:
            external_id: External provider job identifier.
            platform: Source platform name.

        Returns:
            Matching Job when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            external_id=external_id,
            platform=platform,
        )
        log.debug("Fetching job by external identifier")

        try:
            result = await self.db.execute(
                select(Job).where(
                    Job.external_id == external_id,
                    Job.platform == platform,
                )
            )
            job = result.scalar_one_or_none()
            log.bind(found=job is not None).debug("Fetched job by external identifier")
            return job
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job by external identifier")
            raise RepositoryError(
                "Failed to fetch job by external identifier."
            ) from exc

    @staticmethod
    def _is_duplicate_job_error(error: IntegrityError) -> bool:
        """Check whether an integrity error represents duplicate job violation.

        Args:
            error: SQLAlchemy integrity error.

        Returns:
            ``True`` when error indicates duplicate external_id + platform.

        Note:
            Detection relies on PostgreSQL error message text and constraint naming.
        """
        error_text = (
            str(error.orig).lower() if error.orig is not None else str(error).lower()
        )
        return (
            "duplicate key value violates unique constraint" in error_text
            and "uq_jobs_external_id_platform" in error_text
        ) or (
            "unique constraint" in error_text
            and "external_id" in error_text
            and "platform" in error_text
        )
