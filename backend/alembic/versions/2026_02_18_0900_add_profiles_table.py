"""Add profiles table

Revision ID: 202602180900
Revises: 202602121200
Create Date: 2026-02-18 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602180900"
down_revision: Union[str, Sequence[str], None] = "202602121200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create profiles table with constraints and indexes."""
    op.create_table(
        "profiles",
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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("experience_years", sa.Integer(), nullable=False),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "experience_years >= 0",
            name="ck_profiles_experience_years_non_negative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(skills) = 'array' AND jsonb_array_length(skills) > 0",
            name="ck_profiles_skills_non_empty_array",
        ),
        sa.CheckConstraint(
            "preferences IS NULL OR jsonb_typeof(preferences) = 'object'",
            name="ck_profiles_preferences_object",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_location", "profiles", ["location"], unique=False)
    op.create_index(
        "ix_profiles_skills_gin",
        "profiles",
        ["skills"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop profiles table and related indexes."""
    op.drop_index("ix_profiles_skills_gin", table_name="profiles")
    op.drop_index("ix_profiles_location", table_name="profiles")
    op.drop_table("profiles")
