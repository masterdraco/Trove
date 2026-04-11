from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AiCacheRow(SQLModel, table=True):
    __tablename__ = "ai_cache"

    id: int | None = Field(default=None, primary_key=True)
    prompt_hash: str = Field(index=True, unique=True, max_length=64)
    model: str = Field(max_length=128)
    response: str = Field()
    created_at: datetime = Field(default_factory=_utcnow)
    ttl_seconds: int = Field(default=0)
