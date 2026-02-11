"""Async SQLAlchemy session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator

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
