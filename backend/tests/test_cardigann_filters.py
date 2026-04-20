from __future__ import annotations

from bs4 import BeautifulSoup

from trove.indexers.cardigann import (
    CardigannDefinition,
    CardigannIndexer,
    FieldSpec,
)


def _driver_with_field(name: str, filters: list[dict]) -> CardigannIndexer:
    definition = CardigannDefinition(
        site="test",
        name="test",
        links=["https://test.local"],
        search_path="/",
        search_params={},
        rows_selector="tr",
        fields={name: FieldSpec(selector="td", filters=filters)},
    )
    return CardigannIndexer(definition)


def _apply(driver: CardigannIndexer, html: str, field: str) -> str | None:
    row = BeautifulSoup(html, "lxml").find("tr")
    return driver._extract_field(row, field)


def test_urldecode() -> None:
    drv = _driver_with_field("title", [{"name": "urldecode"}])
    assert _apply(drv, "<tr><td>Hello%20World</td></tr>", "title") == "Hello World"


def test_split_by_delimiter_index() -> None:
    drv = _driver_with_field(
        "size",
        [{"name": "split", "args": ["|", 1]}],
    )
    result = _apply(drv, "<tr><td>1.2 GB | 42 seeders | 3 leechers</td></tr>", "size")
    assert result is not None
    assert result.strip() == "42 seeders"


def test_split_negative_index_returns_last() -> None:
    drv = _driver_with_field(
        "size",
        [{"name": "split", "args": ["|", -1]}],
    )
    assert _apply(drv, "<tr><td>a|b|c</td></tr>", "size") == "c"
