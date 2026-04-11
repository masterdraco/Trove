from __future__ import annotations

import httpx
import pytest
import respx

from trove.clients.base import AddOptions, Protocol, Release
from trove.clients.transmission import SESSION_HEADER, TransmissionClient

BASE = "http://trans.test:9091"
RPC = f"{BASE}/transmission/rpc"


@pytest.mark.asyncio
async def test_test_connection_retries_session_id() -> None:
    client = TransmissionClient(BASE)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(RPC)
        route.side_effect = [
            httpx.Response(409, headers={SESSION_HEADER: "sess-123"}, text="conflict"),
            httpx.Response(
                200,
                json={
                    "result": "success",
                    "arguments": {
                        "version": "4.0.5",
                        "rpc-version": 18,
                        "download-dir": "/downloads",
                    },
                },
            ),
        ]
        health = await client.test_connection()
    assert health.ok is True
    assert health.version == "4.0.5"
    assert client._session_id == "sess-123"
    await client.close()


@pytest.mark.asyncio
async def test_add_magnet_sends_filename_argument() -> None:
    client = TransmissionClient(BASE)
    client._session_id = "sess-abc"
    release = Release(
        title="Ubuntu 24.04",
        protocol=Protocol.TORRENT,
        download_url="magnet:?xt=urn:btih:abcdef",
    )
    options = AddOptions(save_path="/downloads/iso", label="iso")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(RPC).mock(
            return_value=httpx.Response(
                200,
                json={
                    "result": "success",
                    "arguments": {
                        "torrent-added": {"id": 12, "hashString": "abcdef123"},
                    },
                },
            )
        )
        result = await client.add_torrent(release, options)
        req = route.calls[0].request
        body = req.content.decode("utf-8")
    assert result.ok is True
    assert result.identifier == "abcdef123"
    assert "filename" in body
    assert "/downloads/iso" in body
    await client.close()


@pytest.mark.asyncio
async def test_failed_result_raises_client_error() -> None:
    client = TransmissionClient(BASE)
    client._session_id = "x"
    with respx.mock(assert_all_called=True) as mock:
        mock.post(RPC).mock(return_value=httpx.Response(200, json={"result": "duplicate torrent"}))
        health = await client.test_connection()
    assert health.ok is False
    assert "duplicate" in (health.message or "")
    await client.close()
