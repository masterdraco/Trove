# Public Torrent Site Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a curated, built-in catalog of 12 public (no-account) torrent sites installable with one click from a dedicated `/indexers/catalog` page and as an optional step in the onboarding wizard.

**Architecture:** A new `backend/src/trove/indexers/catalog/` directory holds a hand-written `registry.yaml` plus twelve vendored Cardigann `.yml` definitions. A new `services/catalog.py` module exposes the catalog, and two new endpoints (`GET /api/indexers/catalog`, `POST /api/indexers/catalog/{slug}`) create ordinary `type=cardigann` indexer rows — the only storage change is a nullable `catalog_slug` marker column. The existing Cardigann parser is extended with a handful of new filter types (driven by what the vendored YAMLs actually use).

**Tech Stack:** Python 3.12, FastAPI, SQLModel, Alembic, httpx, PyYAML, BeautifulSoup4/lxml; SvelteKit 5 + TypeScript; pytest + respx for tests.

**Spec:** `docs/superpowers/specs/2026-04-20-public-torrent-site-catalog-design.md`

---

## File Structure

**New files:**

- `backend/migrations/versions/0016_indexer_catalog_slug.py` — Alembic migration adding the column
- `backend/src/trove/indexers/catalog/__init__.py` — empty marker
- `backend/src/trove/indexers/catalog/registry.yaml` — curated metadata (authoritative)
- `backend/src/trove/indexers/catalog/*.yml` — 12 vendored Prowlarr definitions (downloaded via script)
- `backend/src/trove/services/catalog.py` — registry loader + YAML reader
- `backend/src/trove/api/catalog.py` — new router with two endpoints (lives next to `indexers.py`, mounted under the same prefix)
- `backend/tests/test_catalog.py` — registry integrity + per-YAML parse tests
- `backend/tests/test_cardigann_filters.py` — unit tests for new parser filters
- `backend/tests/api/test_catalog_api.py` — endpoint tests
- `backend/tests/fixtures/catalog/` — captured HTML responses, one per site
- `scripts/update-catalog.py` — downloads/diffs vendored YAMLs against upstream
- `web/src/routes/indexers/catalog/+page.svelte` — tile-grid catalog page

**Modified files:**

- `backend/src/trove/models/indexer.py` — add `catalog_slug` field to `IndexerRow`
- `backend/src/trove/indexers/cardigann.py` — extend `_apply_filter` with new filter types and an unknown-filter warn log
- `backend/src/trove/main.py` — mount the new catalog router
- `web/src/lib/api.ts` — add `CatalogEntryOut` type + `api.indexers.catalog.*` methods
- `web/src/routes/indexers/+page.svelte` — add "Browse catalog" button
- `web/src/routes/onboarding/+page.svelte` — insert a new "Public torrent sites" step
- `backend/src/trove/docs/03-indexers.md` — document the catalog

---

## Task 1: Add `catalog_slug` column to `IndexerRow` model

**Files:**
- Modify: `backend/src/trove/models/indexer.py:12-27`

- [ ] **Step 1: Add the field**

Edit `backend/src/trove/models/indexer.py` — add one line inside the `IndexerRow` class, directly after `last_test_message`:

```python
    catalog_slug: str | None = Field(default=None, max_length=64, index=True)
```

- [ ] **Step 2: Verify model import still works**

Run: `cd backend && uv run python -c "from trove.models.indexer import IndexerRow; print(IndexerRow.__fields__.keys())"`
Expected: the printed list includes `catalog_slug`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/trove/models/indexer.py
git commit -m "feat: add catalog_slug field to IndexerRow"
```

---

## Task 2: Alembic migration for the new column

**Files:**
- Create: `backend/migrations/versions/0016_indexer_catalog_slug.py`

- [ ] **Step 1: Write the migration**

Create `backend/migrations/versions/0016_indexer_catalog_slug.py`:

```python
"""indexer.catalog_slug column

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-20

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("indexer") as batch:
        batch.add_column(
            sa.Column(
                "catalog_slug",
                sqlmodel.sql.sqltypes.AutoString(length=64),
                nullable=True,
            )
        )
    op.create_index(
        "ix_indexer_catalog_slug", "indexer", ["catalog_slug"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_indexer_catalog_slug", table_name="indexer")
    with op.batch_alter_table("indexer") as batch:
        batch.drop_column("catalog_slug")
```

`op.batch_alter_table` is required on SQLite because ALTER is restricted; Trove uses SQLite in WAL mode.

- [ ] **Step 2: Apply migration against a scratch DB**

Run: `cd backend && rm -f /tmp/trove-mig-test.db && TROVE_CONFIG_DIR=/tmp/trove-mig-test uv run alembic upgrade head`
Expected: last line `INFO  [alembic.runtime.migration] Running upgrade 0015 -> 0016, indexer.catalog_slug column`.

- [ ] **Step 3: Roll it back, then forward again**

Run: `cd backend && TROVE_CONFIG_DIR=/tmp/trove-mig-test uv run alembic downgrade 0015 && TROVE_CONFIG_DIR=/tmp/trove-mig-test uv run alembic upgrade head`
Expected: both steps complete without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/versions/0016_indexer_catalog_slug.py
git commit -m "feat: migration adds indexer.catalog_slug column"
```

---

## Task 3: Write `registry.yaml`

**Files:**
- Create: `backend/src/trove/indexers/catalog/__init__.py`
- Create: `backend/src/trove/indexers/catalog/registry.yaml`

- [ ] **Step 1: Create the package marker**

Create `backend/src/trove/indexers/catalog/__init__.py` as an empty file:

```python
```

- [ ] **Step 2: Write the registry**

Create `backend/src/trove/indexers/catalog/registry.yaml`:

```yaml
# Authoritative index of public no-account torrent sites shipped with Trove.
# Each entry references a vendored Cardigann YAML in the same directory.
#
# Filenames under `yaml_file:` are OUR vendored filenames — they need not
# match upstream. `upstream_path:` records where the definition came from
# so scripts/update-catalog.py can diff against Prowlarr-indexers.

entries:
  - slug: thepiratebay
    display_name: The Pirate Bay
    description: General-purpose public torrent tracker, no account required.
    categories: [movies, tv, music, software, games, books, other]
    yaml_file: thepiratebay.yml
    upstream_path: definitions/v11/thepiratebay.yml
    mirrors:
      - https://thepiratebay.org
      - https://tpb.party
      - https://piratebay.live
    default_mirror: https://thepiratebay.org
    protocol: torrent

  - slug: 1337x
    display_name: 1337x
    description: Large public general-purpose tracker with strong TV/movie scene coverage.
    categories: [movies, tv, music, software, games, books, anime]
    yaml_file: 1337x.yml
    upstream_path: definitions/v11/1337x.yml
    mirrors:
      - https://1337x.to
      - https://1337x.st
      - https://1337x.tw
    default_mirror: https://1337x.to
    protocol: torrent

  - slug: torrentgalaxy
    display_name: TorrentGalaxy
    description: General-purpose public tracker with reliable scene releases and good category filtering.
    categories: [movies, tv, music, software, games, books, anime, other]
    yaml_file: torrentgalaxy.yml
    upstream_path: definitions/v11/torrentgalaxy.yml
    mirrors:
      - https://torrentgalaxy.to
      - https://tgx.rs
    default_mirror: https://torrentgalaxy.to
    protocol: torrent

  - slug: limetorrents
    display_name: LimeTorrents
    description: Long-running public aggregator with a wide catalogue.
    categories: [movies, tv, music, software, games, anime, other]
    yaml_file: limetorrents.yml
    upstream_path: definitions/v11/limetorrents.yml
    mirrors:
      - https://www.limetorrents.lol
      - https://www.limetorrents.info
    default_mirror: https://www.limetorrents.lol
    protocol: torrent

  - slug: magnetdl
    display_name: MagnetDL
    description: Magnet-link aggregator, fast and light.
    categories: [movies, tv, music, software, games, books, anime]
    yaml_file: magnetdl.yml
    upstream_path: definitions/v11/magnetdl.yml
    mirrors:
      - https://www.magnetdl.com
    default_mirror: https://www.magnetdl.com
    protocol: torrent

  - slug: torlock
    display_name: Torlock
    description: General-purpose tracker focused on verified torrents.
    categories: [movies, tv, music, software, games, books, anime]
    yaml_file: torlock.yml
    upstream_path: definitions/v11/torlock.yml
    mirrors:
      - https://www.torlock.com
    default_mirror: https://www.torlock.com
    protocol: torrent

  - slug: bitsearch
    display_name: BitSearch
    description: Aggregator that searches across multiple public sites.
    categories: [movies, tv, music, software, games, books, anime, other]
    yaml_file: bitsearch.yml
    upstream_path: definitions/v11/bitsearch.yml
    mirrors:
      - https://bitsearch.to
    default_mirror: https://bitsearch.to
    protocol: torrent

  - slug: solidtorrents
    display_name: SolidTorrents
    description: Multi-source torrent search aggregator.
    categories: [movies, tv, music, software, games, books, anime, other]
    yaml_file: solidtorrents.yml
    upstream_path: definitions/v11/solidtorrents.yml
    mirrors:
      - https://solidtorrents.to
    default_mirror: https://solidtorrents.to
    protocol: torrent

  - slug: nyaa
    display_name: Nyaa
    description: The largest public anime & manga tracker.
    categories: [anime, music, books, other]
    yaml_file: nyaa.yml
    upstream_path: definitions/v11/nyaasi.yml
    mirrors:
      - https://nyaa.si
    default_mirror: https://nyaa.si
    protocol: torrent

  - slug: eztv
    display_name: EZTV
    description: TV-focused public tracker with strong scene release coverage.
    categories: [tv]
    yaml_file: eztv.yml
    upstream_path: definitions/v11/eztv.yml
    mirrors:
      - https://eztv.re
      - https://eztvx.to
    default_mirror: https://eztv.re
    protocol: torrent

  - slug: yts
    display_name: YTS
    description: Public tracker specializing in small-size movie encodes.
    categories: [movies]
    yaml_file: yts.yml
    upstream_path: definitions/v11/yts.yml
    mirrors:
      - https://yts.mx
    default_mirror: https://yts.mx
    protocol: torrent

  - slug: animetosho
    display_name: AnimeTosho
    description: Anime mirror and long-term archive of Nyaa + Tokyo Toshokan.
    categories: [anime]
    yaml_file: animetosho.yml
    upstream_path: definitions/v11/animetosho.yml
    mirrors:
      - https://animetosho.org
    default_mirror: https://animetosho.org
    protocol: torrent
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/trove/indexers/catalog/__init__.py backend/src/trove/indexers/catalog/registry.yaml
git commit -m "feat: add catalog registry for 12 public torrent sites"
```

---

## Task 4: Write `services/catalog.py`

**Files:**
- Create: `backend/src/trove/services/catalog.py`

- [ ] **Step 1: Write the module**

Create `backend/src/trove/services/catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from trove.clients.base import Protocol
from trove.indexers.base import Category

_CATALOG_DIR = Path(__file__).parent.parent / "indexers" / "catalog"


class CatalogError(Exception):
    """Raised when the shipped catalog is malformed. This is always our bug,
    never user input — the registry is vendored code."""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    slug: str
    display_name: str
    description: str
    categories: list[Category]
    yaml_file: str
    upstream_path: str
    mirrors: list[str]
    default_mirror: str
    protocol: Protocol
    logo: str | None = None


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, CatalogEntry]:
    registry_path = _CATALOG_DIR / "registry.yaml"
    if not registry_path.exists():
        raise CatalogError(f"catalog registry missing at {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries_raw = raw.get("entries") or []
    if not isinstance(entries_raw, list):
        raise CatalogError("registry.yaml: `entries` must be a list")

    by_slug: dict[str, CatalogEntry] = {}
    for row in entries_raw:
        if not isinstance(row, dict):
            raise CatalogError("registry.yaml: each entry must be a mapping")
        slug = row.get("slug")
        if not slug or not isinstance(slug, str):
            raise CatalogError("registry.yaml: entry missing `slug`")
        if slug in by_slug:
            raise CatalogError(f"registry.yaml: duplicate slug {slug!r}")

        try:
            categories = [Category(c) for c in row.get("categories") or []]
        except ValueError as e:
            raise CatalogError(f"registry.yaml: {slug}: unknown category {e}") from e
        try:
            protocol = Protocol(row.get("protocol") or "torrent")
        except ValueError as e:
            raise CatalogError(f"registry.yaml: {slug}: unknown protocol {e}") from e

        mirrors = list(row.get("mirrors") or [])
        default_mirror = row.get("default_mirror") or ""
        if not mirrors:
            raise CatalogError(f"registry.yaml: {slug}: at least one mirror required")
        if default_mirror not in mirrors:
            raise CatalogError(
                f"registry.yaml: {slug}: default_mirror must be a member of mirrors"
            )

        by_slug[slug] = CatalogEntry(
            slug=slug,
            display_name=str(row.get("display_name") or slug),
            description=str(row.get("description") or ""),
            categories=categories,
            yaml_file=str(row.get("yaml_file") or f"{slug}.yml"),
            upstream_path=str(row.get("upstream_path") or ""),
            mirrors=mirrors,
            default_mirror=default_mirror,
            protocol=protocol,
            logo=row.get("logo"),
        )

    return by_slug


def list_entries() -> list[CatalogEntry]:
    return list(load_catalog().values())


def get_entry(slug: str) -> CatalogEntry:
    entries = load_catalog()
    if slug not in entries:
        raise KeyError(slug)
    return entries[slug]


def read_yaml(slug: str) -> str:
    entry = get_entry(slug)
    path = _CATALOG_DIR / entry.yaml_file
    if not path.exists():
        raise CatalogError(f"catalog: {slug}: missing yaml file at {path}")
    return path.read_text(encoding="utf-8")


def reset_cache_for_tests() -> None:
    """pytest hook — the module-level cache would otherwise outlive test DBs."""
    load_catalog.cache_clear()
```

- [ ] **Step 2: Sanity-load**

Run: `cd backend && uv run python -c "from trove.services import catalog; print(len(catalog.list_entries()))"`
Expected: `12`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/trove/services/catalog.py
git commit -m "feat: catalog service loads registry + vendored YAMLs"
```

---

## Task 5: Catalog integrity test (pre-vendoring)

**Files:**
- Create: `backend/tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_catalog.py`:

```python
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
        except Exception as e:  # noqa: BLE001
            failures.append(f"{entry.slug}: {type(e).__name__}: {e}")
    assert not failures, "YAMLs failed to parse:\n  " + "\n  ".join(failures)
```

- [ ] **Step 2: Run — expect failure on vendored-files test**

Run: `cd backend && uv run pytest tests/test_catalog.py -v`
Expected: `test_registry_loads` and `test_default_mirror_is_in_mirrors` PASS. `test_every_entry_has_a_vendored_yaml_file` and `test_every_vendored_yaml_parses` FAIL with "missing vendored YAML files".

This is the correct state before vendoring — don't fix yet.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_catalog.py
git commit -m "test: catalog integrity checks (pre-vendor, expected to fail)"
```

---

## Task 6: Write `scripts/update-catalog.py`

**Files:**
- Create: `scripts/update-catalog.py`

- [ ] **Step 1: Write the script**

Create `scripts/update-catalog.py`:

```python
#!/usr/bin/env python3
"""Vendor or diff Cardigann YAML definitions from Prowlarr-indexers.

Usage:
    scripts/update-catalog.py sync    # download + overwrite vendored files
    scripts/update-catalog.py diff    # print per-file status, no writes

The canonical upstream is Prowlarr/Prowlarr-indexers @ master. Slug→path
mapping lives in backend/src/trove/indexers/catalog/registry.yaml.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import httpx
import yaml

REPO_ROOT = Path(__file__).parent.parent
CATALOG_DIR = REPO_ROOT / "backend" / "src" / "trove" / "indexers" / "catalog"
REGISTRY_PATH = CATALOG_DIR / "registry.yaml"
UPSTREAM_RAW = "https://raw.githubusercontent.com/Prowlarr/Prowlarr-indexers/master/"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_registry() -> list[dict[str, str]]:
    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    entries = raw.get("entries") or []
    out: list[dict[str, str]] = []
    for row in entries:
        upstream = row.get("upstream_path")
        if not upstream:
            continue
        out.append(
            {
                "slug": row["slug"],
                "yaml_file": row["yaml_file"],
                "upstream_path": upstream,
            }
        )
    return out


def _fetch(client: httpx.Client, upstream_path: str) -> bytes | None:
    url = UPSTREAM_RAW + upstream_path
    resp = client.get(url, timeout=30.0)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


def run(mode: str) -> int:
    entries = _load_registry()
    with httpx.Client(follow_redirects=True) as client:
        changes = 0
        missing = 0
        for entry in entries:
            slug = entry["slug"]
            local_path = CATALOG_DIR / entry["yaml_file"]
            upstream_bytes = _fetch(client, entry["upstream_path"])
            if upstream_bytes is None:
                print(f"  [MISSING] {slug}: upstream {entry['upstream_path']} not found")
                missing += 1
                continue

            local_hash = _sha256(local_path.read_bytes()) if local_path.exists() else None
            upstream_hash = _sha256(upstream_bytes)

            if local_hash == upstream_hash:
                print(f"  [unchanged] {slug}")
                continue

            changes += 1
            if mode == "sync":
                local_path.write_bytes(upstream_bytes)
                state = "created" if local_hash is None else "updated"
                print(f"  [{state}] {slug}")
            else:
                state = "missing locally" if local_hash is None else "upstream changed"
                print(f"  [{state}] {slug}")

        print(f"\n{changes} change(s), {missing} missing upstream")
        return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["sync", "diff"])
    args = parser.parse_args()
    return run(args.mode)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Mark executable**

Run: `chmod +x scripts/update-catalog.py`

- [ ] **Step 3: Commit**

```bash
git add scripts/update-catalog.py
git commit -m "feat: script to sync/diff vendored catalog YAMLs with upstream"
```

---

## Task 7: Run `update-catalog.py sync` to vendor the 12 YAMLs

**Files:**
- Create: `backend/src/trove/indexers/catalog/thepiratebay.yml` (and 11 others)

- [ ] **Step 1: Run the script**

Run: `cd /home/masterdraco/trove && ./scripts/update-catalog.py sync`
Expected: 12 `[created]` lines, `12 change(s), 0 missing upstream`.

If any entry reports `[MISSING]`, the `upstream_path` in `registry.yaml` is wrong for that slug — look on GitHub under `Prowlarr/Prowlarr-indexers/tree/master/definitions` for the correct filename (it may live under `v10` instead of `v11`, or have a slightly different spelling), fix `registry.yaml`, re-run.

- [ ] **Step 2: Spot-check one YAML**

Run: `head -40 backend/src/trove/indexers/catalog/thepiratebay.yml`
Expected: a Cardigann YAML document starting with `---` or `id:` / `name:` / `type:` fields.

- [ ] **Step 3: Commit the vendored files and any fixed upstream paths**

```bash
git add backend/src/trove/indexers/catalog/*.yml backend/src/trove/indexers/catalog/registry.yaml
git commit -m "vendor: import 12 Cardigann YAML definitions from Prowlarr-indexers"
```

---

## Task 8: Verify catalog parse test now passes (or surfaces missing filters)

**Files:**
- None (investigation only)

- [ ] **Step 1: Run catalog tests**

Run: `cd backend && uv run pytest tests/test_catalog.py -v`
Expected: all four tests PASS **if** the vendored YAMLs only use filters the existing parser understands.

If `test_every_vendored_yaml_parses` fails, read the error — `load_definition_yaml` raises `IndexerError` with descriptive messages for structural problems. Common failure modes:
- `has no search.paths` → upstream may have changed schema; fix in Task 15.
- `has no search.rows.selector` → same.

These structural issues are rare; most failures in this phase come from filter-parsing. The filter layer only emits warnings today, so Task 8 may pass even when unknown filters are present (silently returning the unfiltered value). Tasks 9–13 fix that.

- [ ] **Step 2: Scan the vendored files for filter names in use**

Run: `cd backend && uv run python -c "
import pathlib, re
from trove.services import catalog
wanted = set()
for e in catalog.list_entries():
    text = catalog.read_yaml(e.slug)
    for m in re.finditer(r'name:\s*(\w+)', text):
        wanted.add(m.group(1))
print(sorted(wanted))
"`
Expected: a sorted list. Note any unfamiliar names — cross-reference with Tasks 9–14 to see what's already covered.

Known-covered filters: `replace`, `regexp`, `append`, `prepend`.
Tasks 9–13 cover: `urldecode`, `urlencode`, `split`, `trim`, `querystring`.
Anything *else* in the list is an additional filter — write a TDD task for it using the template in Tasks 9–13 (failing test in `test_cardigann_filters.py` + one branch in `_apply_filter` + passing test + commit) and slot it in between Tasks 13 and 14.

No commit — this step is investigation.

---

## Task 9: Add `urldecode` / `urlencode` filters to Cardigann parser

**Files:**
- Create: `backend/tests/test_cardigann_filters.py`
- Modify: `backend/src/trove/indexers/cardigann.py:256-270`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_cardigann_filters.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup

from trove.indexers.cardigann import (
    CardigannDefinition,
    CardigannIndexer,
    FieldSpec,
    load_definition_yaml,
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


def test_urlencode() -> None:
    drv = _driver_with_field("title", [{"name": "urlencode"}])
    assert _apply(drv, "<tr><td>Hello World</td></tr>", "title") == "Hello%20World"
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v`
Expected: `test_urldecode` PASSES unexpectedly (fallthrough returns value unchanged, which happens to equal the literal input for `urldecode` only when there's nothing to decode — but our input contains `%20`, so it should FAIL). `test_urlencode` FAILS — fallthrough returns unchanged.

If both PASS because the fallthrough returns value unchanged and your inputs happen to match, that's still the wrong behavior: the filters are supposed to transform. Proceed to Step 3.

- [ ] **Step 3: Implement the filters**

Edit `backend/src/trove/indexers/cardigann.py` — extend `_apply_filter` (around line 256). Add these two branches **before** the final `return value`:

```python
        if name == "urldecode":
            from urllib.parse import unquote
            return unquote(value)
        if name == "urlencode":
            from urllib.parse import quote
            return quote(value, safe="")
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "urldecode or urlencode"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cardigann_filters.py backend/src/trove/indexers/cardigann.py
git commit -m "feat: cardigann urldecode/urlencode filters"
```

---

## Task 10: Add `split` filter

**Files:**
- Modify: `backend/tests/test_cardigann_filters.py`
- Modify: `backend/src/trove/indexers/cardigann.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_cardigann_filters.py`:

```python
def test_split_by_delimiter_index() -> None:
    drv = _driver_with_field(
        "size",
        [{"name": "split", "args": ["|", 1]}],
    )
    # "1.2 GB | 42 seeders | 3 leechers" -> split on '|', index 1 -> " 42 seeders "
    assert _apply(drv, "<tr><td>1.2 GB | 42 seeders | 3 leechers</td></tr>", "size").strip() == "42 seeders"


def test_split_negative_index_returns_last() -> None:
    drv = _driver_with_field(
        "size",
        [{"name": "split", "args": ["|", -1]}],
    )
    # index -1 -> last chunk
    assert _apply(drv, "<tr><td>a|b|c</td></tr>", "size") == "c"
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py::test_split_by_delimiter_index -v`
Expected: FAIL — returns the unsplit string.

- [ ] **Step 3: Implement**

Edit `backend/src/trove/indexers/cardigann.py` — add to `_apply_filter`, before the final `return value`:

```python
        if name == "split" and isinstance(args, list) and len(args) >= 2:
            delimiter = str(args[0])
            try:
                index = int(args[1])
            except (TypeError, ValueError):
                return value
            parts = value.split(delimiter)
            if not parts:
                return value
            try:
                return parts[index]
            except IndexError:
                return value
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "split"`
Expected: both split tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cardigann_filters.py backend/src/trove/indexers/cardigann.py
git commit -m "feat: cardigann split filter"
```

---

## Task 11: Add `trim` filter

**Files:**
- Modify: `backend/tests/test_cardigann_filters.py`
- Modify: `backend/src/trove/indexers/cardigann.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_cardigann_filters.py`:

```python
def test_trim() -> None:
    drv = _driver_with_field("title", [{"name": "trim"}])
    # get_text(" ", strip=True) strips leading/trailing whitespace already,
    # but real use is *after* another filter (e.g. split) has reintroduced whitespace.
    drv2 = _driver_with_field(
        "title",
        [{"name": "split", "args": ["|", 0]}, {"name": "trim"}],
    )
    assert _apply(drv2, "<tr><td>  hello  | world</td></tr>", "title") == "hello"


def test_trim_with_args_strips_specific_chars() -> None:
    drv = _driver_with_field("title", [{"name": "trim", "args": "/"}])
    # emulate "/path/to/thing/" -> "path/to/thing"
    drv2 = _driver_with_field(
        "title",
        [{"name": "split", "args": [" | ", 0]}, {"name": "trim", "args": "/"}],
    )
    assert _apply(drv2, "<tr><td>/path/to/thing/ | rest</td></tr>", "title") == "path/to/thing"
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "trim"`
Expected: FAIL — `test_trim` passes by accident (the text-extraction already strips), `test_trim_with_args_strips_specific_chars` FAILS.

- [ ] **Step 3: Implement**

Edit `backend/src/trove/indexers/cardigann.py`, add to `_apply_filter`:

```python
        if name == "trim":
            if isinstance(args, str) and args:
                return value.strip(args)
            return value.strip()
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "trim"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cardigann_filters.py backend/src/trove/indexers/cardigann.py
git commit -m "feat: cardigann trim filter"
```

---

## Task 12: Add `querystring` filter

**Files:**
- Modify: `backend/tests/test_cardigann_filters.py`
- Modify: `backend/src/trove/indexers/cardigann.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_querystring_extract_param() -> None:
    drv = _driver_with_field(
        "infohash",
        [{"name": "querystring", "args": "id"}],
    )
    assert _apply(
        drv,
        '<tr><td><a href="/download.php?id=abc123&cat=movies">link</a></td></tr>',
        "infohash",
    ) is None  # spec: driver extracts from text — this case pulls text of the cell, not href.


def test_querystring_on_href_value() -> None:
    drv = _driver_with_field(
        "infohash",
        [{"name": "querystring", "args": "id"}],
    )
    # When combined with attribute:"href", the filter receives the URL string.
    definition = CardigannDefinition(
        site="t",
        name="t",
        links=["https://t.local"],
        search_path="/",
        search_params={},
        rows_selector="tr",
        fields={
            "infohash": FieldSpec(
                selector="a",
                attribute="href",
                filters=[{"name": "querystring", "args": "id"}],
            )
        },
    )
    drv = CardigannIndexer(definition)
    row = BeautifulSoup(
        '<tr><td><a href="/download.php?id=abc123&cat=movies">link</a></td></tr>',
        "lxml",
    ).find("tr")
    assert drv._extract_field(row, "infohash") == "abc123"
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "querystring"`
Expected: `test_querystring_on_href_value` FAILS (returns the full URL unchanged).

- [ ] **Step 3: Implement**

Add to `_apply_filter`:

```python
        if name == "querystring" and isinstance(args, str):
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(value)
            params = parse_qs(parsed.query)
            picks = params.get(args)
            return picks[0] if picks else value
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py -v -k "querystring"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cardigann_filters.py backend/src/trove/indexers/cardigann.py
git commit -m "feat: cardigann querystring filter"
```

---

## Task 13: Warn once per process on unknown filter names

**Files:**
- Modify: `backend/src/trove/indexers/cardigann.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_cardigann_filters.py`:

```python
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
```

- [ ] **Step 2: Run — expect fail**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py::test_unknown_filter_logs_warning -v`
Expected: FAIL — no warning logged.

- [ ] **Step 3: Implement**

Edit `backend/src/trove/indexers/cardigann.py`. Near the top of the file, below the imports, add:

```python
import logging

log = logging.getLogger(__name__)
_WARNED_FILTERS: set[str] = set()
```

Modify the final `return value` at the end of `_apply_filter` to warn on unknown names:

```python
        if name and name not in _WARNED_FILTERS:
            _WARNED_FILTERS.add(name)
            log.warning("cardigann: unknown filter %r — passing value through unchanged", name)
        return value
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && uv run pytest tests/test_cardigann_filters.py::test_unknown_filter_logs_warning -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_cardigann_filters.py backend/src/trove/indexers/cardigann.py
git commit -m "feat: cardigann warns once per unknown filter name"
```

---

## Task 14: Add `CatalogEntryOut` Pydantic model

**Files:**
- Create: `backend/src/trove/api/catalog.py`

- [ ] **Step 1: Scaffold the router module**

Create `backend/src/trove/api/catalog.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.api.indexers import IndexerOut, _to_out
from trove.clients.base import Protocol
from trove.indexers.base import Category
from trove.indexers.cardigann import load_definition_yaml
from trove.models.indexer import IndexerRow
from trove.models.user import User
from trove.services import catalog, indexer_registry

router = APIRouter()


class CatalogEntryOut(BaseModel):
    slug: str
    display_name: str
    description: str
    categories: list[Category]
    mirrors: list[str]
    default_mirror: str
    protocol: Protocol
    logo: str | None = None
    already_installed: bool


class CatalogInstallRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=512)
    name: str | None = Field(default=None, max_length=64)


@router.get("", response_model=list[CatalogEntryOut])
async def list_catalog(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[CatalogEntryOut]:
    installed_slugs = set(
        session.exec(
            select(IndexerRow.catalog_slug).where(IndexerRow.catalog_slug.is_not(None))  # type: ignore[attr-defined]
        ).all()
    )
    out: list[CatalogEntryOut] = []
    for entry in catalog.list_entries():
        out.append(
            CatalogEntryOut(
                slug=entry.slug,
                display_name=entry.display_name,
                description=entry.description,
                categories=entry.categories,
                mirrors=entry.mirrors,
                default_mirror=entry.default_mirror,
                protocol=entry.protocol,
                logo=entry.logo,
                already_installed=entry.slug in installed_slugs,
            )
        )
    return out
```

- [ ] **Step 2: Import-check**

Run: `cd backend && uv run python -c "from trove.api import catalog; print(catalog.router.routes)"`
Expected: prints one `APIRoute` (the GET handler).

- [ ] **Step 3: Commit**

```bash
git add backend/src/trove/api/catalog.py
git commit -m "feat: scaffold catalog API router with GET /catalog"
```

---

## Task 15: Implement `POST /api/indexers/catalog/{slug}`

**Files:**
- Modify: `backend/src/trove/api/catalog.py`

- [ ] **Step 1: Add the endpoint**

Append to `backend/src/trove/api/catalog.py`, below the GET handler:

```python
def _dedup_name(session: Session, base: str) -> str:
    candidate = base
    suffix = 2
    while session.exec(select(IndexerRow).where(IndexerRow.name == candidate)).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@router.post("/{slug}", response_model=IndexerOut, status_code=status.HTTP_201_CREATED)
async def install_catalog_entry(
    slug: str,
    payload: CatalogInstallRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> IndexerOut:
    try:
        entry = catalog.get_entry(slug)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown_slug") from None

    if payload.base_url not in entry.mirrors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url_not_in_catalog_mirrors",
        )

    try:
        yaml_text = catalog.read_yaml(slug)
        load_definition_yaml(yaml_text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"catalog_yaml_broken: {e}",
        ) from e

    base_name = payload.name or entry.display_name
    name = _dedup_name(session, base_name)

    row = IndexerRow(
        name=name,
        type="cardigann",
        protocol=entry.protocol.value,
        base_url=payload.base_url,
        credentials_cipher=indexer_registry.encrypt_credentials({}),
        definition_yaml=yaml_text,
        enabled=True,
        priority=50,
        catalog_slug=slug,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)
```

- [ ] **Step 2: Mount the router**

Modify `backend/src/trove/main.py` — find the block that includes the `indexers` router, and directly after it, include the catalog router under the catalog-specific prefix.

Open the file, search for `from trove.api.indexers import router as indexers_router`, and add alongside it:

```python
from trove.api.catalog import router as catalog_router
```

Then in the `app.include_router(indexers_router, prefix="/api/indexers", ...)` call region, add:

```python
app.include_router(catalog_router, prefix="/api/indexers/catalog", tags=["catalog"])
```

- [ ] **Step 3: Sanity check — start the app headless**

Run: `cd backend && uv run python -c "
from trove.main import create_app
app = create_app()
paths = sorted(r.path for r in app.routes if hasattr(r, 'path'))
print([p for p in paths if 'catalog' in p])
"`
Expected: prints `['/api/indexers/catalog', '/api/indexers/catalog/{slug}']`.

- [ ] **Step 4: Commit**

```bash
git add backend/src/trove/api/catalog.py backend/src/trove/main.py
git commit -m "feat: POST /api/indexers/catalog/{slug} installs a catalog entry"
```

---

## Task 16: API tests for catalog endpoints

**Files:**
- Create: `backend/tests/api/test_catalog_api.py`

- [ ] **Step 1: Write the tests**

Create `backend/tests/api/test_catalog_api.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient) -> None:
    client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "correct horse battery staple"},
    )


def test_list_catalog_returns_entries(client: TestClient) -> None:
    _login(client)
    resp = client.get("/api/indexers/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 12
    slugs = {e["slug"] for e in body}
    assert "thepiratebay" in slugs
    tpb = next(e for e in body if e["slug"] == "thepiratebay")
    assert tpb["already_installed"] is False
    assert tpb["default_mirror"] in tpb["mirrors"]


def test_install_catalog_entry_creates_indexer(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://thepiratebay.org", "name": None},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "cardigann"
    assert body["base_url"] == "https://thepiratebay.org"
    assert body["name"] == "The Pirate Bay"

    # already_installed flips on a subsequent list
    listing = client.get("/api/indexers/catalog").json()
    tpb = next(e for e in listing if e["slug"] == "thepiratebay")
    assert tpb["already_installed"] is True


def test_install_twice_dedups_name(client: TestClient) -> None:
    _login(client)
    first = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://thepiratebay.org"},
    )
    second = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://tpb.party"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["name"] == "The Pirate Bay"
    assert second.json()["name"] == "The Pirate Bay-2"


def test_install_unknown_slug_404(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/not-a-real-site",
        json={"base_url": "https://example.com"},
    )
    assert resp.status_code == 404


def test_install_rejects_base_url_not_in_mirrors(client: TestClient) -> None:
    _login(client)
    resp = client.post(
        "/api/indexers/catalog/thepiratebay",
        json={"base_url": "https://totally-evil-mirror.example.com"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "base_url_not_in_catalog_mirrors"
```

- [ ] **Step 2: Run**

Run: `cd backend && uv run pytest tests/api/test_catalog_api.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_catalog_api.py
git commit -m "test: catalog API endpoints"
```

---

## Task 17: Expose catalog endpoints in frontend `api.ts`

**Files:**
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Add the TypeScript type**

Edit `web/src/lib/api.ts` — after the `IndexerHealthOut` type (around line 131), add:

```typescript
export type CatalogEntryOut = {
  slug: string;
  display_name: string;
  description: string;
  categories: Category[];
  mirrors: string[];
  default_mirror: string;
  protocol: Protocol;
  logo: string | null;
  already_installed: boolean;
};

export type CatalogInstallRequest = {
  base_url: string;
  name?: string | null;
};
```

- [ ] **Step 2: Add the API methods**

Inside the `api.indexers` object literal (around line 483), add a `catalog` sub-object. The diff, line-for-line:

```typescript
  indexers: {
    list: () => request<IndexerOut[]>("/api/indexers"),
    health: () => request<IndexerHealthOut[]>("/api/indexers/health"),
    create: (payload: IndexerCreate) =>
      request<IndexerOut>("/api/indexers", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    update: (id: number, payload: Partial<IndexerCreate>) =>
      request<IndexerOut>(`/api/indexers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      }),
    remove: (id: number) => request<void>(`/api/indexers/${id}`, { method: "DELETE" }),
    test: (id: number) =>
      request<IndexerTestResult>(`/api/indexers/${id}/test`, { method: "POST" }),
    catalog: {
      list: () => request<CatalogEntryOut[]>("/api/indexers/catalog"),
      install: (slug: string, payload: CatalogInstallRequest) =>
        request<IndexerOut>(`/api/indexers/catalog/${slug}`, {
          method: "POST",
          body: JSON.stringify(payload)
        })
    }
  },
```

- [ ] **Step 3: Typecheck**

Run: `cd web && pnpm check`
Expected: no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/api.ts
git commit -m "feat(web): catalog types + api.indexers.catalog methods"
```

---

## Task 18: Create `/indexers/catalog/+page.svelte`

**Files:**
- Create: `web/src/routes/indexers/catalog/+page.svelte`

- [ ] **Step 1: Write the page**

Create `web/src/routes/indexers/catalog/+page.svelte`:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { api, type CatalogEntryOut } from "$lib/api";
  import { Database, Loader2, Check, ArrowLeft } from "lucide-svelte";

  let entries = $state<CatalogEntryOut[]>([]);
  let loading = $state(true);
  let errorMsg = $state<string | null>(null);
  let installingSlug = $state<string | null>(null);
  let selectedMirror = $state<Record<string, string>>({});
  let perEntryError = $state<Record<string, string>>({});

  async function load() {
    loading = true;
    errorMsg = null;
    try {
      entries = await api.indexers.catalog.list();
      // Seed mirror selection with default_mirror.
      const next: Record<string, string> = {};
      for (const e of entries) next[e.slug] = e.default_mirror;
      selectedMirror = next;
    } catch (e) {
      const err = e as { detail?: string };
      errorMsg = err.detail ?? "Failed to load catalog.";
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function install(entry: CatalogEntryOut) {
    installingSlug = entry.slug;
    perEntryError[entry.slug] = "";
    try {
      await api.indexers.catalog.install(entry.slug, {
        base_url: selectedMirror[entry.slug],
        name: null
      });
      // Refresh — the server now reports already_installed=true.
      await load();
    } catch (e) {
      const err = e as { detail?: string };
      perEntryError[entry.slug] = err.detail ?? "Install failed.";
    } finally {
      installingSlug = null;
    }
  }
</script>

<div class="space-y-6">
  <div class="flex items-center gap-3">
    <a
      href="/indexers"
      class="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm hover:bg-muted"
    >
      <ArrowLeft class="h-3.5 w-3.5" /> Indexers
    </a>
    <div>
      <h2 class="text-xl font-semibold">Catalog</h2>
      <p class="mt-1 text-sm text-muted-foreground">
        One-click install for public, no-account torrent sites.
      </p>
    </div>
  </div>

  {#if loading}
    <div class="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground">
      Loading…
    </div>
  {:else if errorMsg}
    <div class="rounded-xl border border-destructive/30 bg-destructive/10 p-6 text-sm text-destructive">
      {errorMsg}
    </div>
  {:else}
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {#each entries as entry (entry.slug)}
        <div class="flex flex-col rounded-xl border border-border bg-card p-5 shadow-sm">
          <div class="mb-2 flex items-start gap-3">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted">
              <Database class="h-5 w-5 text-muted-foreground" />
            </div>
            <div class="min-w-0">
              <div class="truncate text-base font-semibold">{entry.display_name}</div>
              <div class="mt-0.5 flex flex-wrap gap-1">
                {#each entry.categories as cat (cat)}
                  <span class="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {cat}
                  </span>
                {/each}
              </div>
            </div>
          </div>
          <p class="mb-4 flex-1 text-sm text-muted-foreground">{entry.description}</p>

          <label class="mb-3 block">
            <span class="mb-1 block text-xs font-medium text-muted-foreground">Mirror</span>
            <select
              bind:value={selectedMirror[entry.slug]}
              disabled={entry.already_installed}
              class="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs disabled:opacity-60"
            >
              {#each entry.mirrors as mirror (mirror)}
                <option value={mirror}>{mirror}</option>
              {/each}
            </select>
          </label>

          {#if entry.already_installed}
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-md bg-muted px-3 py-2 text-sm font-medium text-muted-foreground"
              disabled
            >
              <Check class="h-4 w-4" /> Installed
            </button>
          {:else}
            <button
              type="button"
              class="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              disabled={installingSlug === entry.slug}
              onclick={() => install(entry)}
            >
              {#if installingSlug === entry.slug}
                <Loader2 class="h-4 w-4 animate-spin" /> Installing…
              {:else}
                Add
              {/if}
            </button>
          {/if}

          {#if perEntryError[entry.slug]}
            <div class="mt-2 text-xs text-destructive">{perEntryError[entry.slug]}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
```

- [ ] **Step 2: Typecheck**

Run: `cd web && pnpm check`
Expected: no errors.

- [ ] **Step 3: Start backend + frontend, smoke-test by hand**

Run (two terminals):
- Backend: `cd backend && uv run uvicorn trove.main:app --reload`
- Frontend: `cd web && pnpm dev`

Browse to `http://localhost:5173/indexers/catalog`. Log in if prompted. Verify all 12 tiles render with mirror dropdowns and an enabled **Add** button. Click **Add** on one site. Verify the button flips to **Installed**. Visit `/indexers` — the new row appears with the correct name and URL.

- [ ] **Step 4: Commit**

```bash
git add web/src/routes/indexers/catalog/+page.svelte
git commit -m "feat(web): /indexers/catalog tile grid for catalog entries"
```

---

## Task 19: Add "Browse catalog" button on `/indexers`

**Files:**
- Modify: `web/src/routes/indexers/+page.svelte:243-249`

- [ ] **Step 1: Add the button**

Edit `web/src/routes/indexers/+page.svelte` — replace the single header-action block:

```svelte
    <button
      class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      onclick={openForm}
    >
      <Plus class="h-4 w-4" /> Add indexer
    </button>
```

with a two-button cluster:

```svelte
    <div class="flex items-center gap-2">
      <a
        href="/indexers/catalog"
        class="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-muted"
      >
        <Database class="h-4 w-4" /> Browse catalog
      </a>
      <button
        class="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        onclick={openForm}
      >
        <Plus class="h-4 w-4" /> Add indexer
      </button>
    </div>
```

(`Database` is already imported from `lucide-svelte` in this file; no new import required.)

- [ ] **Step 2: Visual smoke-test**

With both servers still running, refresh `/indexers`. Verify the new **Browse catalog** button appears next to **Add indexer** and navigates to `/indexers/catalog`.

- [ ] **Step 3: Commit**

```bash
git add web/src/routes/indexers/+page.svelte
git commit -m "feat(web): browse catalog button on /indexers"
```

---

## Task 20: Add onboarding step for catalog

**Files:**
- Modify: `web/src/routes/onboarding/+page.svelte`

- [ ] **Step 1: Add the new step to the Step union**

Edit line 28 — change:

```typescript
  type Step = "welcome" | "client" | "indexer" | "ai" | "tmdb" | "done";
```

to:

```typescript
  type Step = "welcome" | "client" | "indexer" | "catalog" | "ai" | "tmdb" | "done";
```

- [ ] **Step 2: Add state + helpers for the step**

In the `<script>` block, after the existing `indexerJustSaved` declaration (around line 79), append:

```typescript
  // Catalog step state
  import type { CatalogEntryOut } from "$lib/api";
  let catalogEntries = $state<CatalogEntryOut[]>([]);
  let catalogLoading = $state(false);
  let catalogSelected = $state<Set<string>>(new Set());
  let catalogInstalling = $state(false);
  let catalogJustAdded = $state(0);
  let catalogError = $state<string | null>(null);

  async function loadCatalog() {
    if (catalogEntries.length > 0) return;
    catalogLoading = true;
    try {
      catalogEntries = await api.indexers.catalog.list();
    } catch (e) {
      const err = e as { detail?: string };
      catalogError = err.detail ?? "Failed to load catalog.";
    } finally {
      catalogLoading = false;
    }
  }

  function toggleCatalog(slug: string) {
    const next = new Set(catalogSelected);
    if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    catalogSelected = next;
  }

  async function installSelectedCatalog() {
    catalogInstalling = true;
    catalogError = null;
    let added = 0;
    for (const entry of catalogEntries) {
      if (!catalogSelected.has(entry.slug) || entry.already_installed) continue;
      try {
        await api.indexers.catalog.install(entry.slug, {
          base_url: entry.default_mirror,
          name: null
        });
        added += 1;
      } catch (e) {
        const err = e as { detail?: string };
        catalogError = `${entry.display_name}: ${err.detail ?? "install failed"}`;
        break;
      }
    }
    catalogJustAdded = added;
    catalogInstalling = false;
    if (added > 0) {
      indexers = await api.indexers.list();
    }
    step = "ai";
  }
```

Move the `import type { CatalogEntryOut } from "$lib/api";` to the top of the `<script>` block next to the other imports (keep the codebase's single `import` style).

- [ ] **Step 3: Insert step transition from indexer → catalog**

Find every place in the file where `step = "ai"` is assigned as the transition out of the `indexer` step (lines ~587, ~666, based on existing content). Change those two transitions to `step = "catalog"` so the catalog step is entered after the manual indexer step.

- [ ] **Step 4: Add the catalog step template**

Find the closing `{/if}` of the `step === "indexer"` block (around line 670), and immediately after it insert:

```svelte
  {#if step === "catalog"}
    {#await loadCatalog() then _}{/await}
    <div class="rounded-2xl border border-border bg-card p-8 shadow-sm">
      <div class="flex items-start justify-between">
        <div>
          <h2 class="flex items-center gap-2 text-xl font-semibold">
            <Database class="h-5 w-5 text-primary" /> Public torrent sites (optional)
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Pick any public sites you want Trove to search. You can always add more later.
          </p>
        </div>
      </div>

      {#if catalogLoading}
        <div class="mt-6 text-sm text-muted-foreground">Loading catalog…</div>
      {:else}
        <div class="mt-6 grid grid-cols-1 gap-3 md:grid-cols-2">
          {#each catalogEntries as entry (entry.slug)}
            <label
              class="flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-background p-3 hover:bg-muted"
              class:opacity-50={entry.already_installed}
            >
              <input
                type="checkbox"
                class="mt-1 h-4 w-4"
                checked={catalogSelected.has(entry.slug)}
                disabled={entry.already_installed}
                onchange={() => toggleCatalog(entry.slug)}
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 text-sm font-medium">
                  {entry.display_name}
                  {#if entry.already_installed}
                    <span class="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
                      installed
                    </span>
                  {/if}
                </div>
                <div class="mt-0.5 text-xs text-muted-foreground">{entry.description}</div>
              </div>
            </label>
          {/each}
        </div>
      {/if}

      {#if catalogError}
        <div class="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {catalogError}
        </div>
      {/if}

      <div class="mt-6 flex items-center justify-between">
        <button
          type="button"
          class="rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
          onclick={() => (step = "ai")}
        >
          <SkipForward class="mr-1 inline h-4 w-4" />
          Skip
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          disabled={catalogInstalling || catalogSelected.size === 0}
          onclick={installSelectedCatalog}
        >
          {#if catalogInstalling}
            <Loader2 class="h-4 w-4 animate-spin" /> Installing…
          {:else}
            Add {catalogSelected.size} site{catalogSelected.size === 1 ? "" : "s"}
            <ChevronRight class="h-4 w-4" />
          {/if}
        </button>
      </div>
    </div>
  {/if}
```

- [ ] **Step 5: Smoke-test**

Restart the frontend (`pnpm dev`), clear `localStorage.trove_onboarding_dismissed` in DevTools if set, visit `/onboarding`. Walk through: welcome → client → indexer (skip) → **catalog** step appears. Check two boxes, click "Add 2 sites", land on AI step. Visit `/indexers` and verify both sites were added.

- [ ] **Step 6: Commit**

```bash
git add web/src/routes/onboarding/+page.svelte
git commit -m "feat(onboarding): public-sites step between indexer and AI"
```

---

## Task 21: Per-site fixture smoke tests (representative subset)

**Files:**
- Create: `backend/tests/fixtures/catalog/.gitignore` (empty — placeholder so empty dir can be committed)
- Create: `backend/tests/fixtures/catalog/README.md`
- Create: `backend/tests/test_catalog_fixtures.py`

Spec requires per-site HTML fixtures for all 12 sites. Capturing 12 real HTML responses is a manual operation outside the scope of this plan — but we ship the machinery and a worked example for one site so the pattern is clear and any site with a fixture immediately gets coverage.

- [ ] **Step 1: Write the README and fixture runner**

Create `backend/tests/fixtures/catalog/README.md`:

```markdown
# Catalog fixture HTML

One `<slug>-search.html` file per site, containing a real search-results page captured from the site's response to a benign query (e.g. "ubuntu").

## How to capture

```bash
# Example: TPB
curl -sL 'https://thepiratebay.org/search/ubuntu/0/99/0' \
  -H 'User-Agent: Mozilla/5.0' \
  > thepiratebay-search.html
```

Pick a query whose results are unambiguous and stable (distro ISOs, commonly-seeded old scene releases). The fixture is committed — keep it small (<500 KB) by trimming or using a narrow query.

Re-capture whenever `scripts/update-catalog.py diff` shows the upstream YAML has changed *and* the corresponding fixture test starts failing.
```

Create `backend/tests/test_catalog_fixtures.py`:

```python
"""Parse-each-fixture smoke test.

For every slug in the catalog that has a corresponding
`tests/fixtures/catalog/<slug>-search.html` file, this test:
    - loads the vendored YAML
    - runs the Cardigann row extractor against the fixture
    - asserts at least one release with a non-empty title

Missing fixtures are silently skipped — run `pytest -vv` to see which
slugs are covered. Capturing 12 real HTML fixtures is a one-time manual
task; tests pass until a fixture is captured AND its extraction breaks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from trove.indexers.cardigann import CardigannIndexer, load_definition_yaml
from trove.services import catalog

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "catalog"


def _covered_slugs() -> list[str]:
    return [
        e.slug
        for e in catalog.list_entries()
        if (FIXTURE_DIR / f"{e.slug}-search.html").exists()
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
```

- [ ] **Step 2: Capture one fixture to validate the mechanism (TPB)**

Run: `cd backend/tests/fixtures/catalog && curl -sL 'https://thepiratebay.org/search/ubuntu/0/99/0' -H 'User-Agent: Mozilla/5.0' > thepiratebay-search.html`

If the command fails (rate-limited, blocked) or returns a captcha page, try one of the other mirrors (`tpb.party`, `piratebay.live`) using the same URL path structure.

Verify: `head -c 200 backend/tests/fixtures/catalog/thepiratebay-search.html` shows actual HTML, not a captcha/empty body.

- [ ] **Step 3: Run the fixture test**

Run: `cd backend && uv run pytest tests/test_catalog_fixtures.py -v`
Expected: one parametrization for `thepiratebay` PASSES. The rest of the catalog is simply not covered (empty parametrization set for those slugs).

If the TPB fixture test FAILS, the vendored YAML doesn't match the HTML — likely filter-path differences. Debug by running a one-off extraction in a REPL:

```python
from pathlib import Path
from bs4 import BeautifulSoup
from trove.indexers.cardigann import load_definition_yaml
from trove.services import catalog

defn = load_definition_yaml(catalog.read_yaml("thepiratebay"))
html = Path("tests/fixtures/catalog/thepiratebay-search.html").read_text()
soup = BeautifulSoup(html, "lxml")
print(len(soup.select(defn.rows_selector)))
```

Then inspect `defn.fields["title"]` etc. If parser filters are missing, add them following the Task 9–13 TDD pattern.

- [ ] **Step 4: Document follow-up**

Add a line to `TODO.md` at the repo root (create the `## Catalog fixtures` section if needed):

```markdown
## Catalog fixtures

- [ ] Capture `-search.html` fixtures for the 11 remaining catalog slugs.
  Pattern: `backend/tests/fixtures/catalog/<slug>-search.html`.
  Extraction test lives in `backend/tests/test_catalog_fixtures.py` and
  is parametrized over whichever fixtures are present.
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/ backend/tests/test_catalog_fixtures.py TODO.md
git commit -m "test: parametrized catalog fixture extraction + TPB fixture"
```

---

## Task 22: Document the catalog in user docs

**Files:**
- Modify: `backend/src/trove/docs/03-indexers.md`

- [ ] **Step 1: Add a section**

Edit `backend/src/trove/docs/03-indexers.md`. Before the `## Priority and ordering` heading, insert:

```markdown
## Catalog (public sites, one click)

For public, no-account torrent sites, Trove ships with a curated catalog of 12 pre-configured definitions: The Pirate Bay, 1337x, TorrentGalaxy, LimeTorrents, MagnetDL, Torlock, BitSearch, SolidTorrents, Nyaa, EZTV, YTS, and AnimeTosho.

**How to install:**

1. On `/indexers`, click **Browse catalog** (next to **Add indexer**).
2. Pick a mirror from the dropdown on the site's tile — catalog entries list multiple known mirrors for sites that have them.
3. Click **Add**. The tile flips to **Installed** and the site appears on `/indexers` as a normal Cardigann indexer.

The onboarding wizard also surfaces these sites as an optional step — pick any you want in one go.

**Behind the scenes**: a catalog-installed entry is an ordinary `type=cardigann` indexer with a vendored YAML definition. The Test, Edit, and Delete buttons work the same way they do for hand-added indexers. If you ever need to override the URL or rename the entry, use **Edit** — nothing is special about catalog rows.

**Updating definitions**: the shipped YAMLs track `Prowlarr/Prowlarr-indexers`. When a site changes its HTML, searches will start returning 0 results. Upstream usually has a fix within days. Trove refreshes the vendored files on each release; to sync sooner, a maintainer can run `scripts/update-catalog.py diff` to see what's changed upstream, then `sync` to pull.
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/trove/docs/03-indexers.md
git commit -m "docs: document public-site catalog in indexers guide"
```

---

## Task 23: Final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: all tests PASS, including the new `test_catalog.py`, `test_cardigann_filters.py`, `test_catalog_api.py`, and `test_catalog_fixtures.py` (parametrized over whatever fixtures are present).

- [ ] **Step 2: Run ruff + mypy**

Run: `cd backend && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy`
Expected: no errors.

If mypy complains about `IndexerRow.catalog_slug.is_not(None)`, keep the existing `# type: ignore[attr-defined]` comment from Task 14.

- [ ] **Step 3: Frontend typecheck**

Run: `cd web && pnpm check`
Expected: no TypeScript errors.

- [ ] **Step 4: Manual end-to-end smoke test**

With both servers running, starting from a clean browser (or after clearing the onboarding-dismissed flag):

1. `/onboarding` → complete welcome, skip client, skip indexer, arrive at catalog step. Pick 2 sites, click **Add 2 sites**. Land on AI step.
2. Navigate to `/indexers` → verify both sites in the list with the correct base URL and `type=cardigann`.
3. Click **Test** on one of them — verify green check or a descriptive failure (network-dependent; "HTTP 200" = ok, CAPTCHA page = expected intermittent).
4. Click **Browse catalog** → verify the two installed sites show **Installed** (grey, disabled).
5. Pick a third site from the catalog, select an alternate mirror, click **Add** → lands on `/indexers` list with three entries.
6. Delete one of the catalog sites on `/indexers` → go back to `/indexers/catalog` → verify it's no longer marked **Installed**.

- [ ] **Step 5: No-op commit for the plan completion marker**

Not needed — the branch will be merged via PR.

---

## Notes for the implementer

- **Private trackers stay out.** Do not add UNIT3D / RarTracker / account-based sites to the catalog; those already have their own dedicated flows. The catalog is for "no account, just search" sites only.
- **When a filter fires a warning in production** (`cardigann: unknown filter`), that's your signal that a vendored YAML grew a new filter. Add it using the TDD template from Tasks 9–13; the one-line addition to `_apply_filter` is almost always trivial.
- **Don't pre-fetch or pre-test upstream during backend startup.** The app boots offline; the catalog is pure static data from disk until the user clicks **Install**, at which point the normal indexer flow takes over.
- **`catalog_slug` is a marker, not a foreign key.** If a user renames or re-bases a catalog-installed indexer, `catalog_slug` still points at the original entry — that's fine; it only drives `already_installed` in the UI.
