"""Parse-each-fixture smoke test.

For every slug in the catalog that has a corresponding
`tests/fixtures/catalog/<slug>-search.html` file, this test:
    - loads the vendored YAML
    - runs the Cardigann row extractor against the fixture
    - asserts at least one release with a non-empty title

Missing fixtures are silently skipped — run `pytest -vv` to see which
slugs are covered. Capturing real HTML fixtures is a one-time manual
task per site; tests pass until a fixture is captured AND its extraction
breaks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from trove.indexers.cardigann import CardigannIndexer, load_definition_yaml
from trove.services import catalog

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "catalog"


def _covered_slugs() -> list[str]:
    catalog.reset_cache_for_tests()
    return [
        e.slug for e in catalog.list_entries() if (FIXTURE_DIR / f"{e.slug}-search.html").exists()
    ]


@pytest.mark.parametrize("slug", _covered_slugs())
def test_fixture_extracts_at_least_one_release(slug: str) -> None:
    entry = catalog.get_entry(slug)
    definition = load_definition_yaml(catalog.read_yaml(slug))
    definition.name = slug
    driver = CardigannIndexer(definition, base_url=entry.default_mirror)

    html = (FIXTURE_DIR / f"{slug}-search.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(definition.rows_selector)
    assert rows, f"{slug}: rows_selector {definition.rows_selector!r} matched no elements"

    extracted = [driver._extract_release(r) for r in rows]
    extracted = [r for r in extracted if r is not None]
    assert extracted, f"{slug}: 0 releases extracted from {len(rows)} row(s)"
    assert extracted[0].title, f"{slug}: first release has empty title"
