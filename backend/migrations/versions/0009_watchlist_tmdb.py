"""watchlist TMDB discovery columns

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("watchlist_item") as batch:
        batch.add_column(sa.Column("tmdb_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("tmdb_type", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=True)
        )
        batch.add_column(
            sa.Column("poster_path", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True)
        )
        batch.add_column(
            sa.Column("backdrop_path", sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True)
        )
        batch.add_column(
            sa.Column("overview", sqlmodel.sql.sqltypes.AutoString(length=4096), nullable=True)
        )
        batch.add_column(
            sa.Column("release_date", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True)
        )
        batch.add_column(sa.Column("rating", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "discovery_status",
                sqlmodel.sql.sqltypes.AutoString(length=16),
                nullable=False,
                server_default="tracking",
            )
        )
        batch.add_column(sa.Column("discovery_task_id", sa.Integer(), nullable=True))
    op.create_index("ix_watchlist_tmdb_id", "watchlist_item", ["tmdb_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_tmdb_id", table_name="watchlist_item")
    with op.batch_alter_table("watchlist_item") as batch:
        batch.drop_column("discovery_task_id")
        batch.drop_column("discovery_status")
        batch.drop_column("rating")
        batch.drop_column("release_date")
        batch.drop_column("overview")
        batch.drop_column("backdrop_path")
        batch.drop_column("poster_path")
        batch.drop_column("tmdb_type")
        batch.drop_column("tmdb_id")
