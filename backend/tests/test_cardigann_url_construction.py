"""Regression: search URL construction must join base_url + path correctly
even when the expanded template path has no leading slash. Otherwise the
path fuses into the hostname via naive string concatenation and DNS
resolution fails for every search."""

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


def _driver_with_search_path(path: str, base_url: str) -> CardigannIndexer:
    definition = CardigannDefinition(
        site="t",
        name="t",
        links=[base_url],
        search_path=path,
        search_params={},
        rows_selector="tr",
        fields={"title": FieldSpec(selector="td")},
    )
    return CardigannIndexer(definition, base_url=base_url)


@pytest.mark.asyncio
async def test_search_path_without_leading_slash_is_normalized() -> None:
    drv = _driver_with_search_path(
        "search/all/{{ .Keywords }}/1/",
        "https://limetorrents.example",
    )
    with respx.mock(assert_all_called=True) as mock:
        expected = mock.get("https://limetorrents.example/search/all/ubuntu/1/").mock(
            return_value=httpx.Response(200, text="<table><tr><td>x</td></tr></table>")
        )
        await drv.search(SearchQuery(terms="ubuntu"))
    assert expected.called
    await drv.close()


@pytest.mark.asyncio
async def test_search_path_with_leading_slash_is_unchanged() -> None:
    drv = _driver_with_search_path("/", "https://nyaa.example")
    with respx.mock(assert_all_called=True) as mock:
        expected = mock.get("https://nyaa.example/").mock(
            return_value=httpx.Response(200, text="<table></table>")
        )
        await drv.search(SearchQuery(terms="ubuntu"))
    assert expected.called
    await drv.close()


@pytest.mark.asyncio
async def test_absolute_url_path_is_passed_through() -> None:
    drv = _driver_with_search_path(
        "https://other-host.example/api?q={{ .Keywords }}",
        "https://base.example",
    )
    with respx.mock(assert_all_called=True) as mock:
        expected = mock.get("https://other-host.example/api?q=ubuntu").mock(
            return_value=httpx.Response(200, text="<table></table>")
        )
        await drv.search(SearchQuery(terms="ubuntu"))
    assert expected.called
    await drv.close()
