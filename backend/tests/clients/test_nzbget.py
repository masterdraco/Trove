from __future__ import annotations

import json

import httpx
import pytest
import respx

from trove.clients.base import AddOptions, Protocol, Release
from trove.clients.nzbget import NzbgetClient

BASE = "http://nzbget.test:6789"
RPC = f"{BASE}/jsonrpc"


def _responder(handlers):  # type: ignore[no-untyped-def]
    def _inner(request):  # type: ignore[no-untyped-def]
        body = json.loads(request.content.decode("utf-8"))
        method = body["method"]
        result = handlers[method](body.get("params") or [])
        return httpx.Response(200, json={"result": result, "version": "1.1"})

    return _inner


@pytest.mark.asyncio
async def test_version_roundtrip() -> None:
    client = NzbgetClient(BASE, username="nzbget", password="tegbzn6789")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(RPC).mock(side_effect=_responder({"version": lambda params: "21.1"}))
        health = await client.test_connection()
    assert health.ok is True
    assert health.version == "21.1"
    await client.close()


@pytest.mark.asyncio
async def test_append_returns_id() -> None:
    import base64

    client = NzbgetClient(BASE, username="u", password="p")
    captured: list[object] = []

    def handle_append(params):  # type: ignore[no-untyped-def]
        captured.extend(params)
        return 42

    nzb_bytes = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"></nzb>'
    release = Release(
        title="Foo.S01",
        protocol=Protocol.USENET,
        download_url="https://indexer.test/nzb/foo",
    )
    options = AddOptions(category="tv", priority=10)
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://indexer.test/nzb/foo").mock(
            return_value=httpx.Response(200, content=nzb_bytes)
        )
        mock.post(RPC).mock(side_effect=_responder({"append": handle_append}))
        result = await client.add_nzb(release, options)
    assert result.ok is True
    assert result.identifier == "42"
    assert captured[1] == base64.b64encode(nzb_bytes).decode("ascii")
    assert captured[2] == "tv"  # category
    assert captured[3] == 10  # priority
    await client.close()


@pytest.mark.asyncio
async def test_rejects_html_response() -> None:
    from trove.clients.base import ClientError

    client = NzbgetClient(BASE, username="u", password="p")
    release = Release(
        title="Foo.S01",
        protocol=Protocol.USENET,
        download_url="https://indexer.test/nzb/foo",
    )
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://indexer.test/nzb/foo").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>API limit reached</body></html>",
                headers={"content-type": "text/html"},
            )
        )
        with pytest.raises(ClientError, match="not return an nzb"):
            await client.add_nzb(release, AddOptions())
    await client.close()


@pytest.mark.asyncio
async def test_accepts_gzipped_nzb() -> None:
    import gzip

    client = NzbgetClient(BASE, username="u", password="p")
    nzb_bytes = b'<?xml version="1.0"?><nzb></nzb>'
    gz = gzip.compress(nzb_bytes)
    release = Release(
        title="Foo.S01",
        protocol=Protocol.USENET,
        download_url="https://indexer.test/nzb/foo.nzb.gz",
    )
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://indexer.test/nzb/foo.nzb.gz").mock(
            return_value=httpx.Response(200, content=gz)
        )
        mock.post(RPC).mock(side_effect=_responder({"append": lambda params: 7}))
        result = await client.add_nzb(release, AddOptions())
    assert result.ok is True
    await client.close()


@pytest.mark.asyncio
async def test_401_is_auth_error() -> None:
    client = NzbgetClient(BASE, username="u", password="bad")
    with respx.mock(assert_all_called=True) as mock:
        mock.post(RPC).mock(return_value=httpx.Response(401, text="unauthorized"))
        health = await client.test_connection()
    assert health.ok is False
    assert "authentication" in (health.message or "")
    await client.close()
