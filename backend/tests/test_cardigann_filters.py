from __future__ import annotations

import re

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


def test_trim_with_no_args_strips_whitespace() -> None:
    drv = _driver_with_field(
        "title",
        [{"name": "split", "args": ["|", 0]}, {"name": "trim"}],
    )
    assert _apply(drv, "<tr><td>  hello  | world</td></tr>", "title") == "hello"


def test_trim_with_args_strips_specific_chars() -> None:
    drv = _driver_with_field(
        "title",
        [{"name": "split", "args": [" | ", 0]}, {"name": "trim", "args": "/"}],
    )
    assert _apply(drv, "<tr><td>/path/to/thing/ | rest</td></tr>", "title") == "path/to/thing"


def test_tolower() -> None:
    drv = _driver_with_field("title", [{"name": "tolower"}])
    assert _apply(drv, "<tr><td>Hello WORLD</td></tr>", "title") == "hello world"


def test_re_replace() -> None:
    # Replace sequences of whitespace with a single dash.
    drv = _driver_with_field(
        "title",
        [{"name": "re_replace", "args": [r"\s+", "-"]}],
    )
    assert _apply(drv, "<tr><td>Big Buck  Bunny</td></tr>", "title") == "Big-Buck-Bunny"


def test_re_replace_removes_matches_with_empty_replacement() -> None:
    drv = _driver_with_field(
        "title",
        [{"name": "re_replace", "args": [r"\d+", ""]}],
    )
    assert _apply(drv, "<tr><td>abc123def456</td></tr>", "title") == "abcdef"


def test_unknown_filter_logs_warning(caplog) -> None:
    import logging

    drv = _driver_with_field(
        "title",
        [{"name": "definitelynotarealfilter"}],
    )
    with caplog.at_level(logging.WARNING):
        result = _apply(drv, "<tr><td>hello</td></tr>", "title")
    assert result == "hello"
    assert any(
        "definitelynotarealfilter" in rec.message for rec in caplog.records
    ), "expected a warning mentioning the unknown filter name"


def test_unknown_filter_logs_once_per_process(caplog) -> None:
    import logging

    drv = _driver_with_field(
        "title",
        [{"name": "another-fake-filter"}],
    )
    with caplog.at_level(logging.WARNING):
        _apply(drv, "<tr><td>1</td></tr>", "title")
        _apply(drv, "<tr><td>2</td></tr>", "title")
        _apply(drv, "<tr><td>3</td></tr>", "title")
    count = sum(1 for rec in caplog.records if "another-fake-filter" in rec.message)
    assert count == 1, f"expected exactly one warning, got {count}"
