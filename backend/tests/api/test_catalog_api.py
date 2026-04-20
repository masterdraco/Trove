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
    assert len(body) >= 10
    slugs = {e["slug"] for e in body}
    assert "1337x" in slugs
    entry = next(e for e in body if e["slug"] == "1337x")
    assert entry["already_installed"] is False
    assert entry["default_mirror"] in entry["mirrors"]


def test_install_catalog_entry_creates_indexer(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/1337x",
        json={"base_url": "https://1337x.to", "name": None},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "cardigann"
    assert body["base_url"] == "https://1337x.to"
    assert body["name"] == "1337x"

    # already_installed flips on a subsequent list
    listing = client.get("/api/indexers/catalog").json()
    entry = next(e for e in listing if e["slug"] == "1337x")
    assert entry["already_installed"] is True


def test_install_twice_dedups_name(client: TestClient) -> None:
    _login(client)
    first = client.post(
        "/api/indexers/catalog/1337x",
        json={"base_url": "https://1337x.to"},
    )
    second = client.post(
        "/api/indexers/catalog/1337x",
        json={"base_url": "https://1337x.st"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["name"] == "1337x"
    assert second.json()["name"] == "1337x-2"


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
        "/api/indexers/catalog/1337x",
        json={"base_url": "https://totally-evil-mirror.example.com"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "base_url_not_in_catalog_mirrors"
