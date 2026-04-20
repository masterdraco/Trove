"""indexer.catalog_slug column

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-20

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("indexer") as batch:
        batch.add_column(
            sa.Column(
                "catalog_slug",
                sqlmodel.sql.sqltypes.AutoString(length=64),
                nullable=True,
            )
        )
    op.create_index(
        "ix_indexer_catalog_slug", "indexer", ["catalog_slug"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_indexer_catalog_slug", table_name="indexer")
    with op.batch_alter_table("indexer") as batch:
        batch.drop_column("catalog_slug")
