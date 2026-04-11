from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Client(SQLModel, table=True):
    __tablename__ = "client"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=32)  # ClientType value
    url: str = Field(min_length=1, max_length=512)
    credentials_cipher: str = Field(min_length=1, max_length=4096)
    default_category: str | None = Field(default=None, max_length=128)
    default_save_path: str | None = Field(default=None, max_length=512)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)
    last_test_at: datetime | None = Field(default=None)
    last_test_ok: bool | None = Field(default=None)
    last_test_message: str | None = Field(default=None, max_length=512)
