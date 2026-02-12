"""Shared pytest fixtures for backend repository tests."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.db.base import Base
from tests.factories import job_factory


def _default_test_database_url() -> str:
    """Build a default test DB URL using env vars and local secrets fallback."""
    host = os.getenv("TEST_DB_HOST", "localhost")
    port = os.getenv("TEST_DB_PORT", "5432")
    user = os.getenv("TEST_DB_USER", os.getenv("DB_USER", "postgres"))
    name = os.getenv("TEST_DB_NAME", "career_scout_test")

    password = os.getenv("TEST_DB_PASSWORD") or os.getenv("DB_PASSWORD", "")
    if not password:
        secrets_password_file = (
            Path(__file__).resolve().parents[2] / "secrets" / "db_password.txt"
        )
        if secrets_password_file.is_file():
            password = secrets_password_file.read_text(encoding="utf-8").strip()

    return (
        f"postgresql+asyncpg://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{name}"
    )


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", _default_test_database_url())


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an isolated engine and ensure schema lifecycle for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a per-test async session and cleanup DB state."""
    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.execute(text("TRUNCATE TABLE jobs RESTART IDENTITY CASCADE"))
            await session.commit()
