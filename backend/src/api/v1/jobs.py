"""Jobs API endpoints for CRUD operations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from loguru import logger

from src.api.deps import get_job_service, get_match_service
from src.core.exceptions import BusinessLogicError, NotFoundError
from src.schemas.job import (
    EnrichedJobResponse,
    JobCreate,
    JobResponse,
    JobUpdate,
    RawJobResponse,
)
from src.services.job_service import JobService
from src.services.match_service import MatchService

router = APIRouter()
raw_jobs_router = APIRouter()


@router.get("", response_model=list[EnrichedJobResponse])
async def list_jobs(
    service: Annotated[JobService, Depends(get_job_service)],
    match_service: Annotated[MatchService, Depends(get_match_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    sort: str = Query("date", pattern="^(date|relevance)$"),
    platform: str | None = None,
    is_active: bool = True,
) -> list[EnrichedJobResponse]:
    """List jobs with pagination and optional filters.

    Args:
        service: Job service dependency.
        skip: Number of rows to offset.
        limit: Maximum number of rows to return.
        sort: Sort strategy; date order or relevance score order.
        platform: Optional platform filter.
        is_active: Whether to return active jobs only.

    Returns:
        List of job response payloads.

    Raises:
        HTTPException: If business validation fails.
    """
    try:
        if sort == "relevance":
            return await match_service.list_jobs_by_relevance(
                skip=skip,
                limit=limit,
                platform=platform,
                is_active=is_active,
            )
        return await service.list_enriched_jobs(
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
        )
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@raw_jobs_router.get("/scraped_raw_jobs", response_model=list[RawJobResponse])
async def list_scraped_raw_jobs(
    service: Annotated[JobService, Depends(get_job_service)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    platform: str | None = None,
    is_active: bool = True,
) -> list[RawJobResponse]:
    """List raw scraped jobs with pagination and optional filters.

    Args:
        service: Job service dependency.
        skip: Number of rows to offset.
        limit: Maximum number of rows to return.
        platform: Optional platform filter.
        is_active: Whether to return active jobs only.

    Returns:
        List of raw scraped job response payloads.

    Raises:
        HTTPException: If business validation fails.
    """
    try:
        return await service.list_raw_jobs(
            skip=skip,
            limit=limit,
            platform=platform,
            is_active=is_active,
        )
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Get one job by ID.

    Args:
        job_id: Primary key of the job.
        service: Job service dependency.

    Returns:
        One job response payload.

    Raises:
        HTTPException: If job is missing or service fails.
    """
    try:
        return await service.get_job(job_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BusinessLogicError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Create a new job.

    Args:
        payload: Job create request payload.
        service: Job service dependency.

    Returns:
        Created job response payload.

    Raises:
        HTTPException: If business validation fails or a duplicate exists.
    """
    try:
        return await service.create_job(payload)
    except BusinessLogicError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already exists" in detail.lower()
            or "must remain unique" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    payload: JobUpdate,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    """Update an existing job.

    Args:
        job_id: Primary key of the job.
        payload: Partial update payload.
        service: Job service dependency.

    Returns:
        Updated job response payload.

    Raises:
        HTTPException: If job is missing, duplicate conflict, or business rule fails.
    """
    try:
        return await service.update_job(job_id, payload)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BusinessLogicError as exc:
        detail = str(exc)
        status_code = (
            status.HTTP_409_CONFLICT
            if "already exists" in detail.lower()
            or "must remain unique" in detail.lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    service: Annotated[JobService, Depends(get_job_service)],
) -> Response:
    """Soft-delete an existing job.

    Args:
        job_id: Primary key of the job.
        service: Job service dependency.

    Returns:
        Empty response for successful deletion.

    Raises:
        HTTPException: If job is missing or delete fails.
    """
    try:
        await service.delete_job(job_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BusinessLogicError as exc:
        logger.error("Failed to delete job", job_id=job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
