from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.models.user import User
from trove.services import quality_profile

router = APIRouter()


class QualityProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    quality_tiers: dict[str, int] = Field(default_factory=dict)
    source_tiers: dict[str, int] = Field(default_factory=dict)
    codec_bonus: dict[str, int] = Field(default_factory=dict)
    reject_tokens: list[str] = Field(default_factory=list)
    prefer_quality: str | None = None
    min_acceptable_tier: int = 0


class QualityProfilesOut(BaseModel):
    default: str
    profiles: dict[str, Any]


@router.get("", response_model=QualityProfilesOut)
async def list_profiles(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> QualityProfilesOut:
    data = quality_profile.list_profiles(session)
    return QualityProfilesOut(
        default=data.get("default") or quality_profile.DEFAULT_PROFILE_NAME,
        profiles=data.get("profiles") or {},
    )


@router.put("/{name}", response_model=QualityProfilesOut)
async def upsert_profile(
    name: str,
    payload: QualityProfileIn,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> QualityProfilesOut:
    # The URL name is authoritative — override the body so you can't
    # accidentally create "foo" by PUTting "bar".
    profile = payload.model_dump()
    profile["name"] = name
    try:
        quality_profile.upsert_profile(session, profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await list_profiles(session, _user)  # type: ignore[arg-type]


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    name: str,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    try:
        quality_profile.delete_profile(session, name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


class DefaultIn(BaseModel):
    name: str


@router.post("/default", response_model=QualityProfilesOut)
async def set_default(
    payload: DefaultIn,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> QualityProfilesOut:
    try:
        quality_profile.set_default(session, payload.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return await list_profiles(session, _user)  # type: ignore[arg-type]
