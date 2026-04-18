from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SavedAlertRow(SQLModel, table=True):
    __tablename__ = "saved_alert"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=128)
    # Which /browse tab the alert watches.
    category: str = Field(max_length=32)
    # Optional comma-separated keywords. A hit matches if any keyword is
    # a case-insensitive substring of the release title. Empty → match
    # everything in the category.
    keywords: str = Field(default="", max_length=512)
    # Optional torrent|usenet protocol restriction; empty means any.
    protocol: str | None = Field(default=None, max_length=16)
    enabled: bool = Field(default=True)
    check_interval_minutes: int = Field(default=30)
    last_check_at: datetime | None = Field(default=None)
    # JSON-encoded list of the titles we last saw so re-checks can diff
    # and fire "new match" only for genuinely new releases.
    last_seen_titles: str = Field(default="[]")
    created_at: datetime = Field(default_factory=_utcnow)
