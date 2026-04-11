from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.user import User
from trove.models.watchlist import WatchlistItemRow

router = APIRouter()


class WatchlistCreate(BaseModel):
    kind: str = Field(pattern="^(series|movie)$")
    title: str = Field(min_length=1, max_length=256)
    year: int | None = None
    target_quality: str | None = None
    notes: str | None = None


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
    row = WatchlistItemRow(
        kind=payload.kind,
        title=payload.title,
        year=payload.year,
        target_quality=payload.target_quality,
        notes=payload.notes,
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
    session.delete(row)
    session.commit()
