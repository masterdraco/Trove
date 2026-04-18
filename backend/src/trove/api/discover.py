from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.models.user import User
from trove.services import plex_library, tmdb

router = APIRouter()

POSTER_SIZE = "w342"
BACKDROP_SIZE = "w1280"


class DiscoverItem(BaseModel):
    tmdb_id: int
    kind: str
    title: str
    original_title: str | None
    year: int | None
    overview: str | None
    poster_url: str | None
    backdrop_url: str | None
    rating: float | None
    genres: list[str] = Field(default_factory=list)
    release_date: str | None
    popularity: float | None
    # True when Plex is configured AND the library contains this title.
    # Cached per-title in plex_library so repeat visits are cheap.
    in_library: bool = False


class ConfigStatus(BaseModel):
    configured: bool


def _to_out(item: tmdb.TmdbItem) -> DiscoverItem:
    return DiscoverItem(
        tmdb_id=item.tmdb_id,
        kind=item.kind,
        title=item.title,
        original_title=item.original_title,
        year=item.year,
        overview=item.overview,
        poster_url=item.poster_url(POSTER_SIZE),
        backdrop_url=item.backdrop_url(BACKDROP_SIZE),
        rating=item.rating,
        genres=item.genres,
        release_date=item.release_date,
        popularity=item.popularity,
    )


async def _annotate_library(session: Session, items: list[DiscoverItem]) -> None:
    """Set ``in_library`` on each item by looking up Plex in parallel.
    No-op when Plex isn't configured (every lookup short-circuits)."""
    if not items:
        return
    results = await asyncio.gather(
        *(
            plex_library.title_in_library(
                session,
                kind=item.kind if item.kind in ("movie", "tv") else "movie",
                tmdb_id=item.tmdb_id,
                title=item.title,
                year=item.year,
            )
            for item in items
        ),
        return_exceptions=True,
    )
    for item, found in zip(items, results, strict=True):
        if isinstance(found, Exception):
            continue
        item.in_library = bool(found)


def _wrap(err: Exception) -> HTTPException:
    msg = str(err)
    if "not configured" in msg:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tmdb_not_configured",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"tmdb: {msg}",
    )


@router.get("/status", response_model=ConfigStatus)
async def status_endpoint(_user: User = Depends(current_user)) -> ConfigStatus:
    return ConfigStatus(configured=tmdb.is_configured())


@router.get("/trending", response_model=list[DiscoverItem])
async def trending_endpoint(
    media: str = Query("all", pattern="^(all|movie|tv)$"),
    window: str = Query("week", pattern="^(day|week)$"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.trending(media=media, window=window, limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    outs = [_to_out(i) for i in items]
    await _annotate_library(session, outs)
    return outs


@router.get("/popular", response_model=list[DiscoverItem])
async def popular_endpoint(
    media: str = Query("movie", pattern="^(movie|tv)$"),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.popular(media=media, limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    outs = [_to_out(i) for i in items]
    await _annotate_library(session, outs)
    return outs


@router.get("/upcoming/movies", response_model=list[DiscoverItem])
async def upcoming_movies_endpoint(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.upcoming_movies(limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    outs = [_to_out(i) for i in items]
    await _annotate_library(session, outs)
    return outs


@router.get("/on-air/tv", response_model=list[DiscoverItem])
async def on_air_tv_endpoint(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.on_the_air_tv(limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    outs = [_to_out(i) for i in items]
    await _annotate_library(session, outs)
    return outs


@router.get("/search", response_model=list[DiscoverItem])
async def search_endpoint(
    q: str = Query(min_length=1),
    kind: str = Query("multi", pattern="^(multi|movie|tv)$"),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.search(query=q, kind=kind)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    outs = [_to_out(i) for i in items]
    await _annotate_library(session, outs)
    return outs


@router.get("/movie/{tmdb_id}", response_model=DiscoverItem)
async def movie_detail(
    tmdb_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> DiscoverItem:
    try:
        item = await tmdb.get_movie(tmdb_id)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    out = _to_out(item)
    await _annotate_library(session, [out])
    return out


@router.get("/tv/{tmdb_id}", response_model=DiscoverItem)
async def tv_detail(
    tmdb_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> DiscoverItem:
    try:
        item = await tmdb.get_tv(tmdb_id)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    out = _to_out(item)
    await _annotate_library(session, [out])
    return out


@router.post("/test")
async def test_endpoint(_user: User = Depends(current_user)) -> dict[str, object]:
    return await tmdb.test_connection()
