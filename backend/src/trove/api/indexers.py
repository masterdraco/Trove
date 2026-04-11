from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.clients.base import Protocol
from trove.indexers.base import Category, IndexerError, IndexerType
from trove.models.indexer import IndexerRow
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
