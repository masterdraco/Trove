"""ai_cache table

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ai_cache",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("prompt_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_ai_cache_prompt_hash", "ai_cache", ["prompt_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ai_cache_prompt_hash", table_name="ai_cache")
    op.drop_table("ai_cache")
