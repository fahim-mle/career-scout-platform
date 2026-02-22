"""Add generic scraped payload columns to jobs.

Revision ID: 202602221900
Revises: 202602220900
Create Date: 2026-02-22 19:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602221900"
down_revision: Union[str, Sequence[str], None] = "202602220900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable raw scrape payload and generic metadata columns."""
    op.add_column("jobs", sa.Column("scraped_jobs", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_jobs_metadata_gin",
        "jobs",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove raw scrape payload and generic metadata columns."""
    op.drop_index("ix_jobs_metadata_gin", table_name="jobs")
    op.drop_column("jobs", "metadata")
    op.drop_column("jobs", "scraped_jobs")
