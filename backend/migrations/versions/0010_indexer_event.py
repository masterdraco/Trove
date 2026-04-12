"""indexer_event table for health dashboard

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "indexer_event",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("indexer_id", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("query", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.ForeignKeyConstraint(["indexer_id"], ["indexer.id"]),
    )
    op.create_index("ix_indexer_event_indexer_id", "indexer_event", ["indexer_id"])
    op.create_index("ix_indexer_event_at", "indexer_event", ["at"])


def downgrade() -> None:
    op.drop_index("ix_indexer_event_at", table_name="indexer_event")
    op.drop_index("ix_indexer_event_indexer_id", table_name="indexer_event")
    op.drop_table("indexer_event")
