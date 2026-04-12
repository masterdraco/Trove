"""download state tracking on seen_release

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-12

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("seen_release") as batch:
        batch.add_column(sa.Column("client_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "grabbed_identifier",
                sqlmodel.sql.sqltypes.AutoString(length=128),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "download_status",
                sqlmodel.sql.sqltypes.AutoString(length=16),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("download_progress", sa.Float(), nullable=True))
        batch.add_column(sa.Column("download_size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("download_downloaded_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("download_eta_seconds", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "download_error_message",
                sqlmodel.sql.sqltypes.AutoString(length=512),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("download_state_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_seen_release_download_status",
        "seen_release",
        ["download_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_seen_release_download_status", table_name="seen_release")
    with op.batch_alter_table("seen_release") as batch:
        batch.drop_column("download_state_at")
        batch.drop_column("download_error_message")
        batch.drop_column("download_eta_seconds")
        batch.drop_column("download_downloaded_bytes")
        batch.drop_column("download_size_bytes")
        batch.drop_column("download_progress")
        batch.drop_column("download_status")
        batch.drop_column("grabbed_identifier")
        batch.drop_column("client_id")
