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
    """
    Constructs a default PostgreSQL asyncpg connection URL for tests using environment variables with a secrets-file fallback.
    
    Reads configuration from environment variables with these defaults:
    - host: TEST_DB_HOST or "localhost"
    - port: TEST_DB_PORT or "5432"
    - user: TEST_DB_USER, then DB_USER, or "postgres"
    - database name: TEST_DB_NAME or "career_scout_test"
    Password resolution order:
    1. TEST_DB_PASSWORD
    2. DB_PASSWORD
    3. secrets/db_password.txt located two levels above this file (if present)
    
    The returned URL includes URL-encoded credentials.
    
    Returns:
        str: A connection URL in the form "postgresql+asyncpg://<user>:<password>@<host>:<port>/<name>".
    """
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
    """
    Provide an AsyncEngine connected to the test database with the schema created before tests and dropped after tests.
    
    Yields:
        AsyncEngine: Engine instance bound to the test database with Base.metadata created for the test session.
    """
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
    """
    Provide a per-test database session and ensure test-specific cleanup.
    
    Yields an AsyncSession for use in a test. After the test completes, any pending transactions are rolled back, the `jobs` table is truncated with identity restart and cascade, and the changes are committed.
    
    Returns:
        session (AsyncSession): Database session scoped to the current test.
    """
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