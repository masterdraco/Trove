from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WatchlistItemRow(SQLModel, table=True):
    __tablename__ = "watchlist_item"

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(max_length=16)  # series | movie
    title: str = Field(max_length=256)
    year: int | None = Field(default=None)
    target_quality: str | None = Field(default=None, max_length=64)
    status: str = Field(default="active", max_length=32)  # active | done | paused
    notes: str | None = Field(default=None, max_length=1024)
    added_at: datetime = Field(default_factory=_utcnow)
