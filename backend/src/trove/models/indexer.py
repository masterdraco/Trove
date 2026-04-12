from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IndexerRow(SQLModel, table=True):
    __tablename__ = "indexer"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, min_length=1, max_length=64)
    type: str = Field(max_length=32)  # IndexerType value
    protocol: str = Field(max_length=16)  # Protocol value
    base_url: str = Field(max_length=512)
    credentials_cipher: str = Field(max_length=4096)
    definition_yaml: str | None = Field(default=None)
    enabled: bool = Field(default=True)
    priority: int = Field(default=50)
    created_at: datetime = Field(default_factory=_utcnow)
    last_test_at: datetime | None = Field(default=None)
    last_test_ok: bool | None = Field(default=None)
    last_test_message: str | None = Field(default=None, max_length=512)


class IndexerEventRow(SQLModel, table=True):
    """One per search attempt against an indexer.

    Written by run_search immediately after each per-indexer call finishes,
    regardless of whether the call succeeded or errored. Used by the
    /api/indexers/health endpoint to render per-indexer operational stats.
    """

    __tablename__ = "indexer_event"

    id: int | None = Field(default=None, primary_key=True)
    indexer_id: int = Field(index=True, foreign_key="indexer.id")
    at: datetime = Field(default_factory=_utcnow, index=True)
    success: bool = Field(default=False)
    hit_count: int = Field(default=0)
    elapsed_ms: int = Field(default=0)
    query: str | None = Field(default=None, max_length=256)
    error_message: str | None = Field(default=None, max_length=512)
