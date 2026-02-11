"""Alembic environment configuration for async migrations."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from loguru import logger
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from src.core.config import settings
from src.db.base import Base

# Importing models ensures Alembic autogenerate can discover tables.
from src.models import job

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode.

    Returns:
        None

    Raises:
        RuntimeError: If migration context configuration fails.
    """
    try:
        url = config.get_main_option("sqlalchemy.url")
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            compare_type=True,
            compare_server_default=True,
            dialect_opts={"paramstyle": "named"},
        )

        with context.begin_transaction():
            context.run_migrations()

        logger.info("Alembic offline migrations completed")
    except Exception as exc:
        logger.error(
            "Alembic offline migration failed",
            error=str(exc),
            exc_info=True,
        )
        raise RuntimeError("Failed to run offline migrations") from exc


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations with a provided sync connection.

    Args:
        connection: Synchronous SQLAlchemy connection provided by Alembic.

    Returns:
        None
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode using an async SQLAlchemy engine.

    Returns:
        None

    Raises:
        RuntimeError: If engine initialization or migration execution fails.
    """
    connectable: AsyncEngine | None = None
    try:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        if connectable is None:
            raise RuntimeError("Failed to initialize Alembic async engine")

        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        logger.info("Alembic online migrations completed")
    except Exception as exc:
        logger.error(
            "Alembic online migration failed",
            error=str(exc),
            exc_info=True,
        )
        raise RuntimeError("Failed to run online migrations") from exc
    finally:
        if connectable is not None:
            await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
