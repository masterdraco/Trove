from __future__ import annotations

import json

import httpx
import pytest
import respx

from trove.clients.base import AddOptions, Protocol, Release
from trove.clients.deluge import DelugeClient

BASE = "http://deluge.test:8112"
JSON_URL = f"{BASE}/json"


def _responder(handlers):  # type: ignore[no-untyped-def]
    def _inner(request):  # type: ignore[no-untyped-def]
        body = json.loads(request.content.decode("utf-8"))
        method = body["method"]
        request_id = body["id"]
        result = handlers[method](body.get("params") or [])
        return httpx.Response(200, json={"result": result, "error": None, "id": request_id})

    return _inner


@pytest.mark.asyncio
async def test_login_and_test_connection_happy_path() -> None:
    client = DelugeClient(BASE, password="deluge")
    handlers = {
        "auth.login": lambda params: True,
        "web.connected": lambda params: True,
        "core.get_free_space": lambda params: 123456789,
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.post(JSON_URL).mock(side_effect=_responder(handlers))
        health = await client.test_connection()
    assert health.ok is True
    assert health.details["free_space"] == 123456789
    await client.close()


@pytest.mark.asyncio
async def test_add_magnet_calls_add_torrent_magnet() -> None:
    client = DelugeClient(BASE, password="deluge")
    client._logged_in = True  # skip login in this test

    captured: dict[str, object] = {}

    def handle_add(params):  # type: ignore[no-untyped-def]
        captured["magnet"] = params[0]
        captured["opts"] = params[1]
        return "hash-xyz"

    def handle_label(params):  # type: ignore[no-untyped-def]
        captured["label_params"] = params
        return None

    handlers = {
        "core.add_torrent_magnet": handle_add,
        "label.set_torrent": handle_label,
    }
    release = Release(
        title="Ubuntu",
        protocol=Protocol.TORRENT,
        download_url="magnet:?xt=urn:btih:abc",
    )
    options = AddOptions(label="linux", save_path="/downloads/linux")
    with respx.mock(assert_all_called=False) as mock:
        mock.post(JSON_URL).mock(side_effect=_responder(handlers))
        result = await client.add_torrent(release, options)
    assert result.ok is True
    assert result.identifier == "hash-xyz"
    assert captured["magnet"] == "magnet:?xt=urn:btih:abc"
    assert captured["opts"]["download_location"] == "/downloads/linux"  # type: ignore[index]
    assert captured["label_params"] == ["hash-xyz", "linux"]
    await client.close()


@pytest.mark.asyncio
async def test_auth_failure_reports_error() -> None:
    client = DelugeClient(BASE, password="wrong")
    handlers = {"auth.login": lambda params: False}
    with respx.mock(assert_all_called=False) as mock:
        mock.post(JSON_URL).mock(side_effect=_responder(handlers))
        health = await client.test_connection()
    assert health.ok is False
    assert "authentication" in (health.message or "")
    await client.close()
