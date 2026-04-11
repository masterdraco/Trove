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
