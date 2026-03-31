"""Detect whether a legacy database needs Alembic stamping."""

from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings

APP_TABLES = ("jobs", "profiles", "job_enrichments", "match_scores")
MAX_RETRIES = 5
RETRY_DELAY = 2


async def main() -> int:
    """Return process code indicating whether Alembic stamp is required.

    Exit codes:
      0: No stamp required.
     10: Legacy schema detected (tables exist but alembic_version is missing).
    """
    engine = None
    last_exception = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            engine = create_async_engine(settings.DATABASE_URL)
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
                          AND table_name = ANY(CAST(:table_names AS text[]))
                        """
                    ).bindparams(bindparam("table_names", type_=ARRAY(Text()))),
                    {"table_names": list(APP_TABLES)},
                )
                existing_tables = int(table_count.scalar_one())
                if existing_tables > 0:
                    return 10

                return 0
        except Exception as exc:
            last_exception = exc
            print(
                f"Failed to check migration state (attempt {attempt}/{MAX_RETRIES}): {exc}",
                file=sys.stderr,
            )

            if attempt < MAX_RETRIES:
                print(f"Retrying in {RETRY_DELAY} seconds...", file=sys.stderr)
                time.sleep(RETRY_DELAY)
            else:
                print(
                    f"Failed to check migration state after {MAX_RETRIES} attempts",
                    file=sys.stderr,
                )
                return 1
        finally:
            if engine is not None:
                await engine.dispose()
                engine = None

    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
