"""Data access repository for MatchScore entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.core.metrics import db_query_timer
from src.models.job import Job
from src.models.match_score import ALLOWED_MATCH_CATEGORIES, MatchScore
from src.repositories.base import BaseRepository

PROTECTED_CREATE_FIELDS = frozenset({"id", "created_at", "updated_at"})
PROTECTED_UPDATE_FIELDS = frozenset(
    {"id", "created_at", "updated_at", "job_id", "profile_id"}
)
PROTECTED_UPSERT_FIELDS = frozenset(
    {"id", "created_at", "updated_at", "job_id", "profile_id"}
)


class MatchScoreRepository(BaseRepository[MatchScore]):
    """Repository responsible for match score persistence operations."""

    def __init__(self, db: AsyncSession):
        """Initialize MatchScoreRepository.

        Args:
            db: Active asynchronous SQLAlchemy session.
        """
        super().__init__(db=db, model_type=MatchScore)
        self._column_names = {
            column.key
            for column in MatchScore.__table__.columns  # type: ignore[attr-defined]
        }

    async def get_by_id(self, score_id: int) -> MatchScore | None:
        """Fetch one match score by primary key.

        Args:
            score_id: Match score primary key.

        Returns:
            Matching MatchScore when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="get_by_id",
            score_id=score_id,
        )
        log.debug("Fetching match score by id")

        try:
            with db_query_timer(query_type="match_score_get_by_id"):
                result = await self.db.execute(
                    select(MatchScore).where(MatchScore.id == score_id)
                )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch match score by id")
            raise RepositoryError("Failed to fetch match score by id.") from exc

    async def get_by_job_and_profile(
        self,
        job_id: int,
        profile_id: int,
    ) -> MatchScore | None:
        """Fetch one match score by unique (job_id, profile_id).

        Args:
            job_id: Job primary key.
            profile_id: Profile primary key.

        Returns:
            Matching MatchScore when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="get_by_job_and_profile",
            job_id=job_id,
            profile_id=profile_id,
        )
        log.debug("Fetching match score by job/profile")

        try:
            with db_query_timer(query_type="match_score_get_by_job_and_profile"):
                result = await self.db.execute(
                    select(MatchScore).where(
                        MatchScore.job_id == job_id,
                        MatchScore.profile_id == profile_id,
                    )
                )
            return result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch match score by job/profile")
            raise RepositoryError(
                "Failed to fetch match score by job/profile."
            ) from exc

    async def get_by_profile(
        self,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[MatchScore]:
        """Fetch scores for one profile with pagination.

        Args:
            profile_id: Profile primary key.
            skip: Number of rows to offset.
            limit: Maximum rows to return (max 1000).

        Returns:
            List of MatchScore rows for the profile.

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
            operation="get_by_profile",
            profile_id=profile_id,
            skip=skip,
            limit=limit,
        )
        log.debug("Fetching match scores by profile")

        try:
            with db_query_timer(query_type="match_score_get_by_profile"):
                result = await self.db.execute(
                    select(MatchScore)
                    .where(MatchScore.profile_id == profile_id)
                    .order_by(MatchScore.relevance_score.desc(), MatchScore.id.desc())
                    .offset(skip)
                    .limit(limit)
                )
            return self._to_list(result.scalars().all())
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch match scores by profile")
            raise RepositoryError("Failed to fetch match scores by profile.") from exc

    async def create(self, payload: dict[str, Any]) -> MatchScore:
        """Create a new match score record.

        Args:
            payload: Field-value mapping for a new MatchScore record.

        Returns:
            Persisted MatchScore entity.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload attempts to set protected fields.
        """
        log = logger.bind(repository=self.__class__.__name__, operation="create")
        log.info("Creating match score")

        invalid = PROTECTED_CREATE_FIELDS & payload.keys()
        if invalid:
            blocked = ", ".join(sorted(invalid))
            raise ValueError(f"Cannot set protected fields: {blocked}")

        try:
            score = MatchScore(**payload)
            with db_query_timer(query_type="match_score_create"):
                self.db.add(score)
                created = await self._commit_and_refresh(score)
            log.bind(score_id=created.id).info("Created match score")
            return created
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during match score create")
            raise RepositoryError(
                "Failed to create match score due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during match score create"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during match score create")
            raise RepositoryError("Failed to create match score.") from exc

    async def update(
        self,
        score_id: int,
        payload: dict[str, Any],
    ) -> MatchScore | None:
        """Update an existing match score.

        Args:
            score_id: Existing match score primary key.
            payload: Field-value mapping to update.

        Returns:
            Updated MatchScore when found, otherwise ``None``.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload contains protected or unknown fields.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="update",
            score_id=score_id,
        )
        log.info("Updating match score")

        try:
            with db_query_timer(query_type="match_score_update_lookup"):
                result = await self.db.execute(
                    select(MatchScore).where(MatchScore.id == score_id)
                )
            score = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch match score for update")
            raise RepositoryError("Failed to fetch match score for update.") from exc

        if score is None:
            log.info("Match score not found for update")
            return None

        for field, value in payload.items():
            if field in PROTECTED_UPDATE_FIELDS:
                raise ValueError(f"Cannot update protected field: {field}")
            if field.startswith("_") or field not in self._column_names:
                raise ValueError(f"Unknown or unsafe update field: {field}")
            setattr(score, field, value)

        try:
            with db_query_timer(query_type="match_score_update"):
                updated = await self._commit_and_refresh(score)
            log.bind(score_id=updated.id).info("Updated match score")
            return updated
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during match score update")
            raise RepositoryError(
                "Failed to update match score due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during match score update"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during match score update")
            raise RepositoryError("Failed to update match score.") from exc

    async def upsert_by_job_and_profile(
        self,
        job_id: int,
        profile_id: int,
        payload: dict[str, Any],
    ) -> MatchScore:
        """Insert or fill-missing for a unique (job_id, profile_id) score.

        Existing non-missing fields are preserved; only missing fields are populated.

        Args:
            job_id: Job primary key.
            profile_id: Profile primary key.
            payload: Candidate fields to create or merge.

        Returns:
            Persisted MatchScore entity.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload contains protected or unknown fields.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="upsert_by_job_and_profile",
            job_id=job_id,
            profile_id=profile_id,
        )
        log.info("Upserting match score by job/profile")

        invalid = PROTECTED_UPSERT_FIELDS & payload.keys()
        if invalid:
            blocked = ", ".join(sorted(invalid))
            raise ValueError(
                f"Cannot set protected fields in upsert payload: {blocked}"
            )

        for field in payload:
            if field.startswith("_") or field not in self._column_names:
                raise ValueError(f"Unknown or unsafe upsert field: {field}")

        try:
            existing = await self.get_by_job_and_profile(job_id, profile_id)

            if existing is None:
                create_payload = {**payload, "job_id": job_id, "profile_id": profile_id}
                try:
                    return await self.create(create_payload)
                except RepositoryError as exc:
                    log.bind(error=str(exc)).warning(
                        "Create failed during upsert; refetching once for race recovery"
                    )
                    recovered = await self.get_by_job_and_profile(job_id, profile_id)
                    if recovered is not None:
                        log.bind(score_id=recovered.id).info(
                            "Recovered match score after create race"
                        )
                        return recovered
                    raise exc

            merged_payload = self._merge_missing_fields(existing, payload)
            if not merged_payload:
                log.debug("No missing fields to populate in existing score")
                return existing

            merged_payload["scored_at"] = datetime.now(timezone.utc)
            updated = await self.update(existing.id, merged_payload)
            if updated is None:
                raise RepositoryError("Failed to update match score during upsert.")
            return updated
        except (RepositoryError, ValueError):
            raise
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during match score upsert")
            raise RepositoryError(
                "Failed to upsert match score due to integrity error."
            ) from exc
        except OperationalError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error(
                "Database connection failed during match score upsert"
            )
            raise RepositoryError("Database connection failed.") from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during match score upsert")
            raise RepositoryError("Failed to upsert match score.") from exc

    async def list_for_jobs(
        self,
        job_ids: list[int],
        profile_id: int | None = None,
    ) -> list[MatchScore]:
        """Fetch scores for a job id set, optionally narrowed to one profile.

        Args:
            job_ids: Collection of job primary keys.
            profile_id: Optional profile primary key filter.

        Returns:
            Matching MatchScore rows sorted by score descending.

        Raises:
            RepositoryError: If database query fails.
        """
        if not job_ids:
            return []

        log = logger.bind(
            repository=self.__class__.__name__,
            operation="list_for_jobs",
            count=len(job_ids),
            profile_id=profile_id,
        )
        log.debug("Listing match scores for jobs")

        try:
            query = select(MatchScore).where(MatchScore.job_id.in_(job_ids))
            if profile_id is not None:
                query = query.where(MatchScore.profile_id == profile_id)

            with db_query_timer(query_type="match_score_list_for_jobs"):
                result = await self.db.execute(
                    query.order_by(
                        MatchScore.relevance_score.desc(), MatchScore.id.desc()
                    )
                )
            return self._to_list(result.scalars().all())
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to list match scores for jobs")
            raise RepositoryError("Failed to list match scores for jobs.") from exc

    async def get_jobs_by_score(
        self,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
        platform: str | None = None,
        is_active: bool = True,
        job_type: str | None = None,
        search: str | None = None,
    ) -> list[tuple[Job, int]]:
        """Fetch jobs joined with profile scores ordered by relevance.

        Args:
            profile_id: Profile primary key used for score filtering.
            skip: Number of rows to offset.
            limit: Maximum rows to return (max 1000).
            platform: Optional platform filter.
            is_active: Active status filter on jobs.
            job_type: Optional job-type filter (case-insensitive match).
            search: Optional keyword search across title, company, and location.

        Returns:
            List of ``(Job, relevance_score)`` tuples sorted by relevance.

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
            operation="get_jobs_by_score",
            profile_id=profile_id,
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
            job_type=job_type,
            search=search,
        )
        log.debug("Fetching jobs ordered by relevance score")

        try:
            query = (
                select(Job, MatchScore.relevance_score)
                .join(MatchScore, MatchScore.job_id == Job.id)
                .where(
                    MatchScore.profile_id == profile_id,
                    Job.is_active == is_active,
                )
            )
            if platform is not None:
                query = query.where(Job.platform == platform)

            normalized_job_type = self._normalize_text_filter(job_type)
            if normalized_job_type is not None:
                term = self._contains_pattern(normalized_job_type)
                query = query.where(Job.job_type.ilike(term, escape="\\"))

            normalized_search = self._normalize_text_filter(search)
            if normalized_search is not None:
                term = self._contains_pattern(normalized_search)
                query = query.where(
                    or_(
                        Job.title.ilike(term, escape="\\"),
                        Job.company.ilike(term, escape="\\"),
                        Job.location.ilike(term, escape="\\"),
                    )
                )

            with db_query_timer(query_type="match_score_get_jobs_by_score"):
                result = await self.db.execute(
                    query.order_by(
                        MatchScore.relevance_score.desc(),
                        MatchScore.scored_at.desc(),
                    )
                    .offset(skip)
                    .limit(limit)
                )

            rows = result.all()
            return [(row[0], row[1]) for row in rows]
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch jobs by relevance score")
            raise RepositoryError("Failed to fetch jobs by relevance score.") from exc

    @staticmethod
    def _normalize_text_filter(value: str | None) -> str | None:
        """Normalize optional text filter by trimming whitespace.

        Args:
            value: Optional text filter from service layer.

        Returns:
            Trimmed string when non-empty, otherwise ``None``.
        """
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _contains_pattern(value: str) -> str:
        """Build escaped SQL ILIKE contains pattern.

        Args:
            value: User-provided filter value.

        Returns:
            SQL pattern that performs case-insensitive contains matching.
        """
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    async def count_by_category(self, profile_id: int) -> dict[str, int]:
        """Count profile match scores grouped by category.

        Args:
            profile_id: Profile primary key used for grouping.

        Returns:
            Category-to-count mapping including zeroes for missing categories.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="count_by_category",
            profile_id=profile_id,
        )
        log.debug("Counting match scores by category")

        category_counts = {category: 0 for category in ALLOWED_MATCH_CATEGORIES}

        try:
            with db_query_timer(query_type="match_score_count_by_category"):
                result = await self.db.execute(
                    select(MatchScore.category, func.count(MatchScore.id))
                    .where(MatchScore.profile_id == profile_id)
                    .group_by(MatchScore.category)
                )

            for category, total in result.all():
                if category in category_counts:
                    category_counts[category] = int(total)

            return category_counts
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to count match scores by category")
            raise RepositoryError("Failed to count match scores by category.") from exc

    def _merge_missing_fields(
        self,
        existing: MatchScore,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Build update payload with only missing fields.

        Args:
            existing: Existing persisted score row.
            payload: Incoming candidate field updates.

        Returns:
            Subset payload containing only values that populate missing fields.
        """
        merged: dict[str, Any] = {}
        for field, value in payload.items():
            if field in PROTECTED_UPSERT_FIELDS:
                continue
            if self._is_missing(getattr(existing, field)) and not self._is_missing(
                value
            ):
                merged[field] = value
        return merged

    @staticmethod
    def _is_missing(value: object) -> bool:
        """Determine whether a field value should be treated as missing.

        Args:
            value: Candidate field value.

        Returns:
            ``True`` when value is considered missing.
        """
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False


__all__ = ["MatchScoreRepository"]
