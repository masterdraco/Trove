from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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

    # TMDB discovery metadata — nullable so old rows keep working
    tmdb_id: int | None = Field(default=None, index=True)
    tmdb_type: str | None = Field(default=None, max_length=8)  # movie | tv
    poster_path: str | None = Field(default=None, max_length=256)
    backdrop_path: str | None = Field(default=None, max_length=256)
    overview: str | None = Field(default=None, max_length=4096)
    release_date: str | None = Field(default=None, max_length=16)
    rating: float | None = Field(default=None)

    # Auto-download integration
    discovery_status: str = Field(default="tracking", max_length=16)
    # tracking  — passive, no task yet
    # promoted  — a backing download task exists and is active
    # available — TMDB says release_date is in the past
    # downloaded — task reported success
    discovery_task_id: int | None = Field(default=None)
