"""Normalize duplicated LinkedIn job titles.

Revision ID: 202602220900
Revises: 202602211030
Create Date: 2026-02-22 09:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202602220900"
down_revision: Union[str, Sequence[str], None] = "202602211030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Collapse exact adjacent duplicate title phrases for LinkedIn rows."""
    op.execute(
        """
        UPDATE jobs
        SET title = regexp_replace(
            regexp_replace(title, '\\s+', ' ', 'g'),
            '^(.+?)\\s+\\1$',
            '\\1',
            'i'
        )
        WHERE platform = 'linkedin'
          AND title IS NOT NULL
          AND regexp_replace(title, '\\s+', ' ', 'g') ~* '^(.+?)\\s+\\1$';
        """
    )


def downgrade() -> None:
    """No-op because title cleanup is a one-way data correction."""
    return None
