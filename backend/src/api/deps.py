"""Shared FastAPI dependency helpers for API routes."""

from typing import Annotated, AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.health import HealthService
from src.db.session import get_session_dependency
from src.repositories.job import JobRepository
from src.services.job_service import JobService


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session dependency.

    Returns:
        Async generator yielding one database session.
    """
    async for session in get_session_dependency():
        yield session


def get_request_id(request: Request) -> str:
    """Get request id from request context.

    Args:
        request: Incoming FastAPI request object.

    Returns:
        Request id string when available, otherwise ``"unknown"``.
    """
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return "unknown"


def get_health_service() -> HealthService:
    """Provide a health service dependency.

    Returns:
        HealthService configured for dependency checks.
    """
    return HealthService()


def get_job_service(db: AsyncSession = Depends(get_db_session)) -> JobService:
    """Provide a job service dependency.

    Args:
        db: Active async DB session provided by dependency injection.

    Returns:
        JobService configured with a JobRepository bound to the session.
    """
    return JobService(JobRepository(db))


DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

__all__ = [
    "DBSessionDep",
    "get_db_session",
    "get_health_service",
    "get_job_service",
    "get_request_id",
]
