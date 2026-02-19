"""Add job enrichments table

Revision ID: 202602191100
Revises: 202602180900
Create Date: 2026-02-19 11:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602191100"
down_revision: Union[str, Sequence[str], None] = "202602180900"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create job_enrichments table with constraints and indexes."""
    op.create_table(
        "job_enrichments",
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
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=True),
        sa.Column("salary_min", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("salary_max", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=True),
        sa.Column("salary_period", sa.String(length=20), nullable=True),
        sa.Column("salary_raw", sa.Text(), nullable=True),
        sa.Column("location_normalized", sa.String(length=255), nullable=True),
        sa.Column("confidence_overall", sa.Float(), nullable=True),
        sa.Column(
            "confidence_by_field",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "enriched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_job_enrichments_salary_min_lte_salary_max",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "extractor_version",
            name="uq_job_enrichments_job_id_extractor_version",
        ),
    )

    op.create_index(
        "ix_job_enrichments_job_status_enriched_at_desc",
        "job_enrichments",
        ["job_id", "status", sa.text("enriched_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop job_enrichments table and related indexes."""
    op.drop_index(
        "ix_job_enrichments_job_status_enriched_at_desc",
        table_name="job_enrichments",
    )
    op.drop_table("job_enrichments")
