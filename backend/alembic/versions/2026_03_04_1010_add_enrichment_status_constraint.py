"""Add CHECK constraint on job_enrichments.status column.

Revision ID: 202603041010
Revises: 202603041000
Create Date: 2026-03-04 10:10:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041010"
down_revision: Union[str, Sequence[str], None] = "202603041000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Constrain job_enrichments.status to the four allowed lifecycle values."""
    op.create_check_constraint(
        "ck_job_enrichments_status_valid",
        "job_enrichments",
        "status IN ('pending', 'completed', 'failed', 'stale')",
    )


def downgrade() -> None:
    """Drop the status CHECK constraint, reverting to unconstrained String."""
    op.drop_constraint(
        "ck_job_enrichments_status_valid",
        "job_enrichments",
        type_="check",
    )
