from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FeedRow(SQLModel, table=True):
    __tablename__ = "feed"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, min_length=1, max_length=128)
    url: str = Field(max_length=1024)
    credentials_cipher: str | None = Field(default=None, max_length=4096)
    enabled: bool = Field(default=True)
    poll_interval_seconds: int = Field(default=600)  # 10 minutes
    retention_days: int = Field(default=90)  # keep items for 90 days
    category_hint: str | None = Field(default=None, max_length=64)  # optional default category
    protocol_hint: str = Field(default="torrent", max_length=16)  # torrent|usenet
    created_at: datetime = Field(default_factory=_utcnow)
    last_polled_at: datetime | None = Field(default=None)
    last_poll_status: str | None = Field(default=None, max_length=32)
    last_poll_message: str | None = Field(default=None, max_length=512)
    total_items: int = Field(default=0)
    last_new_items: int = Field(default=0)


class RssItemRow(SQLModel, table=True):
    __tablename__ = "rss_item"

    id: int | None = Field(default=None, primary_key=True)
    feed_id: int = Field(index=True, foreign_key="feed.id")
    guid: str = Field(index=True, max_length=512)
    title: str = Field(index=True, max_length=512)
    normalized_title: str = Field(index=True, max_length=512)
    download_url: str = Field(max_length=2048)
    infohash: str | None = Field(default=None, index=True, max_length=64)
    size: int | None = Field(default=None)
    seeders: int | None = Field(default=None)
    leechers: int | None = Field(default=None)
    category: str | None = Field(default=None, max_length=64)
    published_at: datetime | None = Field(default=None, index=True)
    fetched_at: datetime = Field(default_factory=_utcnow, index=True)
    raw_description: str | None = Field(default=None, max_length=4096)
