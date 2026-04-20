from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )


def test_list_catalog_returns_entries(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/indexers/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 12
    slugs = {e["slug"] for e in body}
    assert "thepiratebay" in slugs
    tpb = next(e for e in body if e["slug"] == "thepiratebay")
    assert tpb["already_installed"] is False
    assert tpb["default_mirror"] in tpb["mirrors"]


def test_install_catalog_entry_creates_indexer(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://thepiratebay.org", "name": None},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "cardigann"
    assert body["base_url"] == "https://thepiratebay.org"
    assert body["name"] == "The Pirate Bay"

    # already_installed flips on a subsequent list
    listing = client.get("/api/indexers/catalog").json()
    tpb = next(e for e in listing if e["slug"] == "thepiratebay")
    assert tpb["already_installed"] is True


def test_install_twice_dedups_name(client: TestClient) -> None:
    _login(client)
    first = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://thepiratebay.org"},
    )
    second = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://tpb.party"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["name"] == "The Pirate Bay"
    assert second.json()["name"] == "The Pirate Bay-2"


def test_install_unknown_slug_404(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/not-a-real-site",
        json={"base_url": "https://example.com"},
    )
    assert resp.status_code == 404


def test_install_rejects_base_url_not_in_mirrors(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://totally-evil-mirror.example.com"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "base_url_not_in_catalog_mirrors"
