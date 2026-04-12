from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from trove.api.deps import current_user
from trove.models.user import User
from trove.services import tmdb

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
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.trending(media=media, window=window, limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return [_to_out(i) for i in items]


@router.get("/popular", response_model=list[DiscoverItem])
async def popular_endpoint(
    media: str = Query("movie", pattern="^(movie|tv)$"),
    limit: int = Query(20, ge=1, le=100),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.popular(media=media, limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return [_to_out(i) for i in items]


@router.get("/upcoming/movies", response_model=list[DiscoverItem])
async def upcoming_movies_endpoint(
    limit: int = Query(20, ge=1, le=100),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.upcoming_movies(limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return [_to_out(i) for i in items]


@router.get("/on-air/tv", response_model=list[DiscoverItem])
async def on_air_tv_endpoint(
    limit: int = Query(20, ge=1, le=100),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.on_the_air_tv(limit=limit)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return [_to_out(i) for i in items]


@router.get("/search", response_model=list[DiscoverItem])
async def search_endpoint(
    q: str = Query(min_length=1),
    kind: str = Query("multi", pattern="^(multi|movie|tv)$"),
    _user: User = Depends(current_user),
) -> list[DiscoverItem]:
    try:
        items = await tmdb.search(query=q, kind=kind)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return [_to_out(i) for i in items]


@router.get("/movie/{tmdb_id}", response_model=DiscoverItem)
async def movie_detail(
    tmdb_id: int,
    _user: User = Depends(current_user),
) -> DiscoverItem:
    try:
        item = await tmdb.get_movie(tmdb_id)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return _to_out(item)


@router.get("/tv/{tmdb_id}", response_model=DiscoverItem)
async def tv_detail(
    tmdb_id: int,
    _user: User = Depends(current_user),
) -> DiscoverItem:
    try:
        item = await tmdb.get_tv(tmdb_id)
    except tmdb.TmdbError as e:
        raise _wrap(e) from e
    return _to_out(item)


@router.post("/test")
async def test_endpoint(_user: User = Depends(current_user)) -> dict[str, object]:
    return await tmdb.test_connection()
