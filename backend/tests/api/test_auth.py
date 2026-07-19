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


def _setup_admin(client: TestClient, password: str = "correct horse battery staple") -> None:
    client.post("/api/auth/setup", json={"username": "admin", "password": password})


def test_change_password_updates_credentials(client: TestClient) -> None:
    _setup_admin(client)

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "a brand new pass phrase",
        },
    )
    assert resp.status_code == 204

    # session survives the change
    assert client.get("/api/auth/me").status_code == 200

    # old password no longer works, new one does
    client.post("/api/auth/logout")
    client.cookies.clear()

    old = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery staple"},
    )
    assert old.status_code == 401

    new = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "a brand new pass phrase"},
    )
    assert new.status_code == 200


def test_change_password_rejects_wrong_current(client: TestClient) -> None:
    _setup_admin(client)

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "not the right one",
            "new_password": "a brand new pass phrase",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_current_password"


def test_change_password_requires_authentication(client: TestClient) -> None:
    _setup_admin(client)
    client.post("/api/auth/logout")
    client.cookies.clear()

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "a brand new pass phrase",
        },
    )
    assert resp.status_code == 401


def test_change_password_rejects_short_new_password(client: TestClient) -> None:
    _setup_admin(client)

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "short",
        },
    )
    assert resp.status_code == 422
