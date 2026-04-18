from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.models.user import User
from trove.services import plex_library

router = APIRouter()


class PlexTestOut(BaseModel):
    ok: bool
    message: str | None = None
    sections: list[dict[str, str]] = []


class InLibraryOut(BaseModel):
    in_library: bool


@router.post("/plex/test", response_model=PlexTestOut)
async def plex_test(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> PlexTestOut:
    cfg = plex_library.load_config(session)
    if cfg is None:
        return PlexTestOut(ok=False, message="plex.url and plex.token not configured")
    try:
        sections = await plex_library.test_connection(cfg)
    except plex_library.PlexError as e:
        return PlexTestOut(ok=False, message=str(e))
    return PlexTestOut(
        ok=True,
        sections=[{"key": s.key, "title": s.title, "kind": s.kind} for s in sections],
    )


@router.get("/check", response_model=InLibraryOut)
async def library_check(
    tmdb_id: int | None = Query(None),
    title: str | None = Query(None),
    year: int | None = Query(None),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> InLibraryOut:
    found = await plex_library.movie_in_library(session, tmdb_id=tmdb_id, title=title, year=year)
    return InLibraryOut(in_library=found)
