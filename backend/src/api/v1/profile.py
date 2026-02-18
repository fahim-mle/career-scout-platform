"""Profile API endpoints for singleton profile management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger

from src.api.deps import get_profile_service
from src.core.exceptions import (
    BusinessLogicError,
    ConflictError,
    NotFoundError,
    RepositoryError,
)
from src.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate
from src.services.profile_service import ProfileService

router = APIRouter()


def _map_business_logic_error_status(error: BusinessLogicError) -> int:
    """Resolve HTTP status code for business errors.

    Args:
        error: Business layer exception raised by service.

    Returns:
        HTTP status code (500 for repository-caused failures, otherwise 400).
    """
    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(error.__cause__, RepositoryError)
        else status.HTTP_400_BAD_REQUEST
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """Get the singleton profile.

    Args:
        service: Profile service dependency.

    Returns:
        Profile response payload.

    Raises:
        HTTPException: If profile is missing or service access fails.
    """
    try:
        return await service.get_profile()
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=_map_business_logic_error_status(exc),
            detail=str(exc),
        ) from exc


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfileCreate,
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """Create the singleton profile.

    Args:
        payload: Profile create payload.
        service: Profile service dependency.

    Returns:
        Created profile response payload.

    Raises:
        HTTPException: If profile already exists or validation fails.
    """
    try:
        return await service.create_profile(payload)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=_map_business_logic_error_status(exc),
            detail=str(exc),
        ) from exc


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> ProfileResponse:
    """Update the singleton profile.

    Args:
        payload: Profile update payload.
        service: Profile service dependency.

    Returns:
        Updated profile response payload.

    Raises:
        HTTPException: If profile is missing or update fails.
    """
    try:
        return await service.update_profile(payload)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=_map_business_logic_error_status(exc),
            detail=str(exc),
        ) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> Response:
    """Delete the singleton profile.

    Args:
        service: Profile service dependency.

    Returns:
        Empty response for successful deletion.

    Raises:
        HTTPException: If profile is missing or delete fails.
    """
    try:
        await service.delete_profile()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except BusinessLogicError as exc:
        logger.error("Failed to delete profile", error=str(exc))
        raise HTTPException(
            status_code=_map_business_logic_error_status(exc),
            detail=str(exc),
        ) from exc


__all__ = ["router"]
