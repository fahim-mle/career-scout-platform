"""Add scorer_version column to match_scores to track LLM/prompt version.

Revision ID: 202603041030
Revises: 202603041020
Create Date: 2026-03-04 10:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603041030"
down_revision: Union[str, Sequence[str], None] = "202603041020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable scorer_version column to match_scores."""
    op.add_column(
        "match_scores",
        sa.Column("scorer_version", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    """Drop scorer_version column from match_scores."""
    op.drop_column("match_scores", "scorer_version")
