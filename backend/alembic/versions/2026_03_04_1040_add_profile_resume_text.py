"""Add resume_text column to profiles to store parsed resume text for LLM context.

Revision ID: 202603041040
Revises: 202603041030
Create Date: 2026-03-04 10:40:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041040"
down_revision: Union[str, Sequence[str], None] = "202603041030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable resume_text column to profiles."""
    op.add_column(
        "profiles",
        sa.Column("resume_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop resume_text column from profiles."""
    op.drop_column("profiles", "resume_text")
