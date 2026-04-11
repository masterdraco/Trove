from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlmodel import Session, select

from trove.clients.base import Protocol, Release
from trove.indexers.base import Category, IndexerError, SearchQuery
from trove.models.feed import FeedRow, RssItemRow
from trove.models.indexer import IndexerRow
from trove.services import indexer_registry

log = structlog.get_logger()


@dataclass(slots=True)
class SearchHit:
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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchError:
    name: str
    message: str


@dataclass(slots=True)
class SearchResponse:
    query: str
    hits: list[SearchHit]
    indexers_used: int
    elapsed_ms: int
    errors: list[SearchError]


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _hit_from_release(release: Release) -> SearchHit:
    meta = release.metadata or {}
    seeders = meta.get("seeders")
    leechers = meta.get("leechers")
    published = meta.get("published_at")
    return SearchHit(
        title=release.title,
        protocol=release.protocol,
        size=release.size,
        seeders=int(seeders)
        if isinstance(seeders, (int, str)) and str(seeders).isdigit()
        else None,
        leechers=int(leechers)
        if isinstance(leechers, (int, str)) and str(leechers).isdigit()
        else None,
        download_url=release.download_url,
        infohash=release.infohash,
        category=release.category,
        source=release.source,
        score=0.0,
        published_at=published if isinstance(published, str) else None,
        metadata=dict(meta),
    )


def _score(hit: SearchHit) -> float:
    score = 0.0
    if hit.seeders is not None:
        score += min(hit.seeders, 200) * 0.5
    if hit.size and 500 * 1024 * 1024 <= hit.size <= 15 * 1024 * 1024 * 1024:
        score += 10
    title_lower = hit.title.lower()
    for bonus_tag, pts in (
        ("1080p", 5),
        ("2160p", 4),
        ("x265", 4),
        ("hevc", 4),
        ("remux", 6),
        ("web-dl", 3),
        ("bluray", 3),
    ):
        if bonus_tag in title_lower:
            score += pts
    for penalty_tag, pts in (
        ("cam", -30),
        ("ts", -15),
        ("telesync", -15),
        ("workprint", -20),
    ):
        if penalty_tag in title_lower:
            score += pts
    return score


def _dedupe(hits: list[SearchHit]) -> list[SearchHit]:
    by_hash: dict[str, SearchHit] = {}
    by_title: dict[str, SearchHit] = {}
    output: list[SearchHit] = []
    for hit in hits:
        if hit.infohash:
            key = hit.infohash.lower()
            if key in by_hash:
                existing = by_hash[key]
                if hit.score > existing.score:
                    by_hash[key] = hit
                continue
            by_hash[key] = hit
            output.append(hit)
            continue
        norm = _normalize_title(hit.title)
        if norm in by_title:
            existing = by_title[norm]
            if hit.score > existing.score:
                by_title[norm] = hit
            continue
        by_title[norm] = hit
        output.append(hit)
    # rebuild output order: keep by_hash + by_title unique set
    seen: set[int] = set()
    result: list[SearchHit] = []
    for h in output:
        current = (
            by_hash.get((h.infohash or "").lower())
            if h.infohash
            else by_title.get(_normalize_title(h.title))
        )
        if current is None:
            continue
        if id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
    return result


def _search_local_rss(
    session: Session,
    query: str,
    protocol: Protocol | None,
    limit: int,
) -> list[SearchHit]:
    """Query the local RSS store for cached items matching the query."""
    # Build LIKE-pattern from normalized query terms. Split on whitespace so
    # "the bear s03" matches "The.Bear.S03E04.1080p.WEB-DL" etc.
    terms = [t for t in _normalize_title(query).split() if t]
    if not terms:
        return []

    feed_ids_by_protocol: list[int] | None = None
    if protocol is not None:
        feeds = session.exec(
            select(FeedRow).where(FeedRow.protocol_hint == protocol.value)
        ).all()
        feed_ids_by_protocol = [f.id for f in feeds if f.id is not None]
        if not feed_ids_by_protocol:
            return []

    stmt = select(RssItemRow, FeedRow).where(RssItemRow.feed_id == FeedRow.id)
    if feed_ids_by_protocol is not None:
        stmt = stmt.where(RssItemRow.feed_id.in_(feed_ids_by_protocol))  # type: ignore[attr-defined]
    for term in terms:
        stmt = stmt.where(RssItemRow.normalized_title.like(f"%{term}%"))  # type: ignore[attr-defined]
    stmt = stmt.order_by(RssItemRow.fetched_at.desc()).limit(limit * 2)  # type: ignore[attr-defined]

    hits: list[SearchHit] = []
    for item, feed in session.exec(stmt).all():
        try:
            hit_protocol = Protocol(feed.protocol_hint)
        except ValueError:
            hit_protocol = Protocol.TORRENT
        hits.append(
            SearchHit(
                title=item.title,
                protocol=hit_protocol,
                size=item.size,
                seeders=item.seeders,
                leechers=item.leechers,
                download_url=item.download_url,
                infohash=item.infohash,
                category=item.category,
                source=f"rss:{feed.name}",
                score=0.0,
                published_at=item.published_at.isoformat() if item.published_at else None,
            )
        )
    return hits


async def run_search(
    session: Session,
    query: str,
    *,
    categories: list[Category] | None = None,
    protocol: Protocol | None = None,
    min_seeders: int | None = None,
    max_size_mb: int | None = None,
    limit: int = 100,
    timeout_per_indexer: float = 15.0,
) -> SearchResponse:
    start = time.monotonic()
    rows = session.exec(
        select(IndexerRow)
        .where(IndexerRow.enabled == True)  # noqa: E712
        .order_by(IndexerRow.priority)
    ).all()

    if protocol is not None:
        rows = [r for r in rows if r.protocol == protocol.value]

    async def _run_one(row: IndexerRow) -> tuple[str, list[Release] | Exception]:
        try:
            driver = indexer_registry.build_driver(row)
        except IndexerError as e:
            return row.name, e
        try:
            async with asyncio.timeout(timeout_per_indexer):
                releases = await driver.search(
                    SearchQuery(terms=query, categories=categories or [], limit=limit)
                )
            return row.name, releases
        except (IndexerError, TimeoutError, asyncio.TimeoutError) as e:  # noqa: UP041
            return row.name, e
        except Exception as e:  # pragma: no cover - defensive
            log.warning("indexer.search.unexpected", name=row.name, error=str(e))
            return row.name, e
        finally:
            await driver.close()

    results = await asyncio.gather(*(_run_one(row) for row in rows))

    hits: list[SearchHit] = []
    errors: list[SearchError] = []
    for name, outcome in results:
        if isinstance(outcome, Exception):
            errors.append(SearchError(name=name, message=str(outcome)))
            continue
        for release in outcome:
            hit = _hit_from_release(release)
            hits.append(hit)

    # Mix in locally-cached RSS items. This works even when no indexers are
    # configured, turning Trove into its own search surface.
    try:
        hits.extend(_search_local_rss(session, query, protocol, limit))
    except Exception as e:  # pragma: no cover - defensive
        log.warning("search.local_rss.failed", error=str(e))
        errors.append(SearchError(name="local-rss", message=str(e)))

    for hit in hits:
        hit.score = _score(hit)

    # Hard filters
    if min_seeders is not None:
        hits = [h for h in hits if (h.seeders or 0) >= min_seeders]
    if max_size_mb is not None:
        size_cap = max_size_mb * 1024 * 1024
        hits = [h for h in hits if h.size is None or h.size <= size_cap]

    hits = _dedupe(hits)
    hits.sort(key=lambda h: h.score, reverse=True)

    elapsed = int((time.monotonic() - start) * 1000)
    return SearchResponse(
        query=query,
        hits=hits[:limit],
        indexers_used=len(rows),
        elapsed_ms=elapsed,
        errors=errors,
    )
