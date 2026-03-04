"""Add standalone index on job_enrichments.job_id for efficient FK lookups.

Revision ID: 202603041020
Revises: 202603041010
Create Date: 2026-03-04 10:20:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041020"
down_revision: Union[str, Sequence[str], None] = "202603041010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add standalone index on job_id to accelerate FK-based lookups and JOINs."""
    op.create_index(
        "ix_job_enrichments_job_id",
        "job_enrichments",
        ["job_id"],
    )


def downgrade() -> None:
    """Drop the standalone job_id index."""
    op.drop_index(
        "ix_job_enrichments_job_id",
        table_name="job_enrichments",
    )
