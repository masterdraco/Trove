"""external_cache table

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-18

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "external_cache",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("namespace", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("key_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_external_cache_namespace", "external_cache", ["namespace"])
    op.create_index("ix_external_cache_key_hash", "external_cache", ["key_hash"])
    op.create_index("ix_external_cache_expires_at", "external_cache", ["expires_at"])
    op.create_index(
        "ux_external_cache_ns_key",
        "external_cache",
        ["namespace", "key_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_external_cache_ns_key", table_name="external_cache")
    op.drop_index("ix_external_cache_expires_at", table_name="external_cache")
    op.drop_index("ix_external_cache_key_hash", table_name="external_cache")
    op.drop_index("ix_external_cache_namespace", table_name="external_cache")
    op.drop_table("external_cache")
