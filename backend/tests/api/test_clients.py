from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )


def test_create_list_and_test_client(client: TestClient) -> None:
    _login(client)

    create = client.post(
        "/api/clients",
        json={
            "name": "home-transmission",
            "type": "transmission",
            "url": "http://trans.test:9091",
            "credentials": {"username": "admin", "password": "secret"},
            "default_save_path": "/downloads",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "home-transmission"
    assert body["protocol"] == "torrent"
    client_id = body["id"]

    listing = client.get("/api/clients")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert listing.json()[0]["id"] == client_id

    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://trans.test:9091/transmission/rpc").mock(
            return_value=httpx.Response(
                200,
                json={"result": "success", "arguments": {"version": "4.0.5"}},
            )
        )
        test = client.post(f"/api/clients/{client_id}/test")

    assert test.status_code == 200
    result = test.json()
    assert result["ok"] is True
    assert result["version"] == "4.0.5"


def test_duplicate_name_is_rejected(client: TestClient) -> None:
    _login(client)
    payload = {
        "name": "only-one",
        "type": "transmission",
        "url": "http://trans.test:9091",
        "credentials": {},
    }
    assert client.post("/api/clients", json=payload).status_code == 201
    second = client.post("/api/clients", json=payload)
    assert second.status_code == 409


def test_update_and_delete(client: TestClient) -> None:
    _login(client)
    created = client.post(
        "/api/clients",
        json={
            "name": "sab",
            "type": "sabnzbd",
            "url": "http://sab.test:8080",
            "credentials": {"api_key": "k"},
        },
    )
    client_id = created.json()["id"]

    patched = client.patch(
        f"/api/clients/{client_id}",
        json={"default_category": "tv", "enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["default_category"] == "tv"
    assert patched.json()["enabled"] is False

    deleted = client.delete(f"/api/clients/{client_id}")
    assert deleted.status_code == 204
    assert client.get("/api/clients").json() == []


def test_unauthenticated_access_is_blocked(client: TestClient) -> None:
    _login(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/clients").status_code == 401
