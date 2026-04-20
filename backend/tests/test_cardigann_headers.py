"""Verify CardigannIndexer sends a realistic browser User-Agent so sites
that trivially block the default httpx UA (python-httpx/x.y.z) don't 403
every request."""

from __future__ import annotations

import httpx
import pytest
import respx

from trove.indexers.base import SearchQuery
from trove.indexers.cardigann import (
    CardigannDefinition,
    CardigannIndexer,
    FieldSpec,
)


def _driver() -> CardigannIndexer:
    definition = CardigannDefinition(
        site="t",
        name="t",
        links=["https://t.example"],
        search_path="/",
        search_params={},
        rows_selector="tr",
        fields={"title": FieldSpec(selector="td")},
    )
    return CardigannIndexer(definition, base_url="https://t.example")


@pytest.mark.asyncio
async def test_search_sends_browser_user_agent() -> None:
    drv = _driver()
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://t.example/").mock(
            return_value=httpx.Response(200, text="<table></table>")
        )
        await drv.search(SearchQuery(terms=""))
    headers = route.calls.last.request.headers
    ua = headers.get("user-agent", "")
    assert "Mozilla/5.0" in ua, f"expected browser-like UA, got: {ua!r}"
    assert "httpx" not in ua.lower()
    # Common accept headers also help defeat trivial bot blocks.
    assert "text/html" in headers.get("accept", "")
    assert headers.get("accept-language", "").startswith("en")
    await drv.close()


@pytest.mark.asyncio
async def test_test_connection_sends_browser_user_agent() -> None:
    drv = _driver()
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://t.example").mock(return_value=httpx.Response(200, text=""))
        await drv.test_connection()
    ua = route.calls.last.request.headers.get("user-agent", "")
    assert "Mozilla/5.0" in ua
    await drv.close()
