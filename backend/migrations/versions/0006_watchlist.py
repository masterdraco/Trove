"""watchlist table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_item",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("target_quality", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("watchlist_item")
