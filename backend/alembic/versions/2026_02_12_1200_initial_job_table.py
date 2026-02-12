"""Initial jobs table

Revision ID: 202602121200
Revises:
Create Date: 2026-02-12 12:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602121200"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial jobs table with constraints and indexes."""
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=True),
        sa.Column("description_short", sa.Text(), nullable=True),
        sa.Column("description_full", sa.Text(), nullable=True),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "salary_range",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "platform IN ('linkedin', 'seek', 'indeed')",
            name="ck_jobs_platform_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_id",
            "platform",
            name="uq_jobs_external_id_platform",
        ),
    )
    op.create_index("ix_jobs_is_active", "jobs", ["is_active"], unique=False)
    op.create_index("ix_jobs_platform", "jobs", ["platform"], unique=False)
    op.create_index("ix_jobs_posted_date", "jobs", ["posted_date"], unique=False)


def downgrade() -> None:
    """Drop jobs table and related indexes."""
    op.drop_index("ix_jobs_posted_date", table_name="jobs")
    op.drop_index("ix_jobs_platform", table_name="jobs")
    op.drop_index("ix_jobs_is_active", table_name="jobs")
    op.drop_table("jobs")
