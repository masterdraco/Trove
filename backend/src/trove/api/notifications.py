from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.notification import NotificationProviderRow
from trove.models.user import User
from trove.services import notification_service
from trove.services.notification_service import EVENT_KINDS, PROVIDER_TYPES

router = APIRouter()


class NotificationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True


class NotificationUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    events: list[str] | None = None
    enabled: bool | None = None


class NotificationOut(BaseModel):
    id: int
    name: str
    type: str
    events: list[str]
    enabled: bool
    created_at: datetime
    last_sent_at: datetime | None
    last_sent_ok: bool | None
    last_sent_message: str | None


class NotificationMeta(BaseModel):
    event_kinds: list[str]
    provider_types: list[str]


def _validate_type(t: str) -> None:
    if t not in PROVIDER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown provider type: {t}",
        )


def _validate_events(events: list[str]) -> None:
    bad = [e for e in events if e not in EVENT_KINDS]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown event kinds: {bad}",
        )


def _to_out(row: NotificationProviderRow) -> NotificationOut:
    assert row.id is not None
    try:
        events = json.loads(row.events or "[]")
    except Exception:
        events = []
    return NotificationOut(
        id=row.id,
        name=row.name,
        type=row.type,
        events=events,
        enabled=row.enabled,
        created_at=row.created_at,
        last_sent_at=row.last_sent_at,
        last_sent_ok=row.last_sent_ok,
        last_sent_message=row.last_sent_message,
    )


@router.get("/meta", response_model=NotificationMeta)
async def get_meta(_user: User = Depends(current_user)) -> NotificationMeta:
    return NotificationMeta(
        event_kinds=list(EVENT_KINDS),
        provider_types=list(PROVIDER_TYPES),
    )


@router.get("", response_model=list[NotificationOut])
async def list_providers(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[NotificationOut]:
    rows = session.exec(
        select(NotificationProviderRow).order_by(NotificationProviderRow.created_at)
    ).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: NotificationCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> NotificationOut:
    _validate_type(payload.type)
    _validate_events(payload.events)
    row = NotificationProviderRow(
        name=payload.name,
        type=payload.type,
        config_cipher=notification_service.encrypt_config(payload.config),
        events=json.dumps(payload.events),
        enabled=payload.enabled,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.patch("/{provider_id}", response_model=NotificationOut)
async def update_provider(
    provider_id: int,
    payload: NotificationUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> NotificationOut:
    row = session.get(NotificationProviderRow, provider_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if payload.name is not None:
        row.name = payload.name
    if payload.config is not None:
        row.config_cipher = notification_service.encrypt_config(payload.config)
    if payload.events is not None:
        _validate_events(payload.events)
        row.events = json.dumps(payload.events)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(NotificationProviderRow, provider_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    session.delete(row)
    session.commit()


class TestResult(BaseModel):
    ok: bool
    message: str | None


@router.post("/{provider_id}/test", response_model=TestResult)
async def test_provider(
    provider_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> TestResult:
    row = session.get(NotificationProviderRow, provider_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    event = notification_service.Event(
        kind="task.grabbed",
        title="Trove test notification",
        description=(
            f"If you can read this, **{row.name}** is wired up correctly. "
            "Delete it from the task.grabbed event subscription if you "
            "don't want real grabs delivered here."
        ),
        fields={"Provider": row.name, "Type": row.type},
    )
    # Bypass the subscription filter for tests — always deliver.
    try:
        await notification_service._deliver(row, event)  # type: ignore[attr-defined]
    except Exception as e:
        return TestResult(ok=False, message=str(e)[:480])
    return TestResult(ok=True, message="delivered")
