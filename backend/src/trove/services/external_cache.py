"""Generic persistent cache for third-party API responses.

Used by browse-enrichment (Steam storesearch today, TMDB/Spotify/etc.
tomorrow) so lookups survive container restarts and upgrades. Each
entry is namespaced so one provider's keys can't collide with another's.

Payloads are stored as JSON text — callers pass in whatever ``dict`` or
``list`` they want cached. Pass ``None`` as the value for a negative
cache entry (provider returned no match for this key), which still
takes up a row but avoids refiring the upstream call on every request.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlmodel import Session, delete, select

from trove.models.external_cache import ExternalCacheRow

log = structlog.get_logger()

_UNSET = object()


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _row_expired(row: ExternalCacheRow, now: datetime) -> bool:
    if row.expires_at is None:
        return False
    expires = row.expires_at
    # SQLite stores naive UTC datetimes; promote to aware for comparison.
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= now


def get(session: Session, namespace: str, key: str) -> Any | None | object:
    """Return the cached payload for ``namespace:key``, or ``_UNSET`` if
    there is no live entry.

    We return the sentinel (distinct from ``None``) so negative caching
    is possible — ``None`` is a valid cached value meaning "provider
    returned no match, don't bother looking again until expiry".
    """
    key_hash = _hash(key)
    row = session.exec(
        select(ExternalCacheRow).where(
            ExternalCacheRow.namespace == namespace,
            ExternalCacheRow.key_hash == key_hash,
        )
    ).first()
    if row is None:
        return _UNSET
    if _row_expired(row, _now()):
        session.delete(row)
        try:
            session.commit()
        except Exception as e:  # pragma: no cover
            log.warning("external_cache.expire.commit_failed", error=str(e))
            session.rollback()
        return _UNSET
    try:
        return json.loads(row.payload)
    except ValueError:  # pragma: no cover — corrupted row
        session.delete(row)
        with _suppress_commit_error(session):
            session.commit()
        return _UNSET


def set(
    session: Session,
    namespace: str,
    key: str,
    value: Any,
    *,
    ttl_seconds: int,
) -> None:
    """Store ``value`` (any JSON-serialisable object, including ``None``)
    under ``namespace:key`` with the given TTL."""
    key_hash = _hash(key)
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None
    payload = json.dumps(value)

    existing = session.exec(
        select(ExternalCacheRow).where(
            ExternalCacheRow.namespace == namespace,
            ExternalCacheRow.key_hash == key_hash,
        )
    ).first()
    if existing is not None:
        existing.payload = payload
        existing.created_at = now
        existing.expires_at = expires_at
        session.add(existing)
    else:
        session.add(
            ExternalCacheRow(
                namespace=namespace,
                key_hash=key_hash,
                payload=payload,
                created_at=now,
                expires_at=expires_at,
            )
        )
    with _suppress_commit_error(session):
        session.commit()


def purge_expired(session: Session) -> int:
    """Delete every expired row. Returns the count removed."""
    now = _now()
    rows = session.exec(
        select(ExternalCacheRow).where(
            ExternalCacheRow.expires_at.is_not(None),  # type: ignore[attr-defined]
            ExternalCacheRow.expires_at <= now,
        )
    ).all()
    count = len(rows)
    if count == 0:
        return 0
    session.exec(
        delete(ExternalCacheRow).where(  # type: ignore[arg-type]
            ExternalCacheRow.expires_at.is_not(None),  # type: ignore[attr-defined]
            ExternalCacheRow.expires_at <= now,
        )
    )
    with _suppress_commit_error(session):
        session.commit()
    return count


UNSET = _UNSET


class _suppress_commit_error:
    def __init__(self, session: Session) -> None:
        self.session = session

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            log.warning("external_cache.commit_failed", error=str(exc))
            self.session.rollback()
            return True
        return False
