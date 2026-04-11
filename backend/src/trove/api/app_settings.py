from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.models.user import User
from trove.services import app_settings

router = APIRouter()


class SettingOut(BaseModel):
    key: str
    type: str
    label: str
    description: str
    group: str
    default: Any
    value: Any
    min_value: int | None
    max_value: int | None


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


@router.get("", response_model=list[SettingOut])
async def list_settings(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[SettingOut]:
    rows = app_settings.list_all(session)
    return [SettingOut(**row) for row in rows]


@router.patch("", response_model=list[SettingOut])
async def update_settings(
    payload: SettingsUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[SettingOut]:
    errors: dict[str, str] = {}
    for key, value in payload.values.items():
        try:
            app_settings.set_value(session, key, value)
        except KeyError:
            errors[key] = "unknown setting"
        except ValueError as e:
            errors[key] = str(e)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors},
        )
    rows = app_settings.list_all(session)
    return [SettingOut(**row) for row in rows]
