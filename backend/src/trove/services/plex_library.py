"""Minimal Plex Media Server library scanner.

Exposes two operations used by the watchlist to avoid re-downloading
titles the user already owns:

  ``test_connection``   sanity-check URL + token; lists library sections.
  ``has_movie_by_tmdb`` returns True if the Plex library contains a movie
                       whose GUIDs include tmdb://<id>. Falls back to a
                       title+year search if the TMDB-agent GUID isn't
                       present.

We deliberately don't touch TV shows here — matching series by season
coverage is much fuzzier and would warrant its own dedicated path.

All network errors are caught and converted to :class:`PlexError` so
callers can surface a clean message. Responses are cached for 5
minutes via external_cache to keep the watchlist list endpoint snappy.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx
import structlog
from sqlmodel import Session

from trove.services import app_settings, external_cache

log = structlog.get_logger()

_CACHE_NS = "plex.library"
_CACHE_TTL = 300  # 5 min — enough to batch a watchlist-list call


class PlexError(Exception):
    """Raised when Plex returns an error or isn't reachable."""


@dataclass(slots=True)
class PlexConfig:
    url: str
    token: str


@dataclass(slots=True)
class PlexSection:
    key: str  # e.g. "1"
    title: str
    kind: str  # "movie" | "show" | "artist" | ...


def load_config(session: Session) -> PlexConfig | None:
    url = str(app_settings.get(session, "plex.url") or "").strip().rstrip("/")
    token = str(app_settings.get(session, "plex.token") or "").strip()
    if not url or not token:
        return None
    return PlexConfig(url=url, token=token)


async def _request_xml(cfg: PlexConfig, path: str, params: dict | None = None) -> ET.Element:
    url = f"{cfg.url}{path}"
    merged = {"X-Plex-Token": cfg.token, **(params or {})}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=merged, headers={"Accept": "application/xml"})
    except httpx.HTTPError as e:
        raise PlexError(f"request failed: {e}") from e
    if resp.status_code == 401:
        raise PlexError("invalid X-Plex-Token")
    if resp.status_code >= 400:
        raise PlexError(f"HTTP {resp.status_code}")
    try:
        return ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise PlexError(f"invalid XML: {e}") from e


async def test_connection(cfg: PlexConfig) -> list[PlexSection]:
    """Probe /library/sections; return the list of sections on success."""
    root = await _request_xml(cfg, "/library/sections")
    sections: list[PlexSection] = []
    for d in root.iter("Directory"):
        sections.append(
            PlexSection(
                key=d.get("key", ""),
                title=d.get("title", ""),
                kind=d.get("type", ""),
            )
        )
    return sections


# Plex type IDs for the /library/all endpoint.
_PLEX_TYPE = {"movie": "1", "tv": "2"}
# Matching XML element tags returned by the /search endpoint.
_PLEX_SEARCH_TAGS = {"movie": ("Video", "movie"), "tv": ("Directory", "show")}


async def _has_by_tmdb(cfg: PlexConfig, kind: str, tmdb_id: int) -> bool:
    type_id = _PLEX_TYPE.get(kind)
    if type_id is None:
        return False
    try:
        root = await _request_xml(
            cfg,
            "/library/all",
            {"type": type_id, "guid": f"tmdb://{tmdb_id}"},
        )
        if int(root.get("size", "0")) > 0:
            return True
    except PlexError:
        pass
    return False


async def _has_by_title_year(cfg: PlexConfig, kind: str, title: str, year: int | None) -> bool:
    tag_spec = _PLEX_SEARCH_TAGS.get(kind)
    if tag_spec is None:
        return False
    element_tag, type_attr = tag_spec
    try:
        root = await _request_xml(cfg, "/search", {"query": title})
    except PlexError:
        return False
    for el in root.iter(element_tag):
        if el.get("type") != type_attr:
            continue
        if year is None:
            return True
        try:
            el_year = int(el.get("year", "0"))
        except ValueError:
            continue
        if abs(el_year - year) <= 1:
            return True
    return False


async def title_in_library(
    session: Session,
    *,
    kind: str,  # "movie" | "tv"
    tmdb_id: int | None,
    title: str | None,
    year: int | None,
) -> bool:
    """Return True when Plex has the movie/show identified by ``tmdb_id``
    (preferred) or ``title`` + ``year`` (fallback).

    Result is cached for 5 min so one watchlist- or browse-render only
    hits Plex once per unique title.
    """
    if kind not in _PLEX_TYPE:
        return False

    cfg = load_config(session)
    if cfg is None:
        return False

    cache_key = f"{kind}|{tmdb_id or ''}|{(title or '').lower()}|{year or ''}"
    cached = external_cache.get(session, _CACHE_NS, cache_key)
    if cached is not external_cache.UNSET:
        return bool(cached)

    found = False
    try:
        if tmdb_id is not None:
            found = await _has_by_tmdb(cfg, kind, tmdb_id)
        if not found and title:
            found = await _has_by_title_year(cfg, kind, title, year)
    except PlexError as e:
        log.warning("plex.library.lookup_failed", error=str(e))
        return False

    external_cache.set(session, _CACHE_NS, cache_key, found, ttl_seconds=_CACHE_TTL)
    return found


async def movie_in_library(
    session: Session,
    *,
    tmdb_id: int | None,
    title: str | None,
    year: int | None,
) -> bool:
    """Backwards-compatible alias — kept so existing watchlist callers
    don't need to be updated."""
    return await title_in_library(session, kind="movie", tmdb_id=tmdb_id, title=title, year=year)
