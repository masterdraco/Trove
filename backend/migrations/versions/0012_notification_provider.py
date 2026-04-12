"""notification_provider table

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "notification_provider",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column(
            "config_cipher",
            sqlmodel.sql.sqltypes.AutoString(length=4096),
            nullable=False,
        ),
        sa.Column(
            "events",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=False,
            server_default='["task.grabbed","download.completed","download.failed"]',
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("last_sent_ok", sa.Boolean(), nullable=True),
        sa.Column(
            "last_sent_message",
            sqlmodel.sql.sqltypes.AutoString(length=512),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_provider")
