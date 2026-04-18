from __future__ import annotations

import re
from difflib import SequenceMatcher

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.api.search import SearchErrorOut, SearchHitOut
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.models.user import User
from trove.services import external_cache, search_service

router = APIRouter()

# Steam storesearch is unauthenticated and rate-limited by IP. Responses
# persist via external_cache (SQLite-backed) so they survive restarts.
_STEAM_CACHE_TTL = 24 * 3600  # 1 day — Steam results are stable enough
_STEAM_NS = "steam"


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
    confidence: float = 0.0  # 0.0 (bad) to 1.0 (perfect)


class SteamSearchOut(BaseModel):
    match: SteamMatch | None


def _normalize_for_match(s: str) -> list[str]:
    """Lowercase, strip punctuation, return tokens suitable for comparison."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def _score_steam_candidate(query: str, candidate_name: str) -> float:
    """Return a 0.0-1.0 similarity score between the cleaned release title
    and a Steam result name.

    Uses a blend of:
      - token Jaccard (bag of words — catches word-order changes)
      - SequenceMatcher ratio (catches typos and partial overlaps)
      - bonus if every query token appears in the candidate

    Short queries (<=2 tokens) lean more on substring matches; longer
    queries lean on Jaccard.
    """
    q_tokens = _normalize_for_match(query)
    c_tokens = _normalize_for_match(candidate_name)
    if not q_tokens or not c_tokens:
        return 0.0

    q_set = set(q_tokens)
    c_set = set(c_tokens)
    jaccard = len(q_set & c_set) / max(len(q_set | c_set), 1)
    ratio = SequenceMatcher(None, " ".join(q_tokens), " ".join(c_tokens)).ratio()
    all_match_bonus = 0.15 if q_set.issubset(c_set) else 0.0

    if len(q_tokens) <= 2:
        base = 0.4 * jaccard + 0.6 * ratio
    else:
        base = 0.65 * jaccard + 0.35 * ratio
    return min(1.0, base + all_match_bonus)


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
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> SteamSearchOut:
    key = q.strip().lower()

    cached = external_cache.get(session, _STEAM_NS, key)
    if cached is not external_cache.UNSET:
        return SteamSearchOut(match=SteamMatch(**cached) if cached else None)

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
            # Score the top 5 candidates and keep the best — Steam's own
            # ranking isn't always right for cracked release names (DLC
            # and soundtracks sneak in ahead of the base game).
            best: SteamMatch | None = None
            for item in items[:5]:
                appid = item.get("id")
                name = item.get("name")
                if not isinstance(appid, int) or not isinstance(name, str):
                    continue
                confidence = _score_steam_candidate(q, name)
                candidate = SteamMatch(
                    appid=appid,
                    name=name,
                    url=f"https://store.steampowered.com/app/{appid}/",
                    image=item.get("tiny_image") or None,
                    confidence=round(confidence, 3),
                )
                if best is None or candidate.confidence > best.confidence:
                    best = candidate
            match = best
    except (httpx.HTTPError, ValueError):
        # Don't cache transient network errors — retry on next hit.
        return SteamSearchOut(match=None)

    external_cache.set(
        session,
        _STEAM_NS,
        key,
        match.model_dump() if match else None,
        ttl_seconds=_STEAM_CACHE_TTL,
    )
    return SteamSearchOut(match=match)
