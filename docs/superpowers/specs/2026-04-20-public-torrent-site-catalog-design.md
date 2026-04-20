# Public torrent site catalog

**Date:** 2026-04-20
**Status:** Design, pre-implementation
**Scope:** Ship a curated, built-in catalog of public (no-account) torrent sites so users can add them with a single click instead of copy-pasting YAML from a GitHub repo.

## Problem

Today, adding a public torrent site like The Pirate Bay or 1337x to Trove requires:

1. Locate a Cardigann YAML definition on GitHub (typically `Prowlarr/Prowlarr-indexers`).
2. Copy the raw YAML.
3. On `/indexers`, click **Add**, select type **Cardigann**, paste the YAML into a textarea.
4. Fill in name + base URL manually.
5. Save and test.

This is friction that hides an entire class of usable sites behind expert knowledge. The underlying Cardigann parser already supports search-only public sites — the gap is pure UX.

## Goal

Add a curated "catalog" of 12 verified public torrent sites, installable in one click from a dedicated in-app page (and as an optional step in the onboarding wizard). Installation produces an ordinary `type=cardigann` indexer row — no new storage model, no parallel driver.

## Non-goals

- **No login / account-based sites**. The catalog is for truly public, search-only sites. Private trackers (account + passkey + cookies) remain in the existing Cardigann / UNIT3D / RarTracker flows.
- **No automated site-health monitoring** beyond what the existing Test button provides.
- **No auto-failover across mirrors** at runtime. The user picks one mirror at install time.
- **No logo hosting**. v1 ships without per-site artwork.
- **No dynamic fetching of definitions from upstream at runtime**. Deterministic builds matter more than freshness.

## Shape of the solution

### Catalog content

Twelve sites, all present in `Prowlarr/Prowlarr-indexers`, all search-only, all no-account:

| Slug | Display name | Focus |
|------|---|---|
| `thepiratebay` | The Pirate Bay | general |
| `1337x` | 1337x | general |
| `torrentgalaxy` | TorrentGalaxy | general |
| `limetorrents` | LimeTorrents | general |
| `magnetdl` | MagnetDL | general |
| `torlock` | Torlock | general |
| `bitsearch` | BitSearch | aggregator |
| `solidtorrents` | SolidTorrents | aggregator |
| `nyaa` | Nyaa | anime / asian |
| `eztv` | EZTV | TV |
| `yts` | YTS | movies (small-size encodes) |
| `animetosho` | AnimeTosho | anime |

The list is expected to evolve; the architecture makes adding an entry a one-YAML-plus-one-registry-line operation.

### Storage layout

```
backend/src/trove/indexers/
├── catalog/
│   ├── registry.yaml         # curated metadata for the 12 entries
│   ├── thepiratebay.yml      # vendored from Prowlarr-indexers
│   ├── 1337x.yml
│   ├── ... (10 more)
│   └── yts.yml
└── cardigann.py              # existing parser, extended as needed
```

`registry.yaml` is the authoritative index. One entry per site:

```yaml
- slug: thepiratebay
  display_name: The Pirate Bay
  description: General-purpose public torrent tracker, no account required.
  categories: [movies, tv, music, software, games, books]
  yaml_file: thepiratebay.yml
  mirrors:
    - https://thepiratebay.org
    - https://tpb.party
    - https://piratebay.live
  default_mirror: https://thepiratebay.org
  protocol: torrent
  logo: null
```

Fields:

- `slug` — stable identifier. Matches filename stem, URL path segment, frontend route.
- `display_name` — shown in UI.
- `description` — one-sentence sell.
- `categories` — list of `Category` enum values, used for filtering / search-routing hints.
- `yaml_file` — filename within `catalog/` (relative).
- `mirrors` — list of base URLs the site is known to respond on. Must include `default_mirror`. This is **our curated list**, not a passthrough of the vendored YAML's `links:` block — upstream often lists dead or unreliable mirrors, and we control what the UI exposes to the user.
- `default_mirror` — pre-selected in the UI dropdown. Must be an element of `mirrors`.
- `protocol` — `torrent` for all current entries, but kept explicit for future-proofing.
- `logo` — always `null` in v1. Reserved for future use (path relative to a static directory).

No database-level representation. The catalog is source code, not data. A user who installs an entry ends up with a plain `IndexerRow` of type `cardigann`, functionally indistinguishable from a hand-added one.

### Vendoring and updates

Definitions are **manually vendored** — the canonical source is `Prowlarr/Prowlarr-indexers`, but the files live in our repo. Updates are explicit:

- `scripts/update-catalog.py` downloads the upstream tarball, compares SHA-256 of each vendored file against upstream, prints a per-file status: `unchanged` / `upstream changed` / `not found upstream`.
- The maintainer reviews the diff, copies updated YAMLs, runs the test suite (notably the per-site fixture tests in §Testing), and commits.
- Cadence is manual — monthly or on user bug report.

Rejected alternatives:

- **Git submodule**: pulls a ~500-file repo for our 12 files, and submodules generate friction for contributors.
- **Build-time fetch**: breaks deterministic builds (same SHA can produce different images across time).

### Backend

**New service: `backend/src/trove/services/catalog.py`**

Module-level cache of the parsed registry plus on-demand YAML reading:

```python
@dataclass(frozen=True, slots=True)
class CatalogEntry:
    slug: str
    display_name: str
    description: str
    categories: list[Category]
    yaml_file: str
    mirrors: list[str]
    default_mirror: str
    protocol: Protocol

def load_catalog() -> dict[str, CatalogEntry]: ...   # cached on first call
def list_entries() -> list[CatalogEntry]: ...
def get_entry(slug: str) -> CatalogEntry: ...        # raises KeyError
def read_yaml(slug: str) -> str: ...                 # reads file from disk
```

The cache invalidates only when the module reloads (i.e. never in production, always in tests that clear `sys.modules`).

**New endpoints in `backend/src/trove/api/indexers.py`**

```
GET  /api/indexers/catalog          → list[CatalogEntryOut]
POST /api/indexers/catalog/{slug}   → IndexerOut (201)
     body: { base_url: str, name: str | null }
```

The API layer exposes a separate `CatalogEntryOut` Pydantic model that mirrors `CatalogEntry`'s fields and adds `already_installed: bool`. `already_installed` is computed at request time by querying `IndexerRow.catalog_slug == slug` (see marker column below) — a single row is enough, we don't count duplicates.

**Tracking which rows came from the catalog**

To compute `already_installed`, we need to know which existing Cardigann indexers originated from the catalog. Options considered:

- Matching by `name == display_name` is fragile (user may have renamed).
- Matching by `base_url` within the entry's `mirrors` list is more robust but still ambiguous if two entries share a mirror (none currently do).
- **Chosen:** add a nullable `catalog_slug: str | None` column to `IndexerRow`. Set on catalog-installed rows, `null` for hand-added rows. Exact-match lookup is O(1) and survives renames.

This requires an Alembic migration adding the column; existing rows get `null`.

**`POST /api/indexers/catalog/{slug}` implementation**

1. `entry = catalog.get_entry(slug)` → 404 if unknown.
2. Validate `body.base_url in entry.mirrors` → 422 otherwise. Prevents using the catalog endpoint as a generic indexer-creator with arbitrary URLs.
3. `yaml_text = catalog.read_yaml(slug)`; parse via `load_definition_yaml`. Errors here are our bug, not the user's — 500 with a diagnostic message.
4. Resolve `name`: prefer `body.name`, otherwise `entry.display_name`. If taken, append `-2`, `-3`, … until free (silent dedup, not a 409).
5. Construct `IndexerRow` with `type="cardigann"`, `protocol=entry.protocol`, `base_url=body.base_url`, `definition_yaml=yaml_text`, `catalog_slug=slug`, empty credentials, enabled=True, default priority.
6. Insert, commit, return `IndexerOut`.

### Frontend

**New page: `web/src/routes/indexers/catalog/+page.svelte`**

Grid of tiles, one per catalog entry. Each tile shows:

- Generic icon (Lucide `Database`) in v1 — no per-site logos.
- Display name.
- Description.
- Category badges.
- Mirror `<select>` pre-set to `default_mirror`.
- **Add** button. Disabled and relabeled **Installed** when `already_installed` is true.

Layout: CSS grid, min column width ~280px, wraps to single column on narrow viewports. No pagination (12 entries fit).

Interaction:

- Click **Add** → POST `/api/indexers/catalog/{slug}` with chosen `base_url`, `name: null`.
- On 201 → toast "{display_name} added", flip the tile's `already_installed`, no navigation.
- On error → in-tile error message, keep button enabled for retry.

No search/filter input in v1. Add one when the catalog exceeds ~20 entries.

**Update: `web/src/routes/indexers/+page.svelte`**

Add a secondary button next to **Add indexer** labeled **Browse catalog**. Routes to `/indexers/catalog`. Existing form is untouched.

**Onboarding: `web/src/routes/onboarding/+page.svelte`**

Insert a new step between the welcome panel and the existing "Add your first indexer" step:

- Title: "Public torrent sites (optional)".
- Body: checkbox list of the 12 catalog entries, each with display name + one-line description.
- **Add selected** button — sequentially POSTs to the catalog endpoint for each checked entry. 12 is small enough that no batching / progress bar is needed beyond a spinner on the button.
- **Skip** continues to the next step.

### Parser extensions

The existing `cardigann.py` supports `replace`, `regexp`, `append`, `prepend`. Vendoring the 12 real YAMLs will surface features the current parser does not understand. Expected additions, based on a quick scan of a handful of Prowlarr definitions:

- `urldecode` / `urlencode`
- `split` (with `delimiter` and `index` args)
- `trim` (unless already covered by `get_text(strip=True)`)
- `querystring` (extract a specific query-string parameter — common for `download.php?id=…`)

A per-row `filters` and `remove` block (as opposed to per-field) may also appear; if so, add a pass over the extracted row after the per-field extraction.

**Principle:** add only what is needed to make one of the 12 YAMLs work correctly. Do not pre-implement the full Cardigann filter library. When a filter appears that isn't implemented yet, the `_apply_filter` fallback already returns the value unchanged — silent failures would mask bugs, so add a one-time warning log the first time an unknown filter name is seen per process.

Time-related filters (`dateparse`, `timeparse`) are explicitly **deferred**. The `Release` dataclass has no `added_at` field today; implementing date parsing now would only paint over a missing field. Ignored date fields are logged once as debug-level.

### Testing

Three layers.

**1. Parser unit tests** — `backend/tests/test_cardigann_filters.py`. One test per new filter implementation, with a mock HTML row and asserted extracted value.

**2. Catalog integrity** — `backend/tests/test_catalog.py`:

- Registry loads, has exactly the documented slugs (spot-check subset, not hard-coded full list — allows adding entries without test churn).
- Every entry's `yaml_file` exists in the `catalog/` directory.
- Every entry's YAML parses without raising `IndexerError`.
- `default_mirror` is a member of `mirrors`.
- No duplicate slugs.

**3. Per-site fixture tests** — `backend/tests/fixtures/catalog/{slug}-search.html` contains a real HTML response captured once per site, and a corresponding test runs the parser against it and asserts ≥1 valid release with title, download URL, and size populated. Fixtures intentionally decouple tests from live internet and from CI reaching blocked torrent domains. When upstream changes a YAML, the matching fixture often needs to be re-captured — this is a feature, not a bug (forces manual review).

No live integration tests. Public torrent sites are regularly blocked, throttled, or down — CI cannot depend on them.

### Error handling and operational model

- **Test button on catalog-installed rows**: reuses the existing `/api/indexers/{id}/test` endpoint. No catalog-specific behavior. Failures surface as ordinary HTTP errors in the existing UI.
- **Mirror goes down**: symptom is a failing Test or 0-result searches. User fix is `Edit` → change `base_url` to another mirror from the YAML's `links` block. In v1 the edit dialog does not surface the mirror list; pasting a new URL is the workflow. (A future enhancement can show a dropdown for rows with a `catalog_slug` set.)
- **Site changes HTML**: symptom is 0-result searches on a site that used to work. No auto-detection. Remediation: run `scripts/update-catalog.py`, review the diff, pull the updated YAML, commit, ship.
- **Catalog YAML is malformed after an update** (rare): caught by `test_catalog.py` in CI before merge. If it slips, the API returns 500 and the user sees a loud error; they can uninstall and wait for a hotfix.
- **Slug collision when installing twice**: the name-dedup logic appends `-2`, `-3`. The `catalog_slug` column is not unique — two rows pointing at different mirrors of The Pirate Bay are legal.

### Rollout

Single branch, single PR. Order of commits within the branch:

1. Alembic migration: add `catalog_slug` column.
2. Vendor the 12 YAML files + write `registry.yaml`.
3. Extend the Cardigann parser with the filters the 12 files require (driven by failing per-site fixture tests).
4. Add `services/catalog.py` and the two API endpoints.
5. Add the `/indexers/catalog` Svelte page + the "Browse catalog" button on `/indexers`.
6. Add the onboarding step.
7. Add `scripts/update-catalog.py`.

Each commit is shippable on its own — the API is useful before the UI ships, and the UI works on top of an empty registry during development.

## Open questions (deferred, not blockers)

- Do we want a "Refresh catalog" button in the app that runs `update-catalog.py` behind the scenes? Rejected for v1 — manual maintainer workflow is safer.
- Should we show per-site health trends on the catalog page (e.g., "3 users reported this mirror down this week")? Out of scope; depends on telemetry we don't collect.
- Should the onboarding step default to all 12 pre-checked or all unchecked? Leaning unchecked — opt-in beats opt-out for anything that calls third-party services.
