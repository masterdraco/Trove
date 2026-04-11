from __future__ import annotations

import contextlib
import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser
import httpx
import structlog
from sqlmodel import Session, delete, select

from trove.models.feed import FeedRow, RssItemRow
from trove.utils.crypto import decrypt_json

log = structlog.get_logger()

SIZE_RE = re.compile(r"([\d.,]+)\s*(TB|GB|MB|KB|B)\b", re.IGNORECASE)
SEEDERS_RE = re.compile(r"seeders?\s*[:=]?\s*(\d+)", re.IGNORECASE)
LEECHERS_RE = re.compile(r"leechers?\s*[:=]?\s*(\d+)", re.IGNORECASE)
INFOHASH_RE = re.compile(r"\b([a-f0-9]{40})\b", re.IGNORECASE)
SIZE_MULTIPLIERS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _parse_size(text: str) -> int | None:
    match = SIZE_RE.search(text)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    unit = match.group(2).upper()
    return int(number * SIZE_MULTIPLIERS.get(unit, 1))


def _parse_int(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_magnet_infohash(url: str) -> str | None:
    match = re.search(r"xt=urn:btih:([A-Za-z0-9]+)", url)
    if match:
        return match.group(1).lower()
    return None


def _stable_guid(entry: Any, fallback_title: str) -> str:
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
    if not raw:
        # Hash title + published as last resort
        raw = fallback_title + str(getattr(entry, "published", ""))
    # GUIDs can be long and contain weird chars — hash if > 512
    if len(raw) > 512:
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return raw


def _get_download_url(entry: Any) -> str | None:
    # Prefer enclosure (standard for torrent/NZB feeds)
    enclosures = getattr(entry, "enclosures", None) or []
    if enclosures:
        href = enclosures[0].get("href") or enclosures[0].get("url")
        if href:
            return href
    # Fall back to <link>
    link = getattr(entry, "link", None)
    if link:
        return link
    return None


def _published_datetime(entry: Any) -> datetime | None:
    # SQLite stores datetimes naive, so we strip the tzinfo for consistency
    # with _naive_utcnow below. Datetimes on the DB column are always
    # interpreted as UTC.
    pp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if pp is None:
        return None
    try:
        return datetime(*pp[:6])
    except (TypeError, ValueError):
        return None


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _fetch_feed(feed: FeedRow) -> str:
    credentials: dict[str, Any] = {}
    if feed.credentials_cipher:
        try:
            credentials = decrypt_json(feed.credentials_cipher)
        except ValueError:
            credentials = {}

    headers = dict(credentials.get("headers") or {})
    headers.setdefault("User-Agent", "Trove/0.1 RSS poller")
    cookies = credentials.get("cookies") or None
    auth: tuple[str, str] | None = None
    if "basic_auth_user" in credentials and "basic_auth_pass" in credentials:
        auth = (credentials["basic_auth_user"], credentials["basic_auth_pass"])

    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, headers=headers, cookies=cookies, auth=auth
    ) as client:
        resp = await client.get(feed.url)
        resp.raise_for_status()
        return resp.text


def _entry_to_row(feed_id: int, entry: Any) -> RssItemRow | None:
    title = getattr(entry, "title", None)
    if not title:
        return None
    download_url = _get_download_url(entry)
    if not download_url:
        return None

    description = getattr(entry, "summary", None) or getattr(entry, "description", "") or ""
    search_text = f"{title} {description}"

    # Try Torznab attrs first (feedparser puts them in namespaces — we look in raw dict)
    size: int | None = None
    seeders: int | None = None
    leechers: int | None = None
    infohash: str | None = None
    category: str | None = None

    # feedparser normalizes namespaced attrs into entry.get() lookups
    raw = dict(entry) if hasattr(entry, "keys") else {}
    for key, value in raw.items():
        lower_key = key.lower() if isinstance(key, str) else ""
        if lower_key.endswith("size") and value and str(value).isdigit():
            size = int(value)
        elif lower_key.endswith("seeders") and value and str(value).isdigit():
            seeders = int(value)
        elif lower_key.endswith("leechers") and value and str(value).isdigit():
            leechers = int(value)
        elif lower_key.endswith("infohash") and isinstance(value, str):
            infohash = value.lower()

    # Enclosure length is the most common size hint
    enclosures = getattr(entry, "enclosures", None) or []
    if size is None and enclosures:
        length = enclosures[0].get("length")
        if length:
            with contextlib.suppress(TypeError, ValueError):
                size = int(length)

    # Fall back to scraping description
    if size is None:
        size = _parse_size(description)
    if seeders is None:
        seeders = _parse_int(SEEDERS_RE, search_text)
    if leechers is None:
        leechers = _parse_int(LEECHERS_RE, search_text)
    if infohash is None:
        if download_url.startswith("magnet:"):
            infohash = _extract_magnet_infohash(download_url)
        else:
            m = INFOHASH_RE.search(search_text)
            if m:
                infohash = m.group(1).lower()

    tags = getattr(entry, "tags", None) or []
    if tags:
        term = tags[0].get("term") if isinstance(tags[0], dict) else None
        if term:
            category = str(term)[:64]

    return RssItemRow(
        feed_id=feed_id,
        guid=_stable_guid(entry, title)[:512],
        title=title[:512],
        normalized_title=normalize_title(title)[:512],
        download_url=download_url[:2048],
        infohash=infohash,
        size=size,
        seeders=seeders,
        leechers=leechers,
        category=category,
        published_at=_published_datetime(entry),
        fetched_at=_naive_utcnow(),
        raw_description=description[:4096] if description else None,
    )


async def poll_feed(session: Session, feed: FeedRow) -> dict[str, Any]:
    """Fetch one feed, upsert new items, update stats."""
    assert feed.id is not None
    started = _naive_utcnow()
    try:
        body = await _fetch_feed(feed)
    except httpx.HTTPError as e:
        feed.last_polled_at = started
        feed.last_poll_status = "error"
        feed.last_poll_message = f"http: {e}"[:512]
        session.add(feed)
        session.commit()
        return {"ok": False, "error": str(e), "new_items": 0}

    parsed = feedparser.parse(body)
    if parsed.bozo and not parsed.entries:
        feed.last_polled_at = started
        feed.last_poll_status = "error"
        feed.last_poll_message = f"parse: {parsed.bozo_exception}"[:512]
        session.add(feed)
        session.commit()
        return {"ok": False, "error": str(parsed.bozo_exception), "new_items": 0}

    new_count = 0
    for entry in parsed.entries:
        row = _entry_to_row(feed.id, entry)
        if row is None:
            continue
        existing = session.exec(
            select(RssItemRow)
            .where(RssItemRow.feed_id == feed.id)
            .where(RssItemRow.guid == row.guid)
        ).first()
        if existing is not None:
            # Refresh mutable fields (seeders/leechers shift over time)
            updated = False
            if row.seeders is not None and row.seeders != existing.seeders:
                existing.seeders = row.seeders
                updated = True
            if row.leechers is not None and row.leechers != existing.leechers:
                existing.leechers = row.leechers
                updated = True
            if updated:
                session.add(existing)
            continue
        session.add(row)
        new_count += 1

    # Retention cleanup — SQLite stores datetimes as naive, and every
    # fetched_at above is also naive, so cutoff has to match. Otherwise
    # SQLAlchemy's in-memory bulk evaluator fails comparing the pending
    # rows against the WHERE expression.
    if feed.retention_days > 0:
        cutoff = _naive_utcnow() - timedelta(days=feed.retention_days)
        session.exec(  # type: ignore[call-overload]
            delete(RssItemRow)
            .where(RssItemRow.feed_id == feed.id)
            .where(RssItemRow.fetched_at < cutoff)
        )

    # Update stats
    total = session.exec(select(RssItemRow).where(RssItemRow.feed_id == feed.id)).all()
    feed.total_items = len(total)
    feed.last_new_items = new_count
    feed.last_polled_at = started
    feed.last_poll_status = "ok"
    feed.last_poll_message = None
    session.add(feed)
    session.commit()
    log.info("feed.polled", name=feed.name, new=new_count, total=feed.total_items)
    return {"ok": True, "new_items": new_count, "total": feed.total_items}


async def preview_feed(
    url: str,
    credentials: dict[str, Any] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch and parse a feed without storing it. Used by the UI preview button."""
    headers = dict((credentials or {}).get("headers") or {})
    headers.setdefault("User-Agent", "Trove/0.1 RSS preview")
    cookies = (credentials or {}).get("cookies") or None
    auth: tuple[str, str] | None = None
    if credentials and "basic_auth_user" in credentials and "basic_auth_pass" in credentials:
        auth = (credentials["basic_auth_user"], credentials["basic_auth_pass"])

    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, headers=headers, cookies=cookies, auth=auth
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.text

    parsed = feedparser.parse(body)
    items: list[dict[str, Any]] = []
    for entry in parsed.entries[:limit]:
        row = _entry_to_row(feed_id=0, entry=entry)
        if row is None:
            continue
        items.append(
            {
                "title": row.title,
                "download_url": row.download_url,
                "size": row.size,
                "seeders": row.seeders,
                "leechers": row.leechers,
                "infohash": row.infohash,
                "category": row.category,
                "published_at": row.published_at.isoformat() if row.published_at else None,
            }
        )
    return items
