"""Business logic service for profile operations."""

from __future__ import annotations

from loguru import logger
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import (
    BusinessLogicError,
    ConflictError,
    NotFoundError,
    RepositoryError,
)
from src.repositories.profile import ProfileRepository
from src.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate


class ProfileService:
    """Service layer for singleton profile business rules."""

    def __init__(self, repo: ProfileRepository):
        """Initialize ProfileService.

        Args:
            repo: Repository used for profile persistence operations.
        """
        self.repo = repo

    async def get_profile(self) -> ProfileResponse:
        """Get the singleton profile.

        Returns:
            Serialized profile response.

        Raises:
            NotFoundError: If no profile exists.
            BusinessLogicError: If repository access fails.
        """
        log = logger.bind(service=self.__class__.__name__, operation="get_profile")
        log.info("Fetching profile")

        try:
            profile = await self.repo.get_first()
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Repository error while fetching profile")
            raise BusinessLogicError("Failed to fetch profile.") from exc

        if profile is None:
            log.warning("Profile not found")
            raise NotFoundError("Profile not found.")

        log.bind(profile_id=profile.id).info("Fetched profile")
        return ProfileResponse.model_validate(profile)

    async def create_profile(self, payload: ProfileCreate) -> ProfileResponse:
        """Create the singleton profile.

        Args:
            payload: Profile creation payload.

        Returns:
            Serialized created profile response.

        Raises:
            ConflictError: If profile already exists.
            BusinessLogicError: If validation fails or repository fails.
        """
        log = logger.bind(service=self.__class__.__name__, operation="create_profile")
        log.info("Creating profile")

        self._validate_experience_years(payload.experience_years)
        self._validate_skills(payload.skills)

        try:
            existing = await self.repo.get_first()
            if existing is not None:
                log.bind(profile_id=existing.id).warning("Profile already exists")
                raise ConflictError(
                    "Profile already exists. Only one profile is allowed."
                )

            profile = await self.repo.create(payload.model_dump(mode="python"))
        except ConflictError:
            raise
        except RepositoryError as exc:
            if self._is_singleton_conflict_error(exc):
                log.bind(error=str(exc)).warning(
                    "Profile create conflict from concurrent insert"
                )
                raise ConflictError(
                    "Profile already exists. Only one profile is allowed."
                ) from exc
            log.bind(error=str(exc)).error("Failed to create profile")
            raise BusinessLogicError(f"Failed to create profile: {exc}") from exc
        except ValueError as exc:
            log.bind(error=str(exc)).error("Failed to create profile")
            raise BusinessLogicError(f"Failed to create profile: {exc}") from exc

        log.bind(profile_id=profile.id).info("Created profile")
        return ProfileResponse.model_validate(profile)

    async def update_profile(self, payload: ProfileUpdate) -> ProfileResponse:
        """Update the singleton profile.

        Args:
            payload: Partial profile update payload.

        Returns:
            Serialized updated profile response.

        Raises:
            NotFoundError: If profile does not exist.
            BusinessLogicError: If validation fails or repository actions fail.
        """
        log = logger.bind(service=self.__class__.__name__, operation="update_profile")
        log.info("Updating profile")

        try:
            existing = await self.repo.get_first()
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile before update")
            raise BusinessLogicError("Failed to update profile.") from exc

        if existing is None:
            log.warning("Profile not found for update")
            raise NotFoundError("Profile not found.")

        update_data = payload.model_dump(exclude_unset=True, mode="python")
        if not update_data:
            log.bind(profile_id=existing.id).info("No fields provided for update")
            return ProfileResponse.model_validate(existing)

        if "experience_years" in update_data:
            self._validate_experience_years(update_data["experience_years"])
        if "skills" in update_data:
            self._validate_skills(update_data["skills"])

        try:
            updated = await self.repo.update(existing.id, update_data)
        except (RepositoryError, ValueError) as exc:
            log.bind(error=str(exc)).error("Failed to update profile")
            raise BusinessLogicError(f"Failed to update profile: {exc}") from exc

        if updated is None:
            log.warning("Profile disappeared during update")
            raise NotFoundError("Profile not found.")

        log.bind(profile_id=updated.id).info("Updated profile")
        return ProfileResponse.model_validate(updated)

    async def delete_profile(self) -> bool:
        """Delete the singleton profile.

        Returns:
            ``True`` when delete succeeds.

        Raises:
            NotFoundError: If no profile exists.
            BusinessLogicError: If repository actions fail.
        """
        log = logger.bind(service=self.__class__.__name__, operation="delete_profile")
        log.info("Deleting profile")

        try:
            existing = await self.repo.get_first()
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to fetch profile before delete")
            raise BusinessLogicError("Failed to delete profile.") from exc

        if existing is None:
            log.warning("Profile not found for delete")
            raise NotFoundError("Profile not found.")

        try:
            deleted = await self.repo.delete(existing.id)
        except RepositoryError as exc:
            log.bind(error=str(exc)).error("Failed to delete profile")
            raise BusinessLogicError("Failed to delete profile.") from exc

        if not deleted:
            log.warning("Profile disappeared during delete")
            raise NotFoundError("Profile not found.")

        log.bind(profile_id=existing.id).info("Deleted profile")
        return True

    def _validate_experience_years(self, experience_years: object) -> None:
        """Validate business rule for profile experience years.

        Args:
            experience_years: Candidate experience years value.

        Returns:
            None.

        Raises:
            BusinessLogicError: If value is invalid.
        """
        if isinstance(experience_years, bool) or not isinstance(experience_years, int):
            raise BusinessLogicError("experience_years must be a non-negative integer.")
        if experience_years < 0:
            raise BusinessLogicError("experience_years must be a non-negative integer.")

    def _validate_skills(self, skills: object) -> None:
        """Validate business rule for profile skills.

        Args:
            skills: Candidate skills list.

        Returns:
            None.

        Raises:
            BusinessLogicError: If skills payload is invalid.
        """
        if not isinstance(skills, list):
            raise BusinessLogicError("skills must contain at least one skill.")
        if not skills:
            raise BusinessLogicError("skills must contain at least one skill.")
        if any(not isinstance(skill, str) or not skill.strip() for skill in skills):
            raise BusinessLogicError("skills must contain only non-empty strings.")

    def _is_singleton_conflict_error(self, error: RepositoryError) -> bool:
        """Determine whether repository error is singleton unique conflict.

        Args:
            error: Repository exception raised during create.

        Returns:
            ``True`` when error originates from unique/singleton constraint violation.
        """
        cause = error.__cause__
        if not isinstance(cause, IntegrityError):
            return False

        original = getattr(cause, "orig", None)
        constraint_name = getattr(
            getattr(original, "diag", None), "constraint_name", None
        ) or getattr(original, "constraint_name", "")
        error_code = getattr(original, "pgcode", None) or getattr(
            original, "sqlstate", ""
        )

        if constraint_name == "uq_profiles_singleton":
            return True

        detail = str(cause).lower()
        return error_code == "23505" and "uq_profiles_singleton" in detail


__all__ = ["ProfileService"]
