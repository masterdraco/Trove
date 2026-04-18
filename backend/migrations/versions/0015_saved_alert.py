"""saved_alert table

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-18

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "saved_alert",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column(
            "keywords",
            sqlmodel.sql.sqltypes.AutoString(length=512),
            nullable=False,
            server_default="",
        ),
        sa.Column("protocol", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "check_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("last_check_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_seen_titles",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("saved_alert")
