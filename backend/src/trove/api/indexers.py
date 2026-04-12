from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.clients.base import Protocol
from trove.indexers.base import Category, IndexerError, IndexerType
from trove.models.indexer import IndexerEventRow, IndexerRow
from trove.models.user import User
from trove.services import indexer_registry

router = APIRouter()


class IndexerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: IndexerType
    protocol: Protocol
    base_url: str = Field(min_length=1, max_length=512)
    credentials: dict[str, Any] = Field(default_factory=dict)
    definition_yaml: str | None = None
    enabled: bool = True
    priority: int = 50


class IndexerUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    credentials: dict[str, Any] | None = None
    definition_yaml: str | None = None
    enabled: bool | None = None
    priority: int | None = None


class IndexerOut(BaseModel):
    id: int
    name: str
    type: IndexerType
    protocol: Protocol
    base_url: str
    enabled: bool
    priority: int
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None


class IndexerTestResult(BaseModel):
    ok: bool
    version: str | None = None
    message: str | None = None
    supported_categories: list[Category] = Field(default_factory=list)


def _to_out(row: IndexerRow) -> IndexerOut:
    assert row.id is not None
    return IndexerOut(
        id=row.id,
        name=row.name,
        type=IndexerType(row.type),
        protocol=Protocol(row.protocol),
        base_url=row.base_url,
        enabled=row.enabled,
        priority=row.priority,
        last_test_at=row.last_test_at,
        last_test_ok=row.last_test_ok,
        last_test_message=row.last_test_message,
    )


@router.get("", response_model=list[IndexerOut])
async def list_indexers(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[IndexerOut]:
    rows = session.exec(select(IndexerRow).order_by(IndexerRow.priority, IndexerRow.name)).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=IndexerOut, status_code=status.HTTP_201_CREATED)
async def create_indexer(
    payload: IndexerCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> IndexerOut:
    existing = session.exec(select(IndexerRow).where(IndexerRow.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")
    row = IndexerRow(
        name=payload.name,
        type=payload.type.value,
        protocol=payload.protocol.value,
        base_url=payload.base_url,
        credentials_cipher=indexer_registry.encrypt_credentials(payload.credentials),
        definition_yaml=payload.definition_yaml,
        enabled=payload.enabled,
        priority=payload.priority,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.patch("/{indexer_id}", response_model=IndexerOut)
async def update_indexer(
    indexer_id: int,
    payload: IndexerUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> IndexerOut:
    row = session.get(IndexerRow, indexer_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if payload.name is not None and payload.name != row.name:
        clash = session.exec(select(IndexerRow).where(IndexerRow.name == payload.name)).first()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")
        row.name = payload.name
    if payload.base_url is not None:
        row.base_url = payload.base_url
    if payload.credentials is not None:
        row.credentials_cipher = indexer_registry.encrypt_credentials(payload.credentials)
    if payload.definition_yaml is not None:
        row.definition_yaml = payload.definition_yaml
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.priority is not None:
        row.priority = payload.priority
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{indexer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_indexer(
    indexer_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(IndexerRow, indexer_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    session.delete(row)
    session.commit()


class IndexerHealthOut(BaseModel):
    id: int
    name: str
    type: IndexerType
    protocol: Protocol
    enabled: bool
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None
    # Aggregated metrics over the last 24 hours of /api/search + task runs
    events_24h: int
    successes_24h: int
    failures_24h: int
    success_rate_24h: float  # 0.0..1.0
    avg_elapsed_ms_24h: int | None
    total_hits_24h: int
    last_event_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error_message: str | None
    # Last-24h sparkline buckets — one entry per hour, oldest first,
    # each is (event_count, failure_count, avg_ms). The UI uses this
    # to render a compact 24-hour response-time / failure chart.
    sparkline: list[list[int]]


@router.get("/health", response_model=list[IndexerHealthOut])
async def list_indexer_health(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[IndexerHealthOut]:
    """Per-indexer operational stats for the health dashboard.

    Aggregates IndexerEventRow entries over the last 24 hours and merges
    them with the static last_test_* fields on IndexerRow. Indexers that
    have no recent events still appear — just with zeroes and whatever
    test result they last reported.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=24)

    indexer_rows = session.exec(
        select(IndexerRow).order_by(IndexerRow.priority, IndexerRow.name)
    ).all()
    if not indexer_rows:
        return []

    event_rows = session.exec(select(IndexerEventRow).where(IndexerEventRow.at >= cutoff)).all()

    # Bucket events per indexer so we can aggregate in one pass.
    by_indexer: dict[int, list[IndexerEventRow]] = {}
    for e in event_rows:
        by_indexer.setdefault(e.indexer_id, []).append(e)

    out: list[IndexerHealthOut] = []
    for row in indexer_rows:
        assert row.id is not None
        events = by_indexer.get(row.id, [])
        total = len(events)
        successes = sum(1 for e in events if e.success)
        failures = total - successes
        total_hits = sum(e.hit_count for e in events if e.success)
        avg_ms = int(sum(e.elapsed_ms for e in events) / total) if total > 0 else None
        success_rate = (successes / total) if total > 0 else 0.0

        last_at = max((e.at for e in events), default=None)
        last_success_at = max((e.at for e in events if e.success), default=None)
        last_failure_at = max((e.at for e in events if not e.success), default=None)
        last_error_message: str | None = None
        if last_failure_at is not None:
            for e in events:
                if not e.success and e.at == last_failure_at:
                    last_error_message = e.error_message
                    break

        # Bucket into 24 hourly slots, oldest first.
        buckets: list[list[int]] = []
        for i in range(24):
            bucket_start = cutoff + timedelta(hours=i)
            bucket_end = bucket_start + timedelta(hours=1)
            bucket_events = [e for e in events if bucket_start <= e.at < bucket_end]
            b_count = len(bucket_events)
            b_failures = sum(1 for e in bucket_events if not e.success)
            b_avg = int(sum(e.elapsed_ms for e in bucket_events) / b_count) if b_count > 0 else 0
            buckets.append([b_count, b_failures, b_avg])

        out.append(
            IndexerHealthOut(
                id=row.id,
                name=row.name,
                type=IndexerType(row.type),
                protocol=Protocol(row.protocol),
                enabled=row.enabled,
                last_test_at=row.last_test_at,
                last_test_ok=row.last_test_ok,
                last_test_message=row.last_test_message,
                events_24h=total,
                successes_24h=successes,
                failures_24h=failures,
                success_rate_24h=success_rate,
                avg_elapsed_ms_24h=avg_ms,
                total_hits_24h=total_hits,
                last_event_at=last_at,
                last_success_at=last_success_at,
                last_failure_at=last_failure_at,
                last_error_message=last_error_message,
                sparkline=buckets,
            )
        )

    # Best-effort prune: drop events older than 30 days so the table
    # doesn't grow forever. Cheap because indexer_event.at is indexed.
    try:
        prune_cutoff = now - timedelta(days=30)
        session.execute(sql_delete(IndexerEventRow).where(IndexerEventRow.at < prune_cutoff))
        session.commit()
    except Exception:
        session.rollback()

    return out


@router.post("/{indexer_id}/test", response_model=IndexerTestResult)
async def test_indexer(
    indexer_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> IndexerTestResult:
    row = session.get(IndexerRow, indexer_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    try:
        driver = indexer_registry.build_driver(row)
    except IndexerError as e:
        return IndexerTestResult(ok=False, message=str(e))
    try:
        health = await driver.test_connection()
    finally:
        await driver.close()

    row.last_test_at = datetime.now(UTC)
    row.last_test_ok = health.ok
    row.last_test_message = (health.message or "")[:512] or None
    session.add(row)
    session.commit()

    return IndexerTestResult(
        ok=health.ok,
        version=health.version,
        message=health.message,
        supported_categories=health.supported_categories,
    )
