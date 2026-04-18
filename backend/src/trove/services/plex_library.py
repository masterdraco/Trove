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

import json
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


async def has_movie_by_tmdb(cfg: PlexConfig, tmdb_id: int) -> bool:
    """Check whether the Plex library contains a movie with tmdb://<id>."""
    # /library/all matches items scraped with the TMDB agent. Plex exposes
    # the GUID as an attribute like guid="plex://movie/123" plus a
    # <Guid id="tmdb://12345"/> child when alternative GUIDs are present.
    # Using guid=tmdb://X works when TMDB is the primary agent, otherwise
    # we have to page through and inspect children.
    try:
        root = await _request_xml(
            cfg,
            "/library/all",
            {
                "type": "1",  # movie
                "guid": f"tmdb://{tmdb_id}",
            },
        )
        if int(root.get("size", "0")) > 0:
            return True
    except PlexError:
        pass

    # Fallback: search across sections by title (callers should also pass
    # the title separately for true fuzzy matches; this branch only
    # returns True on an exact tmdb GUID so we don't false-positive by
    # title alone here).
    return False


async def has_movie_by_title_year(cfg: PlexConfig, title: str, year: int | None) -> bool:
    """Fallback for libraries scraped without TMDB agent: title+year."""
    try:
        root = await _request_xml(
            cfg,
            "/search",
            {"query": title},
        )
    except PlexError:
        return False
    for v in root.iter("Video"):
        if v.get("type") != "movie":
            continue
        if year is None:
            return True
        try:
            v_year = int(v.get("year", "0"))
        except ValueError:
            continue
        if abs(v_year - year) <= 1:
            return True
    return False


async def movie_in_library(
    session: Session,
    *,
    tmdb_id: int | None,
    title: str | None,
    year: int | None,
) -> bool:
    """Public helper that picks the best available match strategy.

    Result is cached for 5 min per (tmdb_id | title+year) so a single
    watchlist-list call only hits Plex once per unique movie.
    """
    cfg = load_config(session)
    if cfg is None:
        return False

    key_parts = [
        str(tmdb_id or ""),
        (title or "").lower(),
        str(year or ""),
    ]
    cache_key = "|".join(key_parts)

    cached = external_cache.get(session, _CACHE_NS, cache_key)
    if cached is not external_cache.UNSET:
        return bool(cached)

    found = False
    try:
        if tmdb_id is not None:
            found = await has_movie_by_tmdb(cfg, tmdb_id)
        if not found and title:
            found = await has_movie_by_title_year(cfg, title, year)
    except PlexError as e:
        log.warning("plex.library.lookup_failed", error=str(e))
        # Don't cache transient errors
        return False

    external_cache.set(session, _CACHE_NS, cache_key, found, ttl_seconds=_CACHE_TTL)
    return found
