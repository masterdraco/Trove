from __future__ import annotations

import httpx
import pytest
import respx

from trove.clients.base import AddOptions, Protocol, Release
from trove.clients.sabnzbd import SabnzbdClient

BASE = "http://sab.test:8080"
API = f"{BASE}/api"


@pytest.mark.asyncio
async def test_test_connection_reads_version() -> None:
    client = SabnzbdClient(BASE, api_key="k")
    with respx.mock(assert_all_called=True) as mock:
        mock.get(API).mock(return_value=httpx.Response(200, json={"version": "4.3.1"}))
        health = await client.test_connection()
    assert health.ok is True
    assert health.version == "4.3.1"
    await client.close()


@pytest.mark.asyncio
async def test_list_categories_filters_star() -> None:
    client = SabnzbdClient(BASE, api_key="k")
    with respx.mock(assert_all_called=True) as mock:
        mock.get(API).mock(
            return_value=httpx.Response(200, json={"categories": ["*", "tv", "movies", "music"]})
        )
        cats = await client.list_categories()
    assert cats == ["tv", "movies", "music"]
    await client.close()


@pytest.mark.asyncio
async def test_add_nzb_via_url_uses_addurl_mode() -> None:
    client = SabnzbdClient(BASE, api_key="k")
    release = Release(
        title="Some.Show.S01E01",
        protocol=Protocol.USENET,
        download_url="https://indexer.test/getnzb/abc",
    )
    options = AddOptions(category="tv")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(API).mock(
            return_value=httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_1"]})
        )
        result = await client.add_nzb(release, options)
        called_url = str(route.calls[0].request.url)
    assert result.ok is True
    assert result.identifier == "SABnzbd_1"
    assert "mode=addurl" in called_url
    assert "cat=tv" in called_url
    await client.close()


@pytest.mark.asyncio
async def test_api_error_reports_failure() -> None:
    client = SabnzbdClient(BASE, api_key="bad")
    with respx.mock(assert_all_called=True) as mock:
        mock.get(API).mock(
            return_value=httpx.Response(200, json={"status": False, "error": "API Key Incorrect"})
        )
        health = await client.test_connection()
    assert health.ok is False
    assert "API Key" in (health.message or "")
    await client.close()
