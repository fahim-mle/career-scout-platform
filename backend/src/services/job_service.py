"""Business logic service for job operations."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from src.core.exceptions import (
    BusinessLogicError,
    DuplicateJobError,
    NotFoundError,
    RepositoryError,
)
from src.core.metrics import increment_jobs_created
from src.core.title_normalization import normalize_job_title, title_preview_for_log
from src.models.job import ALLOWED_PLATFORMS, Job
from src.repositories.job_enrichment import JobEnrichmentRepository
from src.repositories.job import JobRepository
from src.schemas.job import (
    EnrichedJobResponse,
    JobCreate,
    JobResponse,
    JobUpdate,
    RawJobResponse,
)

PLATFORM_DOMAINS: dict[str, str] = {
    "linkedin": "linkedin.com",
    "seek": "seek.com.au",
    "indeed": "indeed.com",
}

if set(PLATFORM_DOMAINS) != set(ALLOWED_PLATFORMS):
    raise RuntimeError("PLATFORM_DOMAINS keys must match ALLOWED_PLATFORMS.")


class JobService:
    """Service layer for job business rules and repository orchestration."""

    def __init__(
        self,
        repo: JobRepository,
        enrichment_repo: JobEnrichmentRepository | None = None,
    ):
        """Initialize JobService.

        Args:
            repo: Repository used for job persistence operations.
            enrichment_repo: Optional repository used for processed enrichment reads.
        """
        self.repo = repo
        self.enrichment_repo = enrichment_repo

    async def get_job(self, job_id: int) -> JobResponse:
        """Get one raw job by identifier.

        Args:
            job_id: Database primary key for the job.

        Returns:
            Serialized job response.

        Raises:
            NotFoundError: If the job does not exist.
            BusinessLogicError: If repository access fails.
        """
        return await self.get_raw_job(job_id)

    async def get_raw_job(self, job_id: int) -> RawJobResponse:
        """Get one raw job by identifier.

        Args:
            job_id: Database primary key for the job.

        Returns:
            Serialized raw job response.

        Raises:
            NotFoundError: If the job does not exist.
            BusinessLogicError: If repository access fails.
        """
        log = logger.bind(
            service=self.__class__.__name__, operation="get_raw_job", job_id=job_id
        )
        log.info("Fetching raw job")

        try:
            job = await self.repo.get_by_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Repository error while fetching raw job")
            raise BusinessLogicError("Failed to fetch job.") from exc

        if job is None:
            log.warning("Raw job not found")
            raise NotFoundError(f"Job {job_id} not found.")

        log.info("Fetched raw job")
        return RawJobResponse.model_validate(job)

    async def get_enriched_job(self, job_id: int) -> EnrichedJobResponse:
        """Get one job enriched with latest processed metadata.

        Args:
            job_id: Database primary key for the raw job.

        Returns:
            Serialized enriched job response.

        Raises:
            NotFoundError: If the raw job does not exist.
            BusinessLogicError: If repository access fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="get_enriched_job",
            job_id=job_id,
        )
        log.info("Fetching enriched job")

        raw_job = await self.get_raw_job(job_id)

        if self.enrichment_repo is None:
            log.warning(
                "Enrichment repository unavailable; returning empty enrichment data"
            )
            return self._build_enriched_job_response(raw_job=raw_job, enrichment=None)

        try:
            enrichment = await self.enrichment_repo.get_latest_by_job_id(job_id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch latest enrichment")
            raise BusinessLogicError("Failed to fetch enriched job.") from exc

        enriched_job = self._build_enriched_job_response(
            raw_job=raw_job,
            enrichment=enrichment,
        )
        log.info("Fetched enriched job")
        return enriched_job

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
        job_type: str | None = None,
        search: str | None = None,
    ) -> list[RawJobResponse]:
        """List raw jobs for backward-compatible service callers.

        Args:
            skip: Number of records to offset.
            limit: Maximum number of records to return.
            platform: Optional platform filter.
            is_active: Optional active state filter.
            job_type: Optional job-type filter.
            search: Optional keyword search across title, company, location.

        Returns:
            List of serialized raw job responses.

        Raises:
            BusinessLogicError: If validation fails or repository access fails.
        """
        return await self.list_raw_jobs(
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
            job_type=job_type,
            search=search,
        )

    async def list_raw_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
        job_type: str | None = None,
        search: str | None = None,
    ) -> list[RawJobResponse]:
        """List jobs with pagination and optional filters.

        Args:
            skip: Number of records to offset.
            limit: Maximum number of records to return.
            platform: Optional platform filter.
            is_active: Optional active state filter.
            job_type: Optional job-type filter.
            search: Optional keyword search across title, company, location.

        Returns:
            List of serialized raw job responses.

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
            job_type=job_type,
            search=search,
        )
        log.info("Listing jobs")

        if platform is not None and platform not in ALLOWED_PLATFORMS:
            allowed = ", ".join(ALLOWED_PLATFORMS)
            log.warning("Invalid platform filter")
            raise BusinessLogicError(
                f"Invalid platform '{platform}'. Allowed values: {allowed}."
            )

        normalized_job_type = self._normalize_optional_filter(job_type)
        normalized_search = self._normalize_optional_filter(search)

        try:
            jobs = await self.repo.get_all(
                skip=skip,
                limit=limit,
                platform=platform,
                is_active=is_active,
                job_type=normalized_job_type,
                search=normalized_search,
            )
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to list jobs")
            raise BusinessLogicError("Failed to list jobs.") from exc

        log.bind(count=len(jobs)).info("Listed jobs")
        return [RawJobResponse.model_validate(job) for job in jobs]

    async def list_enriched_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
        job_type: str | None = None,
        search: str | None = None,
    ) -> list[EnrichedJobResponse]:
        """List jobs enriched with latest processed fields and metadata.

        Args:
            skip: Number of records to offset.
            limit: Maximum number of records to return.
            platform: Optional platform filter.
            is_active: Optional active state filter.
            job_type: Optional job-type filter.
            search: Optional keyword search across title, company, location.

        Returns:
            List of serialized enriched job responses.

        Raises:
            BusinessLogicError: If validation fails or repository access fails.
        """
        log = logger.bind(
            service=self.__class__.__name__,
            operation="list_enriched_jobs",
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
            job_type=job_type,
            search=search,
        )
        log.info("Listing enriched jobs")

        raw_jobs = await self.list_raw_jobs(
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
            job_type=job_type,
            search=search,
        )

        if not raw_jobs:
            return []

        if self.enrichment_repo is None:
            log.warning(
                "Enrichment repository unavailable; returning empty enrichment data"
            )
            return [
                self._build_enriched_job_response(raw_job=job, enrichment=None)
                for job in raw_jobs
            ]

        job_ids = [job.id for job in raw_jobs]

        try:
            enrichments = await self.enrichment_repo.list_by_job_ids(job_ids)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to list enrichments")
            raise BusinessLogicError("Failed to list jobs.") from exc

        latest_by_job_id = self._latest_enrichment_by_job_id(enrichments)
        enriched_jobs = [
            self._build_enriched_job_response(
                raw_job=job,
                enrichment=latest_by_job_id.get(job.id),
            )
            for job in raw_jobs
        ]
        log.bind(count=len(enriched_jobs)).info("Listed enriched jobs")
        return enriched_jobs

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
            self._map_platform_metadata_field(job_data)
            self._normalize_title_for_persistence(job_data, log=log)
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

        self._map_platform_metadata_field(update_data)
        self._normalize_title_for_persistence(update_data, log=log)
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

    def _normalize_title_for_persistence(
        self,
        payload: dict[str, object],
        *,
        log: Any,
    ) -> None:
        """Normalize duplicated title artifacts before repository writes.

        Args:
            payload: Mutable create/update payload.
            log: Bound structured logger.

        Returns:
            None.
        """
        if "title" not in payload:
            return

        raw_title = payload.get("title")
        if raw_title is None or not isinstance(raw_title, str):
            return

        normalized_title = normalize_job_title(raw_title)
        if normalized_title is None:
            return

        payload["title"] = normalized_title
        if normalized_title != raw_title:
            log.bind(
                normalization="adjacent_duplicate_phrase",
                changed=True,
                title_raw=title_preview_for_log(raw_title),
                title_normalized=title_preview_for_log(normalized_title),
            ).info("Normalized job title before persistence")

    @staticmethod
    def _map_platform_metadata_field(payload: dict[str, object]) -> None:
        """Map API-facing ``metadata`` field to ORM ``platform_metadata``.

        Args:
            payload: Mutable create/update payload.

        Returns:
            None.
        """
        if "metadata" not in payload:
            return

        payload["platform_metadata"] = payload.pop("metadata")

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

    def _latest_enrichment_by_job_id(
        self,
        enrichments: Sequence[object],
    ) -> dict[int, object]:
        """Select the latest enrichment row for each job id.

        Args:
            enrichments: Candidate enrichment rows returned by the repository.

        Returns:
            Mapping of ``job_id`` to latest enrichment row.
        """
        latest: dict[int, object] = {}

        for row in enrichments:
            job_id = getattr(row, "job_id", None)
            if not isinstance(job_id, int):
                continue

            current = latest.get(job_id)
            if current is None:
                latest[job_id] = row
                continue

            if self._is_newer_enrichment(candidate=row, current=current):
                latest[job_id] = row

        return latest

    def _is_newer_enrichment(self, candidate: object, current: object) -> bool:
        """Determine whether one enrichment row is newer than another.

        Args:
            candidate: Enrichment row candidate.
            current: Existing enrichment row for comparison.

        Returns:
            ``True`` when candidate should replace current.
        """
        candidate_enriched_at = self._as_datetime(
            getattr(candidate, "enriched_at", None)
        )
        current_enriched_at = self._as_datetime(getattr(current, "enriched_at", None))

        if candidate_enriched_at is not None and current_enriched_at is not None:
            if candidate_enriched_at != current_enriched_at:
                return candidate_enriched_at > current_enriched_at
        elif candidate_enriched_at is not None:
            return True
        elif current_enriched_at is not None:
            return False

        candidate_id = getattr(candidate, "id", 0)
        current_id = getattr(current, "id", 0)
        if isinstance(candidate_id, int) and isinstance(current_id, int):
            return candidate_id > current_id
        return False

    def _build_enriched_job_response(
        self,
        raw_job: RawJobResponse,
        enrichment: object | None,
    ) -> EnrichedJobResponse:
        """Merge a raw job with optional enrichment into API response schema.

        Args:
            raw_job: Raw job response generated from repository entity.
            enrichment: Optional enrichment row matched by job id.

        Returns:
            Enriched job response payload.
        """
        salary_range = self._build_salary_range(enrichment)
        return EnrichedJobResponse(
            id=raw_job.id,
            created_at=raw_job.created_at,
            updated_at=raw_job.updated_at,
            external_id=raw_job.external_id,
            platform=raw_job.platform,
            url=raw_job.url,
            title=raw_job.title,
            company=raw_job.company,
            location=raw_job.location,
            description_short=raw_job.description_short,
            description_full=raw_job.description_full,
            posted_date=raw_job.posted_date,
            scraped_at=raw_job.scraped_at,
            is_active=raw_job.is_active,
            skills=getattr(enrichment, "skills", None),
            job_type=getattr(enrichment, "job_type", None),
            salary_range=salary_range,
            enrichment_status=getattr(enrichment, "status", None),
            enrichment_version=getattr(enrichment, "extractor_version", None),
            enrichment_updated_at=self._as_datetime(
                getattr(enrichment, "enriched_at", None)
            ),
            description_sections=getattr(enrichment, "description_sections", None),
            relevance_score=raw_job.relevance_score,
        )

    def _build_salary_range(self, enrichment: object | None) -> dict[str, Any] | None:
        """Construct salary range payload from enrichment salary columns.

        Args:
            enrichment: Optional enrichment row.

        Returns:
            Salary range dictionary when at least one salary field exists.
        """
        if enrichment is None:
            return None

        salary_range = {
            "min": getattr(enrichment, "salary_min", None),
            "max": getattr(enrichment, "salary_max", None),
            "currency": getattr(enrichment, "salary_currency", None),
            "period": getattr(enrichment, "salary_period", None),
            "raw": getattr(enrichment, "salary_raw", None),
        }
        if all(value is None for value in salary_range.values()):
            return None
        return salary_range

    @staticmethod
    def _as_datetime(value: object) -> datetime | None:
        """Safely cast value to timezone-aware datetime.

        Args:
            value: Candidate datetime value.

        Returns:
            Datetime when value is datetime, otherwise ``None``.
        """
        if isinstance(value, datetime):
            return value
        return None

    @staticmethod
    def _normalize_optional_filter(value: str | None) -> str | None:
        """Normalize optional text filters before repository usage.

        Args:
            value: Optional raw query parameter string.

        Returns:
            Trimmed filter value when non-empty, otherwise ``None``.
        """
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None
