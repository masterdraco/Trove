from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.client import Client
from trove.models.task import SeenReleaseRow, TaskRow
from trove.models.user import User

router = APIRouter()


class DownloadOut(BaseModel):
    id: int
    task_id: int
    task_name: str
    title: str
    outcome: str
    seen_at: datetime
    client_id: int | None
    client_name: str | None
    download_status: str | None
    download_progress: float | None
    download_size_bytes: int | None
    download_downloaded_bytes: int | None
    download_eta_seconds: int | None
    download_error_message: str | None
    download_state_at: datetime | None
    quality_score: float | None
    quality_tier: int | None


@router.get("", response_model=list[DownloadOut])
async def list_downloads(
    status: str | None = Query(None, description="Filter by download_status"),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DownloadOut]:
    """Return all grabbed releases with download state info.

    By default returns the most recent 50 across all tasks. Pass
    ``?status=downloading`` to filter to active downloads only.
    """
    stmt = (
        select(SeenReleaseRow, TaskRow, Client)
        .join(TaskRow, SeenReleaseRow.task_id == TaskRow.id)
        .outerjoin(Client, SeenReleaseRow.client_id == Client.id)
        .where(SeenReleaseRow.outcome.in_(["sent", "upgraded"]))  # type: ignore[attr-defined]
        .where(SeenReleaseRow.grabbed_identifier.is_not(None))  # type: ignore[attr-defined]
        .order_by(SeenReleaseRow.seen_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    if status:
        stmt = stmt.where(SeenReleaseRow.download_status == status)

    rows = session.exec(stmt).all()
    return [
        DownloadOut(
            id=sr.id or 0,
            task_id=sr.task_id,
            task_name=task.name,
            title=sr.title,
            outcome=sr.outcome,
            seen_at=sr.seen_at,
            client_id=sr.client_id,
            client_name=client.name if client else None,
            download_status=sr.download_status,
            download_progress=sr.download_progress,
            download_size_bytes=sr.download_size_bytes,
            download_downloaded_bytes=sr.download_downloaded_bytes,
            download_eta_seconds=sr.download_eta_seconds,
            download_error_message=sr.download_error_message,
            download_state_at=sr.download_state_at,
            quality_score=sr.quality_score,
            quality_tier=sr.quality_tier,
        )
        for sr, task, client in rows
    ]
