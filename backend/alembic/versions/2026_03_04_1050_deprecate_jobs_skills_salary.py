"""Deprecate jobs.skills and jobs.salary_range in favour of job_enrichments equivalents.

Revision ID: 202603041050
Revises: 202603041040
Create Date: 2026-03-04 10:50:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041050"
down_revision: Union[str, Sequence[str], None] = "202603041040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mark jobs.skills and jobs.salary_range as deprecated via SQL comments."""
    op.execute(
        "COMMENT ON COLUMN jobs.skills IS "
        "'DEPRECATED: Use job_enrichments.skills instead'"
    )
    op.execute(
        "COMMENT ON COLUMN jobs.salary_range IS "
        "'DEPRECATED: Use job_enrichments salary fields instead'"
    )


def downgrade() -> None:
    """Clear deprecation comments from jobs.skills and jobs.salary_range."""
    op.execute("COMMENT ON COLUMN jobs.skills IS NULL")
    op.execute("COMMENT ON COLUMN jobs.salary_range IS NULL")
