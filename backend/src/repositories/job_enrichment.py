"""Data access repository for JobEnrichment entities."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.core.metrics import db_query_timer
from src.models.job_enrichment import JobEnrichment
from src.repositories.base import BaseRepository

PROTECTED_UPDATE_FIELDS = frozenset({"id", "created_at", "updated_at", "job_id"})
PROTECTED_CREATE_FIELDS = frozenset({"id", "created_at", "updated_at"})
PROTECTED_UPSERT_FIELDS = frozenset(
    {"id", "created_at", "updated_at", "job_id", "extractor_version"}
)


class JobEnrichmentRepository(BaseRepository[JobEnrichment]):
    """Repository responsible for processed enrichment persistence operations."""

    def __init__(self, db: AsyncSession):
        """Initialize JobEnrichmentRepository.

        Args:
            db: Active asynchronous SQLAlchemy session.
        """
        super().__init__(db=db, model_type=JobEnrichment)
        self._column_names = {
            column.key
            for column in JobEnrichment.__table__.columns  # type: ignore[attr-defined]
        }

    async def create(self, payload: dict[str, Any]) -> JobEnrichment:
        """Create a new enrichment record.

        Args:
            payload: Field-value mapping for a new JobEnrichment record.

        Returns:
            Persisted JobEnrichment entity.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload attempts to set protected fields.
        """
        log = logger.bind(repository=self.__class__.__name__, operation="create")
        log.info("Creating job enrichment")

        try:
            invalid = PROTECTED_CREATE_FIELDS & payload.keys()
            if invalid:
                blocked = ", ".join(sorted(invalid))
                raise ValueError(f"Cannot set protected fields: {blocked}")

            enrichment = JobEnrichment(**payload)
            with db_query_timer(query_type="job_enrichment_create"):
                self.db.add(enrichment)
                created = await self._commit_and_refresh(enrichment)
            log.bind(enrichment_id=created.id, job_id=created.job_id).info(
                "Created job enrichment"
            )
            return created
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Integrity error during job enrichment create"
            )
            raise RepositoryError(
                "Failed to create job enrichment due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during job enrichment create"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database error during job enrichment create"
            )
            raise RepositoryError("Failed to create job enrichment.") from exc

    async def update(
        self,
        enrichment_id: int,
        payload: dict[str, Any],
    ) -> JobEnrichment | None:
        """Update an existing enrichment record.

        Args:
            enrichment_id: Existing enrichment primary key.
            payload: Field-value mapping to update.

        Returns:
            Updated JobEnrichment when found, otherwise ``None``.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload contains protected or unknown fields.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="update",
            enrichment_id=enrichment_id,
        )
        log.info("Updating job enrichment")

        try:
            with db_query_timer(query_type="job_enrichment_update_lookup"):
                result = await self.db.execute(
                    select(JobEnrichment).where(JobEnrichment.id == enrichment_id)
                )
            enrichment = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch enrichment for update")
            raise RepositoryError("Failed to fetch job enrichment for update.") from exc

        if enrichment is None:
            log.info("Job enrichment not found for update")
            return None

        for field, value in payload.items():
            if field in PROTECTED_UPDATE_FIELDS:
                raise ValueError(f"Cannot update protected field: {field}")
            if field.startswith("_") or field not in self._column_names:
                raise ValueError(f"Unknown or unsafe update field: {field}")
            setattr(enrichment, field, value)

        try:
            with db_query_timer(query_type="job_enrichment_update"):
                updated = await self._commit_and_refresh(enrichment)
            log.bind(enrichment_id=updated.id).info("Updated job enrichment")
            return updated
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Integrity error during job enrichment update"
            )
            raise RepositoryError(
                "Failed to update job enrichment due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during job enrichment update"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database error during job enrichment update"
            )
            raise RepositoryError("Failed to update job enrichment.") from exc

    async def get_latest_by_job_id(self, job_id: int) -> JobEnrichment | None:
        """Fetch the latest enrichment for a given job.

        Args:
            job_id: Raw job primary key.

        Returns:
            Latest JobEnrichment by ``enriched_at`` when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="get_latest_by_job_id",
            job_id=job_id,
        )
        log.debug("Fetching latest enrichment by job id")

        try:
            with db_query_timer(query_type="job_enrichment_get_latest"):
                result = await self.db.execute(
                    select(JobEnrichment)
                    .where(JobEnrichment.job_id == job_id)
                    .order_by(
                        JobEnrichment.enriched_at.desc(),
                        JobEnrichment.id.desc(),
                    )
                    .limit(1)
                )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch latest enrichment")
            raise RepositoryError("Failed to fetch latest job enrichment.") from exc

    async def get_by_job_and_version(
        self,
        job_id: int,
        extractor_version: str,
    ) -> JobEnrichment | None:
        """Fetch enrichment for a job/extractor_version pair.

        Args:
            job_id: Raw job primary key.
            extractor_version: Extraction algorithm version token.

        Returns:
            Matching JobEnrichment when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="get_by_job_and_version",
            job_id=job_id,
            extractor_version=extractor_version,
        )
        log.debug("Fetching enrichment by job and version")

        try:
            with db_query_timer(query_type="job_enrichment_get_by_job_and_version"):
                result = await self.db.execute(
                    select(JobEnrichment).where(
                        JobEnrichment.job_id == job_id,
                        JobEnrichment.extractor_version == extractor_version,
                    )
                )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch enrichment by version")
            raise RepositoryError("Failed to fetch job enrichment by version.") from exc

    async def upsert_by_job_and_version(
        self,
        job_id: int,
        extractor_version: str,
        payload: dict[str, Any],
    ) -> JobEnrichment:
        """Insert or merge an enrichment record for a job/version pair.

        Existing non-null fields are preserved and only missing fields are populated.

        Args:
            job_id: Raw job primary key.
            extractor_version: Extraction algorithm version token.
            payload: Enrichment fields to merge into persistence.

        Returns:
            Persisted JobEnrichment entity after merge.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload contains unknown fields.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="upsert_by_job_and_version",
            job_id=job_id,
            extractor_version=extractor_version,
        )
        log.info("Upserting job enrichment by version")

        invalid = PROTECTED_UPSERT_FIELDS & payload.keys()
        if invalid:
            blocked = ", ".join(sorted(invalid))
            raise ValueError(
                f"Cannot set protected fields in upsert payload: {blocked}"
            )

        for field in payload:
            if field.startswith("_"):
                raise ValueError(f"Unknown or unsafe upsert field: {field}")
            if field not in self._column_names:
                raise ValueError(f"Unknown or unsafe upsert field: {field}")

        try:
            existing = await self.get_by_job_and_version(job_id, extractor_version)

            if existing is None:
                create_payload = {
                    **payload,
                    "job_id": job_id,
                    "extractor_version": extractor_version,
                }
                return await self.create(create_payload)

            merged_payload = self._merge_missing_fields(existing, payload)
            if not merged_payload:
                log.debug("No missing fields to populate in existing enrichment")
                return existing

            merged_payload["enriched_at"] = datetime.now(timezone.utc)
            updated = await self.update(existing.id, merged_payload)
            if updated is None:
                raise RepositoryError("Failed to update enrichment during upsert.")
            return updated
        except (RepositoryError, ValueError):
            raise
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during enrichment upsert")
            raise RepositoryError(
                "Failed to upsert job enrichment due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during job enrichment upsert"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database error during job enrichment upsert"
            )
            raise RepositoryError("Failed to upsert job enrichment.") from exc

    async def list_by_job_ids(self, job_ids: Sequence[int]) -> list[JobEnrichment]:
        """Fetch enrichments for a list of raw job ids.

        Args:
            job_ids: Collection of raw job identifiers.

        Returns:
            List of matching JobEnrichment rows ordered by job and recency.

        Raises:
            RepositoryError: If database query fails.
        """
        if not job_ids:
            return []

        log = logger.bind(
            repository=self.__class__.__name__,
            operation="list_by_job_ids",
            count=len(job_ids),
        )
        log.debug("Listing enrichments by job ids")

        try:
            with db_query_timer(query_type="job_enrichment_list_by_job_ids"):
                result = await self.db.execute(
                    select(JobEnrichment)
                    .where(JobEnrichment.job_id.in_(list(job_ids)))
                    .order_by(
                        JobEnrichment.job_id.asc(), JobEnrichment.enriched_at.desc()
                    )
                )
            return self._to_list(result.scalars().all())
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to list enrichments by job ids")
            raise RepositoryError("Failed to list job enrichments.") from exc

    def _merge_missing_fields(
        self,
        existing: JobEnrichment,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an update payload that only fills missing fields.

        Args:
            existing: Existing persisted enrichment row.
            payload: Incoming candidate field updates.

        Returns:
            Subset payload containing only values that populate missing fields.
        """
        merged: dict[str, Any] = {}
        for field, value in payload.items():
            if field in {
                "job_id",
                "extractor_version",
                "id",
                "created_at",
                "updated_at",
            }:
                continue
            if self._is_missing(
                getattr(existing, field), field
            ) and not self._is_missing(
                value,
                field,
            ):
                merged[field] = value
        return merged

    @staticmethod
    def _is_missing(value: object, field: str) -> bool:
        """Determine whether a persisted value should be treated as missing.

        Args:
            value: Candidate field value.
            field: Field name for type-aware checks.

        Returns:
            ``True`` when value is considered missing.
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


__all__ = ["JobEnrichmentRepository"]
