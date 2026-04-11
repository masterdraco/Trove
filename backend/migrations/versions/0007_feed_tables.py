"""feed + rss_item tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-11

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "feed",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=False),
        sa.Column(
            "credentials_cipher",
            sqlmodel.sql.sqltypes.AutoString(length=4096),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("category_hint", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column(
            "protocol_hint",
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=False,
            server_default="torrent",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(), nullable=True),
        sa.Column("last_poll_status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column("last_poll_message", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_new_items", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_feed_name", "feed", ["name"], unique=True)

    op.create_table(
        "rss_item",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), sa.ForeignKey("feed.id"), nullable=False),
        sa.Column("guid", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column("normalized_title", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column("download_url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
        sa.Column("infohash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("seeders", sa.Integer(), nullable=True),
        sa.Column("leechers", sa.Integer(), nullable=True),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("raw_description", sqlmodel.sql.sqltypes.AutoString(length=4096), nullable=True),
    )
    op.create_index("ix_rss_item_feed_id", "rss_item", ["feed_id"])
    op.create_index("ix_rss_item_guid", "rss_item", ["guid"])
    op.create_index("ix_rss_item_title", "rss_item", ["title"])
    op.create_index("ix_rss_item_normalized_title", "rss_item", ["normalized_title"])
    op.create_index("ix_rss_item_infohash", "rss_item", ["infohash"])
    op.create_index("ix_rss_item_published_at", "rss_item", ["published_at"])
    op.create_index("ix_rss_item_fetched_at", "rss_item", ["fetched_at"])
    op.create_index("uq_rss_item_feed_guid", "rss_item", ["feed_id", "guid"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_rss_item_feed_guid", table_name="rss_item")
    op.drop_index("ix_rss_item_fetched_at", table_name="rss_item")
    op.drop_index("ix_rss_item_published_at", table_name="rss_item")
    op.drop_index("ix_rss_item_infohash", table_name="rss_item")
    op.drop_index("ix_rss_item_normalized_title", table_name="rss_item")
    op.drop_index("ix_rss_item_title", table_name="rss_item")
    op.drop_index("ix_rss_item_guid", table_name="rss_item")
    op.drop_index("ix_rss_item_feed_id", table_name="rss_item")
    op.drop_table("rss_item")
    op.drop_index("ix_feed_name", table_name="feed")
    op.drop_table("feed")
