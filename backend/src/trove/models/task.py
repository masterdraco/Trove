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
    outcome: str = Field(max_length=32)  # sent | skipped | failed | removed
    reason: str | None = Field(default=None, max_length=512)
    # Which download client ended up accepting the release, so the
    # poller knows where to look up its current state.
    client_id: int | None = Field(default=None, foreign_key="client.id")
    # NZBGet nzb_id / torrent hash / SABnzbd nzo_id / Deluge torrent id.
    # Whatever AddResult.identifier returned at add-time.
    grabbed_identifier: str | None = Field(default=None, max_length=128)
    # Periodic download-state poll writes into these columns.
    download_status: str | None = Field(default=None, max_length=16, index=True)
    download_progress: float | None = Field(default=None)
    download_size_bytes: int | None = Field(default=None)
    download_downloaded_bytes: int | None = Field(default=None)
    download_eta_seconds: int | None = Field(default=None)
    download_error_message: str | None = Field(default=None, max_length=512)
    download_state_at: datetime | None = Field(default=None)
    # Quality upgrade tracking — populated since v0.8.0.
    quality_score: float | None = Field(default=None)
    quality_tier: int | None = Field(default=None)
    upgraded_from_id: int | None = Field(default=None, foreign_key="seen_release.id")
