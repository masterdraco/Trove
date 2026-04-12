"""TMDB (The Movie Database) client.

Uses the v4 bearer token auth which works against all /3/ endpoints.
The user's token is stored in the app_setting table as tmdb.api_token
and is pulled on every request — so rotating it in the Settings UI
takes effect immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from sqlmodel import Session

from trove.db import get_engine
from trove.services import app_settings

log = structlog.get_logger()

TMDB_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"


class TmdbError(Exception):
    """Raised when the TMDB API returns an error or is not configured."""


@dataclass(slots=True)
class TmdbItem:
    tmdb_id: int
    kind: str  # "movie" | "tv"
    title: str
    original_title: str | None
    year: int | None
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None
    rating: float | None
    genres: list[str]
    release_date: str | None
    popularity: float | None

    def poster_url(self, size: str = "w342") -> str | None:
        if not self.poster_path:
            return None
        return f"{IMAGE_BASE}/{size}{self.poster_path}"

    def backdrop_url(self, size: str = "w1280") -> str | None:
        if not self.backdrop_path:
            return None
        return f"{IMAGE_BASE}/{size}{self.backdrop_path}"


def _get_token(session: Session | None = None) -> str:
    close = False
    if session is None:
        session = Session(get_engine())
        close = True
    try:
        token = app_settings.get_override(session, "tmdb.api_token")
    finally:
        if close:
            session.close()
    if not token:
        raise TmdbError("TMDB is not configured. Add an API token in Settings.")
    return str(token)


def is_configured(session: Session | None = None) -> bool:
    try:
        _get_token(session)
        return True
    except TmdbError:
        return False


async def _request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    url = f"{TMDB_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers, params=params or {})
    except httpx.HTTPError as e:
        raise TmdbError(f"tmdb request failed: {e}") from e
    if resp.status_code == 401:
        raise TmdbError("TMDB rejected the API token — check it in Settings.")
    if resp.status_code == 404:
        raise TmdbError(f"TMDB 404 for {path}")
    if resp.status_code >= 400:
        raise TmdbError(f"TMDB HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _parse_year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


def _genre_names(genres_raw: list[dict[str, Any]] | list[int] | None) -> list[str]:
    if not genres_raw:
        return []
    names: list[str] = []
    for g in genres_raw:
        if isinstance(g, dict):
            name = g.get("name")
            if name:
                names.append(str(name))
    return names


def _coerce_movie(data: dict[str, Any]) -> TmdbItem:
    return TmdbItem(
        tmdb_id=int(data.get("id", 0)),
        kind="movie",
        title=str(data.get("title") or data.get("name") or ""),
        original_title=data.get("original_title") or None,
        year=_parse_year(data.get("release_date")),
        overview=data.get("overview") or None,
        poster_path=data.get("poster_path") or None,
        backdrop_path=data.get("backdrop_path") or None,
        rating=float(data["vote_average"]) if data.get("vote_average") is not None else None,
        genres=_genre_names(data.get("genres") or []),
        release_date=data.get("release_date") or None,
        popularity=float(data["popularity"]) if data.get("popularity") is not None else None,
    )


def _coerce_tv(data: dict[str, Any]) -> TmdbItem:
    return TmdbItem(
        tmdb_id=int(data.get("id", 0)),
        kind="tv",
        title=str(data.get("name") or data.get("title") or ""),
        original_title=data.get("original_name") or None,
        year=_parse_year(data.get("first_air_date")),
        overview=data.get("overview") or None,
        poster_path=data.get("poster_path") or None,
        backdrop_path=data.get("backdrop_path") or None,
        rating=float(data["vote_average"]) if data.get("vote_average") is not None else None,
        genres=_genre_names(data.get("genres") or []),
        release_date=data.get("first_air_date") or None,
        popularity=float(data["popularity"]) if data.get("popularity") is not None else None,
    )


def _coerce_result(data: dict[str, Any], hint: str | None = None) -> TmdbItem | None:
    media_type = data.get("media_type") or hint
    if media_type == "movie":
        return _coerce_movie(data)
    if media_type == "tv":
        return _coerce_tv(data)
    if data.get("title") and "release_date" in data:
        return _coerce_movie(data)
    if data.get("name") and "first_air_date" in data:
        return _coerce_tv(data)
    return None


async def _multi_page(
    path: str,
    pages: int,
    coerce: Any,
    params: dict[str, Any] | None = None,
) -> list[TmdbItem]:
    """Fetch up to *pages* pages from a TMDB list endpoint."""
    results: list[TmdbItem] = []
    for page in range(1, pages + 1):
        merged = {**(params or {}), "page": page}
        data = await _request(path, merged)
        for r in data.get("results", []):
            item = coerce(r)
            if item is not None:
                results.append(item)
        if page >= int(data.get("total_pages", 1)):
            break
    return results


async def trending(media: str = "all", window: str = "week", limit: int = 20) -> list[TmdbItem]:
    """media: all | movie | tv. window: day | week."""
    if media not in ("all", "movie", "tv"):
        raise TmdbError("media must be all, movie, or tv")
    if window not in ("day", "week"):
        raise TmdbError("window must be day or week")
    hint = None if media == "all" else media
    pages = max(1, (limit + 19) // 20)
    items = await _multi_page(
        f"/trending/{media}/{window}",
        pages,
        lambda r: _coerce_result(r, hint=hint),
    )
    return items[:limit]


async def popular(media: str = "movie", limit: int = 20) -> list[TmdbItem]:
    if media not in ("movie", "tv"):
        raise TmdbError("popular media must be movie or tv")
    coerce = _coerce_movie if media == "movie" else _coerce_tv
    pages = max(1, (limit + 19) // 20)
    items = await _multi_page(f"/{media}/popular", pages, coerce)
    return items[:limit]


async def upcoming_movies(limit: int = 20) -> list[TmdbItem]:
    from datetime import date as _date

    today = _date.today().isoformat()
    # Fetch extra pages because we'll drop past releases.
    pages = max(2, (limit + 19) // 20 + 1)
    raw = await _multi_page("/movie/upcoming", pages, _coerce_movie)
    items = [i for i in raw if i.release_date and i.release_date >= today]
    return items[:limit]


async def on_the_air_tv(limit: int = 20) -> list[TmdbItem]:
    pages = max(1, (limit + 19) // 20)
    items = await _multi_page("/tv/on_the_air", pages, _coerce_tv)
    return items[:limit]


async def search(query: str, kind: str = "multi") -> list[TmdbItem]:
    if kind not in ("multi", "movie", "tv"):
        raise TmdbError("kind must be multi, movie, or tv")
    path = f"/search/{kind}"
    data = await _request(path, params={"query": query, "include_adult": "false"})
    hint = None if kind == "multi" else kind
    items = [_coerce_result(r, hint=hint) for r in data.get("results", [])]
    return [i for i in items if i is not None]


async def get_movie(tmdb_id: int) -> TmdbItem:
    data = await _request(f"/movie/{tmdb_id}")
    return _coerce_movie(data)


async def get_tv(tmdb_id: int) -> TmdbItem:
    data = await _request(f"/tv/{tmdb_id}")
    return _coerce_tv(data)


async def test_connection() -> dict[str, Any]:
    """Ping /configuration which is a cheap auth check."""
    try:
        data = await _request("/configuration")
    except TmdbError as e:
        return {"ok": False, "message": str(e)}
    return {
        "ok": True,
        "image_base": data.get("images", {}).get("secure_base_url", IMAGE_BASE),
        "change_keys": len(data.get("change_keys") or []),
    }
