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
