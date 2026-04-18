from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ExternalCacheRow(SQLModel, table=True):
    __tablename__ = "external_cache"

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(index=True, max_length=64)
    key_hash: str = Field(index=True, max_length=64)
    payload: str = Field()  # JSON-encoded response
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = Field(default=None, index=True)
