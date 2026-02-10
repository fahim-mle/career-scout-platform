"""Async SQLAlchemy session management."""

import asyncio
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.exc import OperationalError
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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session with connection retries.

    Yields:
        AsyncSession: Database session instance.

    Raises:
        OperationalError: If the database connection fails after retries.
    """
    max_retries = settings.DB_CONNECT_RETRIES
    delay_seconds = settings.DB_CONNECT_RETRY_DELAY

    for attempt in range(1, max_retries + 1):
        try:
            async with AsyncSessionLocal() as session:
                yield session
                return
        except OperationalError as exc:
            if attempt < max_retries:
                logger.warning(
                    f"Database connection failed; retrying ({attempt}/{max_retries})",
                    error=str(exc),
                )
                await asyncio.sleep(delay_seconds)
                continue

            logger.error(
                f"Database connection failed after {max_retries} retries",
                error=str(exc),
            )
            raise
