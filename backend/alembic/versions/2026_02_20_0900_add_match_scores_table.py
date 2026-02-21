"""Add match scores table

Revision ID: 202602200900
Revises: 202602191100
Create Date: 2026-02-20 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202602200900"
down_revision: Union[str, Sequence[str], None] = "202602191100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create match_scores table with constraints and indexes."""
    op.create_table(
        "match_scores",
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
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 100",
            name="ck_match_scores_relevance_score_range",
        ),
        sa.CheckConstraint(
            "category IN ('Most Relevant', 'Relevant', 'Somewhat Relevant', 'Not Relevant')",
            name="ck_match_scores_category_valid",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "profile_id", name="uq_match_scores_job_profile"),
    )
    op.create_index(
        "ix_match_scores_profile_id",
        "match_scores",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_match_scores_relevance_score_desc",
        "match_scores",
        [sa.text("relevance_score DESC")],
        unique=False,
    )
    op.create_index(
        "ix_match_scores_scored_at_desc",
        "match_scores",
        [sa.text("scored_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop match_scores table and related indexes."""
    op.drop_index("ix_match_scores_scored_at_desc", table_name="match_scores")
    op.drop_index("ix_match_scores_relevance_score_desc", table_name="match_scores")
    op.drop_index("ix_match_scores_profile_id", table_name="match_scores")
    op.drop_table("match_scores")
