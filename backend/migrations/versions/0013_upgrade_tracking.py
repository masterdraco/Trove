"""Add quality upgrade tracking columns to seen_release

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("seen_release") as batch:
        batch.add_column(sa.Column("quality_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("quality_tier", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("upgraded_from_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("seen_release") as batch:
        batch.drop_column("upgraded_from_id")
        batch.drop_column("quality_tier")
        batch.drop_column("quality_score")
