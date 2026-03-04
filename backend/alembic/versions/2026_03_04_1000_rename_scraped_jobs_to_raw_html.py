"""Rename scraped_jobs column to raw_html on jobs table.

Revision ID: 202603041000
Revises: 202602221900
Create Date: 2026-03-04 10:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041000"
down_revision: Union[str, Sequence[str], None] = "202602221900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename scraped_jobs to raw_html; preserves all existing data."""
    op.alter_column("jobs", "scraped_jobs", new_column_name="raw_html")


def downgrade() -> None:
    """Revert raw_html back to scraped_jobs."""
    op.alter_column("jobs", "raw_html", new_column_name="scraped_jobs")
