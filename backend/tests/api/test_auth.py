from __future__ import annotations

from fastapi.testclient import TestClient


def test_status_reports_needs_setup_on_fresh_db(client: TestClient) -> None:
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json() == {"needs_setup": True}


def test_setup_creates_first_user_and_starts_session(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "admin"
    assert "id" in body

    # session cookie should be set
    assert "trove_session" in resp.cookies

    # second setup attempt should 409
    resp2 = client.post(
        "/api/auth/setup",
        json={"username": "other", "password": "another long pass phrase"},
    )
    assert resp2.status_code == 409

    # status now reports no setup needed
    status_resp = client.get("/api/auth/status")
    assert status_resp.json() == {"needs_setup": False}


def test_login_happy_path_and_me_endpoint(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    # logout to clear the session cookie from the setup response
    client.post("/api/auth/logout")
    client.cookies.clear()

    me_unauth = client.get("/api/auth/me")
    assert me_unauth.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert login.json()["username"] == "admin"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_login_rejects_bad_password(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    client.post("/api/auth/logout")
    client.cookies.clear()

    bad = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid_credentials"
