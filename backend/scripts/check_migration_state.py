"""Detect whether a legacy database needs Alembic stamping."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings

APP_TABLES = ("jobs", "profiles", "job_enrichments", "match_scores")


async def main() -> int:
    """Return process code indicating whether Alembic stamp is required.

    Exit codes:
      0: No stamp required.
     10: Legacy schema detected (tables exist but alembic_version is missing).
    """
    engine = create_async_engine(settings.DATABASE_URL, future=True)
    try:
        async with engine.connect() as connection:
            version_table = await connection.execute(
                text("SELECT to_regclass('public.alembic_version')")
            )
            if version_table.scalar_one_or_none() is not None:
                return 0

            table_count = await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:table_names)
                    """
                ),
                {"table_names": list(APP_TABLES)},
            )
            existing_tables = table_count.scalar_one()
            if isinstance(existing_tables, int) and existing_tables > 0:
                return 10

            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
