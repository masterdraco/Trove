"""indexer table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "indexer",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("protocol", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("base_url", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column(
            "credentials_cipher",
            sqlmodel.sql.sqltypes.AutoString(length=4096),
            nullable=False,
        ),
        sa.Column("definition_yaml", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_test_at", sa.DateTime(), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column(
            "last_test_message", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True
        ),
    )
    op.create_index("ix_indexer_name", "indexer", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_indexer_name", table_name="indexer")
    op.drop_table("indexer")
