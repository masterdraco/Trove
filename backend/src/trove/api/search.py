from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.models.user import User
from trove.services import search_service

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    categories: list[Category] = Field(default_factory=list)
    protocol: Protocol | None = None
    min_seeders: int | None = None
    max_size_mb: int | None = None
    use_ai_ranking: bool = False
    limit: int = 100


class SearchHitOut(BaseModel):
    title: str
    protocol: Protocol
    size: int | None
    seeders: int | None
    leechers: int | None
    download_url: str | None
    infohash: str | None
    category: str | None
    source: str | None
    score: float
    published_at: str | None = None
    group: str | None = None
    group_tier: str | None = None


class SearchErrorOut(BaseModel):
    name: str
    message: str


class SearchResponseOut(BaseModel):
    query: str
    hits: list[SearchHitOut]
    indexers_used: int
    elapsed_ms: int
    errors: list[SearchErrorOut]


@router.post("", response_model=SearchResponseOut)
async def search(
    payload: SearchRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> SearchResponseOut:
    result = await search_service.run_search(
        session,
        payload.query,
        categories=payload.categories,
        protocol=payload.protocol,
        min_seeders=payload.min_seeders,
        max_size_mb=payload.max_size_mb,
        limit=payload.limit,
    )

    hits = [
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
            group=h.group,
            group_tier=h.group_tier,
        )
        for h in result.hits
    ]

    if payload.use_ai_ranking:
        from trove.ai import ranker  # lazy import — AI is optional

        hits = await ranker.rerank(hits, payload.query)

    return SearchResponseOut(
        query=result.query,
        hits=hits,
        indexers_used=result.indexers_used,
        elapsed_ms=result.elapsed_ms,
        errors=[SearchErrorOut(name=e.name, message=e.message) for e in result.errors],
    )
