from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AppSettingRow(SQLModel, table=True):
    __tablename__ = "app_setting"

    key: str = Field(primary_key=True, max_length=128)
    value: str = Field(max_length=4096)
    updated_at: datetime = Field(default_factory=_utcnow)
