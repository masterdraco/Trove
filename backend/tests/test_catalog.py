from __future__ import annotations

from pathlib import Path

import pytest

from trove.services import catalog

CATALOG_DIR = Path(catalog.__file__).parent.parent / "indexers" / "catalog"


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    catalog.reset_cache_for_tests()


def test_registry_loads() -> None:
    entries = catalog.list_entries()
    assert len(entries) >= 12
    slugs = {e.slug for e in entries}
    for required in ("thepiratebay", "1337x", "nyaa", "eztv", "yts"):
        assert required in slugs, f"missing catalog entry: {required}"


def test_default_mirror_is_in_mirrors() -> None:
    for entry in catalog.list_entries():
        assert entry.default_mirror in entry.mirrors, (
            f"{entry.slug}: default_mirror {entry.default_mirror!r} "
            f"not present in mirrors {entry.mirrors}"
        )


def test_every_entry_has_a_vendored_yaml_file() -> None:
    missing: list[str] = []
    for entry in catalog.list_entries():
        path = CATALOG_DIR / entry.yaml_file
        if not path.exists():
            missing.append(f"{entry.slug} -> {entry.yaml_file}")
    assert not missing, "missing vendored YAML files: " + ", ".join(missing)


def test_every_vendored_yaml_parses() -> None:
    from trove.indexers.cardigann import load_definition_yaml

    failures: list[str] = []
    for entry in catalog.list_entries():
        try:
            load_definition_yaml(catalog.read_yaml(entry.slug))
        except Exception as e:
            failures.append(f"{entry.slug}: {type(e).__name__}: {e}")
    assert not failures, "YAMLs failed to parse:\n  " + "\n  ".join(failures)
