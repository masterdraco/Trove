from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.api.search import SearchErrorOut, SearchHitOut
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.models.user import User
from trove.services import search_service

router = APIRouter()

# Steam storesearch is unauthenticated and rate-limited by IP. We keep a
# small in-process cache keyed by the normalized query so reopening the
# games tab doesn't re-hit Steam for every row.
_STEAM_CACHE_TTL = 3600.0
_STEAM_CACHE_MAX = 500
_steam_cache: dict[str, tuple[float, "SteamMatch | None"]] = {}


class BrowseResponseOut(BaseModel):
    category: Category
    hits: list[SearchHitOut]
    indexers_used: int
    elapsed_ms: int
    errors: list[SearchErrorOut]


class SteamMatch(BaseModel):
    appid: int
    name: str
    url: str
    image: str | None = None


class SteamSearchOut(BaseModel):
    match: SteamMatch | None


@router.get("/latest", response_model=BrowseResponseOut)
async def latest(
    category: Category = Query(Category.SOFTWARE, alias="cat"),
    protocol: Protocol | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> BrowseResponseOut:
    result = await search_service.run_browse(
        session,
        category=category,
        protocol=protocol,
        limit=limit,
    )
    return BrowseResponseOut(
        category=category,
        hits=[
            SearchHitOut(
                title=h.title,
                protocol=h.protocol,
                size=h.size,
                seeders=h.seeders,
                leechers=h.leechers,
                download_url=h.download_url,
                infohash=h.infohash,
                category=h.category,
                source=h.source,
                score=h.score,
                published_at=h.published_at,
            )
            for h in result.hits
        ],
        indexers_used=result.indexers_used,
        elapsed_ms=result.elapsed_ms,
        errors=[SearchErrorOut(name=e.name, message=e.message) for e in result.errors],
    )


@router.get("/steam", response_model=SteamSearchOut)
async def steam_search(
    q: str = Query(..., min_length=1, max_length=256),
    _user: User = Depends(current_user),
) -> SteamSearchOut:
    key = q.strip().lower()
    now = time.time()

    cached = _steam_cache.get(key)
    if cached is not None and now - cached[0] < _STEAM_CACHE_TTL:
        return SteamSearchOut(match=cached[1])

    match: SteamMatch | None = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": q, "l": "en", "cc": "us"},
            )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items") or []
            if items:
                top = items[0]
                appid = top.get("id")
                name = top.get("name")
                if isinstance(appid, int) and isinstance(name, str):
                    match = SteamMatch(
                        appid=appid,
                        name=name,
                        url=f"https://store.steampowered.com/app/{appid}/",
                        image=top.get("tiny_image") or None,
                    )
    except (httpx.HTTPError, ValueError):
        match = None

    _steam_cache[key] = (now, match)
    if len(_steam_cache) > _STEAM_CACHE_MAX:
        for stale_key in [k for k, (ts, _) in _steam_cache.items() if now - ts > _STEAM_CACHE_TTL]:
            _steam_cache.pop(stale_key, None)

    return SteamSearchOut(match=match)
