from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskRow(SQLModel, table=True):
    __tablename__ = "task"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, min_length=1, max_length=128)
    enabled: bool = Field(default=True)
    schedule_cron: str | None = Field(default=None, max_length=128)
    config_yaml: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    last_run_at: datetime | None = Field(default=None)
    last_run_status: str | None = Field(default=None, max_length=32)
    last_run_accepted: int | None = Field(default=None)
    last_run_considered: int | None = Field(default=None)


class TaskRunRow(SQLModel, table=True):
    __tablename__ = "task_run"

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = Field(default=None)
    status: str = Field(max_length=32)
    considered: int = Field(default=0)
    accepted: int = Field(default=0)
    log: str = Field(default="")
    dry_run: bool = Field(default=False)


class SeenReleaseRow(SQLModel, table=True):
    __tablename__ = "seen_release"

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(index=True, foreign_key="task.id")
    key: str = Field(index=True, max_length=256)
    title: str = Field(max_length=512)
    seen_at: datetime = Field(default_factory=_utcnow)
    outcome: str = Field(max_length=32)  # sent | skipped | failed
    reason: str | None = Field(default=None, max_length=512)
