from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.ai import agent as ai_agent
from trove.api.deps import current_user, db_session
from trove.models.task import TaskRow
from trove.models.user import User
from trove.models.watchlist import WatchlistItemRow
from trove.services import scheduler

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


def _to_out(row: WatchlistItemRow) -> WatchlistOut:
    assert row.id is not None
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
    )


@router.get("", response_model=list[WatchlistOut])
async def list_items(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[WatchlistOut]:
    rows = session.exec(
        select(WatchlistItemRow).order_by(WatchlistItemRow.added_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(r) for r in rows]


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
            return _to_out(existing)

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
    return _to_out(row)


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
    return _to_out(row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(WatchlistItemRow, item_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    # Also stop any backing download task
    if row.discovery_task_id is not None:
        task = session.get(TaskRow, row.discovery_task_id)
        if task is not None:
            scheduler.unschedule_task(task.id)  # type: ignore[arg-type]
            session.delete(task)
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
        config_yaml = ai_agent._build_series_task_yaml(row.title, row.target_quality, output_names)
        schedule_cron = "0 * * * *"
    else:
        slug_parts = [row.title]
        if row.year:
            slug_parts.append(str(row.year))
        task_name = ai_agent._slugify("-".join(slug_parts))
        config_yaml = ai_agent._build_movie_task_yaml(
            row.title, row.year, row.target_quality, output_names
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
    if row.discovery_task_id is not None:
        task = session.get(TaskRow, row.discovery_task_id)
        if task is not None:
            scheduler.unschedule_task(task.id)  # type: ignore[arg-type]
            session.delete(task)
        row.discovery_task_id = None
    row.discovery_status = "tracking"
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)
