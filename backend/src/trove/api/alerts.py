from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.models.saved_alert import SavedAlertRow
from trove.models.user import User
from trove.services import alert_service

router = APIRouter()


class AlertIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: Category
    keywords: str = Field(default="", max_length=512)
    protocol: Protocol | None = None
    enabled: bool = True
    check_interval_minutes: int = Field(default=30, ge=5, le=1440)


class AlertOut(BaseModel):
    id: int
    name: str
    category: str
    keywords: str
    protocol: str | None
    enabled: bool
    check_interval_minutes: int
    last_check_at: datetime | None
    created_at: datetime


def _to_out(row: SavedAlertRow) -> AlertOut:
    assert row.id is not None
    return AlertOut(
        id=row.id,
        name=row.name,
        category=row.category,
        keywords=row.keywords,
        protocol=row.protocol,
        enabled=row.enabled,
        check_interval_minutes=row.check_interval_minutes,
        last_check_at=row.last_check_at,
        created_at=row.created_at,
    )


@router.get("", response_model=list[AlertOut])
def list_alerts(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[AlertOut]:
    rows = session.exec(
        select(SavedAlertRow).order_by(SavedAlertRow.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: AlertIn,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> AlertOut:
    row = SavedAlertRow(
        name=payload.name,
        category=payload.category.value,
        keywords=payload.keywords,
        protocol=payload.protocol.value if payload.protocol else None,
        enabled=payload.enabled,
        check_interval_minutes=payload.check_interval_minutes,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert(
    alert_id: int,
    payload: AlertIn,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> AlertOut:
    row = session.get(SavedAlertRow, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    row.name = payload.name
    row.category = payload.category.value
    row.keywords = payload.keywords
    row.protocol = payload.protocol.value if payload.protocol else None
    row.enabled = payload.enabled
    row.check_interval_minutes = payload.check_interval_minutes
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(SavedAlertRow, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    session.delete(row)
    session.commit()


@router.post("/{alert_id}/run", response_model=dict)
async def run_alert(
    alert_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> dict[str, int]:
    row = session.get(SavedAlertRow, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert_not_found")
    dispatched = await alert_service.check_alert(session, row)
    return {"new_matches": dispatched}
