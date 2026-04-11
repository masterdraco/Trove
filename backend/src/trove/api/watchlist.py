from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.ai import agent as ai_agent
from trove.api.deps import current_user, db_session
from trove.clients.base import (
    AddOptions,
    ClientError,
    ClientType,
    Protocol,
    Release,
    TorrentClient,
    UsenetClient,
)
from trove.indexers.base import Category
from trove.models.client import Client
from trove.models.task import SeenReleaseRow, TaskRow, TaskRunRow
from trove.models.user import User
from trove.models.watchlist import WatchlistItemRow
from trove.services import client_registry, scheduler, search_service
from trove.services.task_engine import score_hit

router = APIRouter()

POSTER_BASE = "https://image.tmdb.org/t/p/w342"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"


class WatchlistCreate(BaseModel):
    kind: str = Field(pattern="^(series|movie)$")
    title: str = Field(min_length=1, max_length=256)
    year: int | None = None
    target_quality: str | None = None
    notes: str | None = None
    # Optional TMDB metadata — set when adding from /discover
    tmdb_id: int | None = None
    tmdb_type: str | None = Field(default=None, pattern="^(movie|tv)$")
    poster_path: str | None = None
    backdrop_path: str | None = None
    overview: str | None = None
    release_date: str | None = None
    rating: float | None = None


class WatchlistUpdate(BaseModel):
    title: str | None = None
    year: int | None = None
    target_quality: str | None = None
    status: str | None = None
    notes: str | None = None


class WatchlistOut(BaseModel):
    id: int
    kind: str
    title: str
    year: int | None
    target_quality: str | None
    status: str
    notes: str | None
    added_at: datetime
    # TMDB metadata
    tmdb_id: int | None
    tmdb_type: str | None
    poster_url: str | None
    backdrop_url: str | None
    overview: str | None
    release_date: str | None
    rating: float | None
    # Auto-download state
    discovery_status: str
    discovery_task_id: int | None
    # Download progress (computed from seen_release)
    download_count: int = 0
    last_download_title: str | None = None
    last_download_at: datetime | None = None


class PromoteResponse(BaseModel):
    ok: bool
    watchlist_id: int
    task_id: int | None
    message: str


def _poster_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{POSTER_BASE}{path}"


def _backdrop_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{BACKDROP_BASE}{path}"


def _detach_backing_task(session: Session, item: WatchlistItemRow) -> None:
    """Unschedule + delete the backing task for a watchlist item, but only
    if no *other* watchlist item references the same task. Cascades the
    task's children (task_run, seen_release) since FK enforcement is on.
    Always clears the item's discovery_task_id.
    """
    task_id = item.discovery_task_id
    item.discovery_task_id = None
    if task_id is None:
        return
    other_users = session.exec(
        select(WatchlistItemRow)
        .where(WatchlistItemRow.discovery_task_id == task_id)
        .where(WatchlistItemRow.id != item.id)
    ).first()
    if other_users is not None:
        # Another watchlist item still relies on this task — leave it.
        return
    task = session.get(TaskRow, task_id)
    if task is None:
        return
    scheduler.unschedule_task(task_id)
    for child in session.exec(
        select(SeenReleaseRow).where(SeenReleaseRow.task_id == task_id)
    ).all():
        session.delete(child)
    for child in session.exec(select(TaskRunRow).where(TaskRunRow.task_id == task_id)).all():
        session.delete(child)
    session.delete(task)


def _download_stats(
    session: Session, task_id: int | None
) -> tuple[int, str | None, datetime | None]:
    """Return (count, last_title, last_time) for sent releases on a task."""
    if task_id is None:
        return 0, None, None
    rows = session.exec(
        select(SeenReleaseRow)
        .where(SeenReleaseRow.task_id == task_id)
        .where(SeenReleaseRow.outcome == "sent")
        .order_by(SeenReleaseRow.seen_at.desc())  # type: ignore[attr-defined]
    ).all()
    if not rows:
        return 0, None, None
    return len(rows), rows[0].title, rows[0].seen_at


def _to_out(row: WatchlistItemRow, session: Session) -> WatchlistOut:
    assert row.id is not None
    count, last_title, last_at = _download_stats(session, row.discovery_task_id)

    # Movies flip to the terminal 'downloaded' state on first successful grab.
    # Series keep the 'promoted' state so new episodes keep landing.
    if row.kind == "movie" and count > 0 and row.discovery_status != "downloaded":
        row.discovery_status = "downloaded"
        session.add(row)
        session.commit()

    return WatchlistOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        year=row.year,
        target_quality=row.target_quality,
        status=row.status,
        notes=row.notes,
        added_at=row.added_at,
        tmdb_id=row.tmdb_id,
        tmdb_type=row.tmdb_type,
        poster_url=_poster_url(row.poster_path),
        backdrop_url=_backdrop_url(row.backdrop_path),
        overview=row.overview,
        release_date=row.release_date,
        rating=row.rating,
        discovery_status=row.discovery_status,
        discovery_task_id=row.discovery_task_id,
        download_count=count,
        last_download_title=last_title,
        last_download_at=last_at,
    )


@router.get("", response_model=list[WatchlistOut])
async def list_items(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[WatchlistOut]:
    rows = session.exec(
        select(WatchlistItemRow).order_by(WatchlistItemRow.added_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(r, session) for r in rows]


@router.post("", response_model=WatchlistOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: WatchlistCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> WatchlistOut:
    # Prevent duplicates when adding from /discover — one TMDB id per user
    if payload.tmdb_id is not None:
        existing = session.exec(
            select(WatchlistItemRow).where(WatchlistItemRow.tmdb_id == payload.tmdb_id)
        ).first()
        if existing is not None:
            return _to_out(existing, session)

    row = WatchlistItemRow(
        kind=payload.kind,
        title=payload.title,
        year=payload.year,
        target_quality=payload.target_quality,
        notes=payload.notes,
        tmdb_id=payload.tmdb_id,
        tmdb_type=payload.tmdb_type,
        poster_path=payload.poster_path,
        backdrop_path=payload.backdrop_path,
        overview=payload.overview,
        release_date=payload.release_date,
        rating=payload.rating,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row, session)


@router.patch("/{item_id}", response_model=WatchlistOut)
async def update_item(
    item_id: int,
    payload: WatchlistUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> WatchlistOut:
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if payload.title is not None:
        row.title = payload.title
    if payload.year is not None:
        row.year = payload.year
    if payload.target_quality is not None:
        row.target_quality = payload.target_quality or None
    if payload.status is not None:
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes or None
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row, session)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    _detach_backing_task(session, row)
    session.delete(row)
    session.commit()


@router.post("/{item_id}/promote", response_model=PromoteResponse)
async def promote_item(
    item_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> PromoteResponse:
    """Create a backing download task for a watchlist item, identical to
    what the AI agent would produce from "add <title> to my downloads".
    """
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    if row.discovery_task_id is not None:
        # Already has a backing task
        return PromoteResponse(
            ok=True,
            watchlist_id=row.id or 0,
            task_id=row.discovery_task_id,
            message="Already promoted",
        )

    # Reuse the AI agent's task builders for consistency
    clients = ai_agent._pick_default_clients(session)
    if not clients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no_clients_configured",
        )
    output_names = [c.name for c in clients]

    if row.kind == "series":
        task_name = ai_agent._slugify(row.title)
        config_yaml = ai_agent._build_series_task_yaml(
            row.title,
            row.target_quality,
            output_names,
            tmdb_id=row.tmdb_id,
        )
        schedule_cron = "0 * * * *"
    else:
        slug_parts = [row.title]
        if row.year:
            slug_parts.append(str(row.year))
        task_name = ai_agent._slugify("-".join(slug_parts))
        config_yaml = ai_agent._build_movie_task_yaml(
            row.title,
            row.year,
            row.target_quality,
            output_names,
            tmdb_id=row.tmdb_id,
        )
        schedule_cron = "0 */2 * * *"

    # Dedup: if a task with that name already exists, reuse it
    existing_task = session.exec(select(TaskRow).where(TaskRow.name == task_name)).first()
    if existing_task is not None:
        task = existing_task
        task.config_yaml = config_yaml
        task.schedule_cron = schedule_cron
        task.enabled = True
    else:
        task = TaskRow(
            name=task_name,
            enabled=True,
            schedule_cron=schedule_cron,
            config_yaml=config_yaml,
        )
        session.add(task)
    session.commit()
    session.refresh(task)

    row.discovery_task_id = task.id
    row.discovery_status = "promoted"
    session.add(row)
    session.commit()

    scheduler.schedule_task(task)
    if task.id is not None:
        scheduler.schedule_run_now(task.id)

    return PromoteResponse(
        ok=True,
        watchlist_id=row.id or 0,
        task_id=task.id,
        message=f"Created task '{task_name}' — running now",
    )


class CandidateOut(BaseModel):
    title: str
    protocol: str
    size: int | None
    seeders: int | None
    source: str
    category: str | None
    download_url: str
    infohash: str | None
    published_at: str | None
    score: float


class GrabRequest(BaseModel):
    title: str
    protocol: str = Field(pattern="^(torrent|usenet)$")
    download_url: str
    size: int | None = None
    infohash: str | None = None


class GrabResponse(BaseModel):
    ok: bool
    client: str | None
    message: str


@router.get("/{item_id}/candidates", response_model=list[CandidateOut])
async def list_candidates(
    item_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[CandidateOut]:
    """Run a one-off search for this watchlist item and return the top
    ranked candidates so the user can pick a specific release."""
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    query = row.title
    if row.kind == "movie" and row.year:
        query = f"{row.title} {row.year}"
    categories = [Category.MOVIES] if row.kind == "movie" else [Category.TV]

    response = await search_service.run_search(session, query, categories=categories, limit=60)
    hits = sorted(
        response.hits,
        key=lambda h: score_hit(h, prefer_quality=row.target_quality),
        reverse=True,
    )[:30]
    return [
        CandidateOut(
            title=h.title,
            protocol=h.protocol.value,
            size=h.size,
            seeders=h.seeders,
            source=h.source,
            category=h.category,
            download_url=h.download_url or "",
            infohash=h.infohash,
            published_at=h.published_at,
            score=round(score_hit(h, prefer_quality=row.target_quality), 1),
        )
        for h in hits
        if h.download_url
    ]


@router.post("/{item_id}/grab", response_model=GrabResponse)
async def grab_release(
    item_id: int,
    payload: GrabRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> GrabResponse:
    """Send a specific release to the first matching-protocol client.

    Used by the watchlist picker so the user can hand-pick a version.
    Records a SeenReleaseRow against the backing task (if any) so the
    same release doesn't get re-grabbed by the scheduled run.
    """
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    try:
        protocol = Protocol(payload.protocol)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_protocol"
        ) from e

    clients = session.exec(select(Client).where(Client.enabled)).all()  # type: ignore[arg-type]
    target: Client | None = None
    for c in clients:
        if ClientType(c.type).protocol is protocol:
            target = c
            break
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"no_{payload.protocol}_client_configured",
        )

    try:
        driver = client_registry.build_driver(target)
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    release = Release(
        title=payload.title,
        protocol=protocol,
        download_url=payload.download_url,
        size=payload.size,
        infohash=payload.infohash,
    )
    options = AddOptions(
        category=target.default_category,
        save_path=target.default_save_path,
    )
    try:
        if protocol is Protocol.TORRENT:
            assert isinstance(driver, TorrentClient)
            result = await driver.add_torrent(release, options)
        else:
            assert isinstance(driver, UsenetClient)
            result = await driver.add_nzb(release, options)
    except ClientError as e:
        await driver.close()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await driver.close()

    if not result.ok:
        return GrabResponse(
            ok=False,
            client=target.name,
            message=result.message or "client rejected the release",
        )

    # Record as sent on the backing task (if one exists) so the scheduler
    # doesn't re-grab this episode/movie on its next run.
    if row.discovery_task_id is not None:
        from trove.services.task_engine import _seen_key  # local import to avoid cycles

        fake_hit = search_service.SearchHit(
            title=payload.title,
            protocol=protocol,
            size=payload.size,
            seeders=None,
            leechers=None,
            download_url=payload.download_url,
            infohash=payload.infohash,
            category=None,
            source="watchlist-pick",
            score=0.0,
            published_at=None,
        )
        seen = SeenReleaseRow(
            task_id=row.discovery_task_id,
            key=_seen_key(fake_hit),
            title=payload.title,
            outcome="sent",
            reason=f"manual pick via watchlist → {target.name}",
        )
        session.add(seen)
        session.commit()

    # Movies flip to 'downloaded' immediately after a successful grab
    if row.kind == "movie":
        row.discovery_status = "downloaded"
        session.add(row)
        session.commit()

    return GrabResponse(ok=True, client=target.name, message=result.message or "sent")


@router.post("/{item_id}/unpromote", response_model=WatchlistOut)
async def unpromote_item(
    item_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> WatchlistOut:
    """Stop and delete the backing download task for a watchlist item
    without removing the item itself."""
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    _detach_backing_task(session, row)
    row.discovery_status = "tracking"
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row, session)
