"""Shared FastAPI dependency helpers for API routes."""

from typing import Annotated, AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session_dependency


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


DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

__all__ = ["DBSessionDep", "get_db_session", "get_request_id"]
