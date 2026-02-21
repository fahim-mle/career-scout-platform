"""Add description_sections to job enrichments

Revision ID: 202602211030
Revises: 202602200900
Create Date: 2026-02-21 10:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602211030"
down_revision: Union[str, Sequence[str], None] = "202602200900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional structured description sections field."""
    op.add_column(
        "job_enrichments",
        sa.Column(
            "description_sections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove structured description sections field."""
    op.drop_column("job_enrichments", "description_sections")
