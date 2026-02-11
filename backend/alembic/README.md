# Alembic Migrations

This project uses Alembic for database schema migrations.

## Configuration

- Migration scripts live under `alembic/versions/`.
- Alembic reads the database URL at runtime from `src.core.config.settings.DATABASE_URL` via `alembic/env.py`.
- No database secrets are committed in `alembic.ini`; the URL is injected from application settings.

## Usage

Run from the backend directory:

```bash
alembic upgrade head
alembic current
alembic downgrade -1
```

Create a new migration (optional):

```bash
alembic revision --autogenerate -m "describe change"
```

## Async Support

`alembic/env.py` is configured to run online migrations with an async SQLAlchemy engine (`postgresql+asyncpg`).
Alembic executes the migration operations through `connection.run_sync(...)` as recommended for async projects.
