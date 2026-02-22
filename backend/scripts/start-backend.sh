#!/usr/bin/env sh
set -eu

echo "Applying database migrations..."
set +e
PYTHONPATH=/app python /app/scripts/check_migration_state.py
MIGRATION_STATE_EXIT=$?
set -e

if [ "$MIGRATION_STATE_EXIT" -eq 10 ]; then
  echo "Legacy schema detected without Alembic version table; stamping head."
  python -m alembic stamp head
elif [ "$MIGRATION_STATE_EXIT" -ne 0 ]; then
  echo "Failed to check migration state (exit $MIGRATION_STATE_EXIT)."
  exit "$MIGRATION_STATE_EXIT"
fi

if ! python -m alembic upgrade head; then
  echo "Alembic upgrade failed; refusing automatic stamp fallback to avoid masking migration drift."
  if [ "${ALLOW_UNSAFE_ALEMBIC_STAMP:-false}" = "true" ]; then
    echo "ALLOW_UNSAFE_ALEMBIC_STAMP=true set; applying unsafe fallback stamp for local recovery."
    python -m alembic stamp head
    python -m alembic upgrade head
  else
    exit 1
  fi
fi

echo "Starting backend server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
