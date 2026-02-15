"""Business logic service for job operations."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from loguru import logger

from src.core.exceptions import (
    BusinessLogicError,
    DuplicateJobError,
    NotFoundError,
    RepositoryError,
)
from src.core.metrics import increment_jobs_created
from src.models.job import ALLOWED_PLATFORMS, Job
from src.repositories.job import JobRepository
from src.schemas.job import JobCreate, JobResponse, JobUpdate

PLATFORM_DOMAINS: dict[str, str] = {
    "linkedin": "linkedin.com",
    "seek": "seek.com.au",
    "indeed": "indeed.com",
}

if set(PLATFORM_DOMAINS) != set(ALLOWED_PLATFORMS):
    raise RuntimeError("PLATFORM_DOMAINS keys must match ALLOWED_PLATFORMS.")


class JobService:
    """Service layer for job business rules and repository orchestration."""

    def __init__(self, repo: JobRepository):
        """Initialize JobService.

        Args:
            repo: Repository used for job persistence operations.
        """
        self.repo = repo

    async def get_job(self, job_id: int) -> JobResponse:
        """Get one job by identifier.

        Args:
            job_id: Database primary key for the job.

        Returns:
            Serialized job response.

        Raises:
            NotFoundError: If the job does not exist.
            BusinessLogicError: If repository access fails.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="get_job", job_id=job_id
        )
        log.info("Fetching job")

        try:
            job = await self.repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Repository error while fetching job")
            raise BusinessLogicError("Failed to fetch job.") from exc

        if job is None:
            log.warning("Job not found")
            raise NotFoundError(f"Job {job_id} not found.")

        log.info("Fetched job")
        return JobResponse.model_validate(job)

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
    ) -> list[JobResponse]:
        """List jobs with pagination and optional filters.

        Args:
            skip: Number of records to offset.
            limit: Maximum number of records to return.
            platform: Optional platform filter.
            is_active: Optional active state filter.

        Returns:
            List of serialized job responses.

        Raises:
            BusinessLogicError: If validation fails or repository access fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="list_jobs",
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
        )
        log.info("Listing jobs")

        if platform is not None and platform not in ALLOWED_PLATFORMS:
            allowed = ", ".join(ALLOWED_PLATFORMS)
            log.warning("Invalid platform filter")
            raise BusinessLogicError(
                f"Invalid platform '{platform}'. Allowed values: {allowed}."
            )

        try:
            jobs = await self.repo.get_all(
                skip=skip,
                limit=limit,
                platform=platform,
                is_active=is_active,
            )
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to list jobs")
            raise BusinessLogicError("Failed to list jobs.") from exc

        log.bind(count=len(jobs)).info("Listed jobs")
        return [JobResponse.model_validate(job) for job in jobs]

    async def create_job(self, payload: JobCreate) -> JobResponse:
        """Create a new job with business validation.

        Args:
            payload: Job creation payload.

        Returns:
            Serialized created job response.

        Raises:
            BusinessLogicError: If business validation or repository actions fail.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="create_job",
            external_id=payload.external_id,
            platform=payload.platform,
        )
        log.info("Creating job")

        self._validate_posted_date(payload.posted_date)
        self._validate_url_for_platform(str(payload.url), payload.platform)

        try:
            job_data = payload.model_dump(mode="python", exclude_unset=True)
            job_data["url"] = str(payload.url)
            job = await self.repo.create(job_data)
        except DuplicateJobError as exc:
            log.bind(error=str(exc)).warning("Duplicate job on create")
            raise BusinessLogicError(
                "A job with this external_id already exists for the selected platform."
            ) from exc
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to create job")
            raise BusinessLogicError(f"Failed to create job: {exc}") from exc

        try:
            increment_jobs_created(platform=job.platform)
        except ValueError as exc:
            log.bind(error=str(exc), platform=job.platform).warning(
                "Skipped jobs_created_total metric"
            )

        log.bind(job_id=job.id).info("Created job")
        return JobResponse.model_validate(job)

    async def update_job(self, job_id: int, payload: JobUpdate) -> JobResponse:
        """Update an existing job with immutable and quality guards.

        Args:
            job_id: Database primary key for the job.
            payload: Partial update payload.

        Returns:
            Serialized updated job response.

        Raises:
            NotFoundError: If the job does not exist.
            BusinessLogicError: If business validation or repository actions fail.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="update_job", job_id=job_id
        )
        log.info("Updating job")

        try:
            existing = await self.repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job before update")
            raise BusinessLogicError("Failed to update job.") from exc

        if existing is None:
            log.warning("Job not found for update")
            raise NotFoundError(f"Job {job_id} not found.")

        update_data = payload.model_dump(exclude_unset=True, mode="python")
        self._validate_and_strip_immutable_fields(
            existing=existing, updates=update_data
        )

        if not update_data:
            log.info("No mutable fields provided; returning existing job")
            return JobResponse.model_validate(existing)

        if "posted_date" in update_data:
            self._validate_posted_date(update_data.get("posted_date"))

        if "url" in update_data:
            update_data["url"] = str(update_data["url"])
            self._validate_url_for_platform(str(update_data["url"]), existing.platform)

        self._validate_description_growth(existing=existing, updates=update_data)

        try:
            updated = await self.repo.update(job_id, update_data)
        except DuplicateJobError as exc:
            log.bind(error=str(exc)).warning("Duplicate job on update")
            raise BusinessLogicError(
                "Cannot update job because external_id/platform must remain unique."
            ) from exc
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to update job")
            raise BusinessLogicError(f"Failed to update job: {exc}") from exc

        if updated is None:
            log.warning("Job disappeared during update")
            raise NotFoundError(f"Job {job_id} not found.")

        log.info("Updated job")
        return JobResponse.model_validate(updated)

    async def delete_job(self, job_id: int) -> bool:
        """Soft-delete a job by setting ``is_active`` to ``False``.

        Args:
            job_id: Database primary key for the job.

        Returns:
            ``True`` when job exists and is inactive after the call.

        Raises:
            NotFoundError: If the job does not exist.
            BusinessLogicError: If repository actions fail.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="delete_job", job_id=job_id
        )
        log.info("Soft deleting job")

        try:
            existing = await self.repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch job before delete")
            raise BusinessLogicError("Failed to delete job.") from exc

        if existing is None:
            log.warning("Job not found for delete")
            raise NotFoundError(f"Job {job_id} not found.")

        if existing.is_active is False:
            log.info("Job already inactive")
            return True

        try:
            deleted = await self.repo.update(job_id, {"is_active": False})
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to soft delete job")
            raise BusinessLogicError(f"Failed to delete job: {exc}") from exc

        if deleted is None:
            log.warning("Job disappeared during delete")
            raise NotFoundError(f"Job {job_id} not found.")

        log.info("Soft deleted job")
        return True

    def _validate_posted_date(self, posted_date: date | None) -> None:
        """Validate posted date is not in the future.

        Args:
            posted_date: Candidate posted date.

        Raises:
            BusinessLogicError: If posted date is after today's date.
        """
        if posted_date is not None and posted_date > date.today():
            raise BusinessLogicError("posted_date cannot be in the future.")

    def _validate_url_for_platform(self, raw_url: str, platform: str) -> None:
        """Validate URL host maps to allowed platform domain.

        Args:
            raw_url: URL value from payload.
            platform: Platform identifier.

        Raises:
            BusinessLogicError: If platform is unsupported or URL host mismatches platform.
        """
        expected_domain = PLATFORM_DOMAINS.get(platform)
        if expected_domain is None:
            allowed = ", ".join(ALLOWED_PLATFORMS)
            raise BusinessLogicError(
                f"Invalid platform '{platform}'. Allowed values: {allowed}."
            )

        hostname = (urlparse(raw_url).hostname or "").lower()
        if not hostname:
            raise BusinessLogicError("url must include a valid hostname.")

        if not self._domain_matches(hostname=hostname, expected=expected_domain):
            raise BusinessLogicError(
                f"URL domain '{hostname}' does not match platform '{platform}'."
            )

    def _validate_and_strip_immutable_fields(
        self,
        existing: Job,
        updates: dict[str, object],
    ) -> None:
        """Enforce immutable job fields and remove them from updates.

        Args:
            existing: Current persisted job entity.
            updates: Partial update payload map that may be mutated in-place.

        Raises:
            BusinessLogicError: If immutable fields are changed.
        """
        if "external_id" in updates and updates["external_id"] != existing.external_id:
            raise BusinessLogicError("external_id cannot be changed after creation.")

        if "platform" in updates and updates["platform"] != existing.platform:
            raise BusinessLogicError("platform cannot be changed after creation.")

        updates.pop("external_id", None)
        updates.pop("platform", None)

    def _validate_description_growth(
        self, existing: Job, updates: dict[str, object]
    ) -> None:
        """Ensure updated descriptions grow in length compared to existing values.

        Args:
            existing: Current persisted job entity.
            updates: Partial update payload map.

        Raises:
            BusinessLogicError: If a provided description is not longer than current value.
        """
        for field_name in ("description_short", "description_full"):
            if field_name not in updates:
                continue

            next_value = updates[field_name]
            if next_value is None:
                continue

            current_value = getattr(existing, field_name)
            current_length = len(current_value or "")
            next_length = len(next_value) if isinstance(next_value, str) else 0

            if next_length <= current_length:
                raise BusinessLogicError(
                    f"{field_name} updates must be longer than the existing value."
                )

    @staticmethod
    def _domain_matches(hostname: str, expected: str) -> bool:
        """Check whether hostname matches expected root domain.

        Args:
            hostname: Parsed lowercase hostname.
            expected: Platform root domain.

        Returns:
            ``True`` when hostname equals expected domain or is its subdomain.
        """
        return hostname == expected or hostname.endswith(f".{expected}")
