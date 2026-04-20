from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from trove.db import get_engine
from trove.models.indexer import IndexerEventRow, IndexerRow


def _login(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )


def test_delete_indexer_succeeds_when_events_exist(client: TestClient) -> None:
    """Regression: deleting an indexer with search history used to 500 with
    `FOREIGN KEY constraint failed` because indexer_event.indexer_id is a
    non-cascading FK and SQLite enforces FKs (db.py enables PRAGMA
    foreign_keys=ON). The endpoint now cleans up events first."""
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/1337x",
        json={"base_url": "https://1337x.to", "name": None},
    )
    assert resp.status_code == 201
    indexer_id = resp.json()["id"]

    # Manually insert an indexer_event row so the FK would block a naive delete.
    with Session(get_engine()) as session:
        session.add(
            IndexerEventRow(
                indexer_id=indexer_id,
                at=datetime.now(UTC).replace(tzinfo=None),
                success=True,
                hit_count=5,
                elapsed_ms=42,
                query="ubuntu",
            )
        )
        session.commit()

    resp = client.delete(f"/api/indexers/{indexer_id}")
    assert resp.status_code == 204

    # Both the indexer and its events should be gone.
    with Session(get_engine()) as session:
        assert session.get(IndexerRow, indexer_id) is None
        events = session.exec(
            select(IndexerEventRow).where(IndexerEventRow.indexer_id == indexer_id)
        ).all()
        assert events == []
