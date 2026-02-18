"""Data access repository for Profile entities."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import RepositoryError
from src.core.metrics import db_query_timer
from src.models.profile import Profile
from src.repositories.base import BaseRepository

PROTECTED_UPDATE_FIELDS = frozenset({"id", "created_at", "updated_at"})
PROTECTED_CREATE_FIELDS = frozenset({"id", "created_at", "updated_at"})


class ProfileRepository(BaseRepository[Profile]):
    """Repository responsible for profile persistence operations."""

    def __init__(self, db: AsyncSession):
        """Initialize ProfileRepository.

        Args:
            db: Active asynchronous SQLAlchemy session.
        """
        super().__init__(db=db, model_type=Profile)
        self._column_names = {column.key for column in Profile.__table__.columns}

    async def get_first(self) -> Profile | None:
        """Fetch the first profile record.

        Returns:
            First profile ordered by id when present, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(repository=self.__class__.__name__, operation="get_first")
        log.debug("Fetching first profile")

        try:
            with db_query_timer(query_type="profile_get_first"):
                result = await self.db.execute(
                    select(Profile).order_by(Profile.id.asc())
                )
            profile = result.scalars().first()
            log.bind(found=profile is not None).debug("Fetched first profile")
            return profile
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch first profile")
            raise RepositoryError("Failed to fetch profile.") from exc

    async def get_by_id(self, profile_id: int) -> Profile | None:
        """Fetch one profile by primary key.

        Args:
            profile_id: Profile primary key.

        Returns:
            Matching profile when found, otherwise ``None``.

        Raises:
            RepositoryError: If database query fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="get_by_id",
            profile_id=profile_id,
        )
        log.debug("Fetching profile by id")

        try:
            with db_query_timer(query_type="profile_get_by_id"):
                result = await self.db.execute(
                    select(Profile).where(Profile.id == profile_id)
                )
            profile = result.scalar_one_or_none()
            log.bind(found=profile is not None).debug("Fetched profile by id")
            return profile
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile by id")
            raise RepositoryError("Failed to fetch profile by id.") from exc

    async def create(self, profile_data: dict[str, Any]) -> Profile:
        """Create a new profile record.

        Args:
            profile_data: Field-value mapping for a new profile.

        Returns:
            Persisted profile entity.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload attempts to set protected fields.
        """
        log = logger.bind(repository=self.__class__.__name__, operation="create")
        log.info("Creating profile")

        try:
            invalid = PROTECTED_CREATE_FIELDS & profile_data.keys()
            if invalid:
                blocked = ", ".join(sorted(invalid))
                raise ValueError(f"Cannot set protected fields: {blocked}")

            profile = Profile(**profile_data)
            with db_query_timer(query_type="profile_create"):
                self.db.add(profile)
                created_profile = await self._commit_and_refresh(profile)
            log.bind(profile_id=created_profile.id).info("Created profile")
            return created_profile
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during profile create")
            raise RepositoryError(
                "Failed to create profile due to integrity error."
            ) from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during profile create")
            raise RepositoryError("Failed to create profile.") from exc

    async def update(
        self,
        profile_id: int,
        profile_data: dict[str, Any],
    ) -> Profile | None:
        """Update an existing profile record.

        Args:
            profile_id: Existing profile primary key.
            profile_data: Field-value mapping to update.

        Returns:
            Updated profile when found, otherwise ``None``.

        Raises:
            RepositoryError: If database write fails.
            ValueError: If payload contains protected or unknown fields.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="update",
            profile_id=profile_id,
        )
        log.info("Updating profile")

        try:
            with db_query_timer(query_type="profile_update_lookup"):
                result = await self.db.execute(
                    select(Profile).where(Profile.id == profile_id)
                )
            profile = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile for update")
            raise RepositoryError("Failed to fetch profile for update.") from exc

        if profile is None:
            log.info("Profile not found for update")
            return None

        for field, value in profile_data.items():
            if field in PROTECTED_UPDATE_FIELDS:
                raise ValueError(f"Cannot update protected field: {field}")
            if field.startswith("_") or field not in self._column_names:
                raise ValueError(f"Unknown or unsafe update field: {field}")
            setattr(profile, field, value)

        try:
            with db_query_timer(query_type="profile_update"):
                updated_profile = await self._commit_and_refresh(profile)
            log.info("Updated profile")
            return updated_profile
        except IntegrityError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Integrity error during profile update")
            raise RepositoryError(
                "Failed to update profile due to integrity error."
            ) from exc
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Database error during profile update")
            raise RepositoryError("Failed to update profile.") from exc

    async def delete(self, profile_id: int) -> bool:
        """Delete an existing profile record.

        Args:
            profile_id: Existing profile primary key.

        Returns:
            ``True`` when deleted, otherwise ``False`` when not found.

        Raises:
            RepositoryError: If database delete fails.
        """
        log = logger.bind(
            repository=self.__class__.__name__,
            operation="delete",
            profile_id=profile_id,
        )
        log.info("Deleting profile")

        try:
            with db_query_timer(query_type="profile_delete_lookup"):
                result = await self.db.execute(
                    select(Profile).where(Profile.id == profile_id)
                )
            profile = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile for delete")
            raise RepositoryError("Failed to fetch profile for delete.") from exc

        if profile is None:
            log.info("Profile not found for delete")
            return False

        try:
            with db_query_timer(query_type="profile_delete"):
                await self.db.delete(profile)
                await self.db.commit()
            log.info("Deleted profile")
            return True
        except SQLAlchemyError as exc:
            await self._rollback_safely()
            log.bind(error=str(exc)).error("Failed to delete profile")
            raise RepositoryError("Failed to delete profile.") from exc


__all__ = ["ProfileRepository"]
