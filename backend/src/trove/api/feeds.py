from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.feed import FeedRow, RssItemRow
from trove.models.user import User
from trove.services import app_settings, feed_poller, scheduler
from trove.utils.crypto import encrypt_json

router = APIRouter()


class FeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=1024)
    credentials: dict[str, Any] | None = None
    enabled: bool = True
    poll_interval_seconds: int | None = Field(default=None, ge=60)
    retention_days: int | None = Field(default=None, ge=1)
    category_hint: str | None = None
    protocol_hint: str = Field(default="torrent", pattern="^(torrent|usenet)$")


class FeedUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    credentials: dict[str, Any] | None = None
    enabled: bool | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=60)
    retention_days: int | None = Field(default=None, ge=1)
    category_hint: str | None = None
    protocol_hint: str | None = Field(default=None, pattern="^(torrent|usenet)$")


class FeedOut(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    poll_interval_seconds: int
    retention_days: int
    category_hint: str | None
    protocol_hint: str
    last_polled_at: datetime | None
    last_poll_status: str | None
    last_poll_message: str | None
    total_items: int
    last_new_items: int


class FeedPreviewRequest(BaseModel):
    url: str
    credentials: dict[str, Any] | None = None


class FeedPreviewItem(BaseModel):
    title: str
    download_url: str
    size: int | None
    seeders: int | None
    leechers: int | None
    infohash: str | None
    category: str | None
    published_at: str | None


class FeedPollResult(BaseModel):
    ok: bool
    new_items: int
    total: int | None = None
    error: str | None = None


class RssItemOut(BaseModel):
    id: int
    feed_id: int
    title: str
    download_url: str
    size: int | None
    seeders: int | None
    leechers: int | None
    category: str | None
    published_at: datetime | None
    fetched_at: datetime


def _to_out(row: FeedRow) -> FeedOut:
    assert row.id is not None
    return FeedOut(
        id=row.id,
        name=row.name,
        url=row.url,
        enabled=row.enabled,
        poll_interval_seconds=row.poll_interval_seconds,
        retention_days=row.retention_days,
        category_hint=row.category_hint,
        protocol_hint=row.protocol_hint,
        last_polled_at=row.last_polled_at,
        last_poll_status=row.last_poll_status,
        last_poll_message=row.last_poll_message,
        total_items=row.total_items,
        last_new_items=row.last_new_items,
    )


@router.get("", response_model=list[FeedOut])
async def list_feeds(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[FeedOut]:
    rows = session.exec(select(FeedRow).order_by(FeedRow.name)).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=FeedOut, status_code=status.HTTP_201_CREATED)
async def create_feed(
    payload: FeedCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> FeedOut:
    existing = session.exec(select(FeedRow).where(FeedRow.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")

    poll_interval = payload.poll_interval_seconds
    if poll_interval is None:
        poll_interval = app_settings.get_int(session, "rss.default_poll_interval_seconds")
    retention_days = payload.retention_days
    if retention_days is None:
        retention_days = app_settings.get_int(session, "rss.default_retention_days")

    row = FeedRow(
        name=payload.name,
        url=payload.url,
        credentials_cipher=encrypt_json(payload.credentials) if payload.credentials else None,
        enabled=payload.enabled,
        poll_interval_seconds=poll_interval,
        retention_days=retention_days,
        category_hint=payload.category_hint,
        protocol_hint=payload.protocol_hint,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    scheduler.schedule_feed(row)
    return _to_out(row)


@router.patch("/{feed_id}", response_model=FeedOut)
async def update_feed(
    feed_id: int,
    payload: FeedUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> FeedOut:
    row = session.get(FeedRow, feed_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if payload.name is not None and payload.name != row.name:
        clash = session.exec(select(FeedRow).where(FeedRow.name == payload.name)).first()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")
        row.name = payload.name
    if payload.url is not None:
        row.url = payload.url
    if payload.credentials is not None:
        row.credentials_cipher = encrypt_json(payload.credentials) if payload.credentials else None
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.poll_interval_seconds is not None:
        row.poll_interval_seconds = payload.poll_interval_seconds
    if payload.retention_days is not None:
        row.retention_days = payload.retention_days
    if payload.category_hint is not None:
        row.category_hint = payload.category_hint or None
    if payload.protocol_hint is not None:
        row.protocol_hint = payload.protocol_hint
    session.add(row)
    session.commit()
    session.refresh(row)
    scheduler.schedule_feed(row)
    return _to_out(row)


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(
    feed_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(FeedRow, feed_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    # Cascade-delete items belonging to this feed first (SQLite lacks ON DELETE CASCADE here)
    items = session.exec(select(RssItemRow).where(RssItemRow.feed_id == feed_id)).all()
    for item in items:
        session.delete(item)
    scheduler.unschedule_feed(feed_id)
    session.delete(row)
    session.commit()


@router.post("/preview", response_model=list[FeedPreviewItem])
async def preview_feed(
    payload: FeedPreviewRequest,
    _user: User = Depends(current_user),
) -> list[FeedPreviewItem]:
    try:
        items = await feed_poller.preview_feed(payload.url, payload.credentials)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"preview failed: {e}",
        ) from e
    return [FeedPreviewItem(**it) for it in items]


@router.post("/{feed_id}/poll", response_model=FeedPollResult)
async def poll_now(
    feed_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> FeedPollResult:
    row = session.get(FeedRow, feed_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    result = await feed_poller.poll_feed(session, row)
    return FeedPollResult(**result)


@router.get("/{feed_id}/items", response_model=list[RssItemOut])
async def list_items(
    feed_id: int,
    q: str | None = None,
    limit: int = 100,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[RssItemOut]:
    stmt = select(RssItemRow).where(RssItemRow.feed_id == feed_id)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(RssItemRow.normalized_title.like(pattern))  # type: ignore[attr-defined]
    stmt = stmt.order_by(RssItemRow.fetched_at.desc()).limit(limit)  # type: ignore[attr-defined]
    rows = session.exec(stmt).all()
    return [
        RssItemOut(
            id=r.id or 0,
            feed_id=r.feed_id,
            title=r.title,
            download_url=r.download_url,
            size=r.size,
            seeders=r.seeders,
            leechers=r.leechers,
            category=r.category,
            published_at=r.published_at,
            fetched_at=r.fetched_at,
        )
        for r in rows
    ]
