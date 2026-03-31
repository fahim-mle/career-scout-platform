"""Async SQLAlchemy session management."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterator, Coroutine, TypeVar

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

_T = TypeVar("_T")

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Provide an async DB session as a context manager.

    This enables usage such as ``async with get_session() as db:``.

    Yields:
        AsyncSession: Database session instance.

    """
    async with AsyncSessionLocal() as session:
        yield session


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for FastAPI dependency injection.

    Yields:
        AsyncSession: Database session instance.

    Raises:
        SQLAlchemyError: If session setup or teardown fails.
    """
    async with get_session() as session:
        yield session


def run_with_cleanup(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine and dispose the DB engine pool afterwards.

    Use this in Celery tasks instead of ``asyncio.run()`` when the worker
    uses ``--pool=solo``.  The solo pool runs all tasks in the same OS thread
    sequentially, so each ``asyncio.run()`` creates a fresh event loop.
    Without cleanup the asyncpg connection pool from the previous loop is
    still cached on the engine, causing a
    ``Future attached to a different loop`` error in the next task.

    Disposing the engine after each run tears down the pool so the next
    invocation starts with a clean slate.

    Args:
        coro: Coroutine to execute.

    Returns:
        The coroutine's return value.
    """

    async def _wrapper() -> _T:
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(_wrapper())


async def database_health_check() -> bool:
    """Validate database connectivity with a lightweight query.

    Returns:
        bool: ``True`` when the database responds to ``SELECT 1``.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Database health check failed", error=str(exc))
        return False
    else:
        return True
