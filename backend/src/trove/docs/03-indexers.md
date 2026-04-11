---
title: Indexers
order: 3
description: Configure Newznab, Torznab, and Cardigann sources for live search.
---

# Indexers

An **indexer** is a site Trove can query for releases in real time. Think of it as your "search backend" — when you run a search on `/search`, Trove fans out to every enabled indexer in parallel and merges the results.

Trove supports three indexer types out of the box:

## Newznab (Usenet)

The classic Usenet indexer API used by sites like NZBgeek, NZBplanet, DrunkenSlug, and dozens of others. Speaks XML-RSS.

**URL**: the base of the indexer's API — e.g. `https://api.nzbgeek.info` or `https://nzbplanet.net`. Trove automatically appends `/api` if you don't include it, and follows HTTP-to-HTTPS redirects.

**API key**: Found on your indexer profile page. Usually a long hex string.

**Protocol**: `usenet` — returns NZB file URLs.

## Torznab (Torrents)

Same API schema as Newznab, but returns torrent metadata. Used by private trackers that expose a public API, and by Prowlarr/Jackett's exported endpoints.

**URL**: whatever the Torznab endpoint provides. Often `http://<prowlarr-host>:9696/1/api`.

**API key**: The tracker's generated API key.

**Protocol**: `torrent` — returns magnet links or `.torrent` URLs.

**Tip**: If you already run Prowlarr or Jackett, you can point Trove's Torznab at any of their indexers. It's a valid migration path — you'll get search pipelines without needing to re-configure every tracker.

## Cardigann (YAML-defined trackers)

For trackers that don't have a native API, Cardigann uses YAML definition files that describe the site's HTML layout. Trove includes a minimal-subset parser that supports **search-only** definitions without login flows.

**When to use**: Public trackers or trackers where you paste a pre-authenticated session cookie. The full Cardigann YAML format (with login forms, CAPTCHAs, and multi-step flows) is NOT supported yet — that's on the roadmap.

**How**:

1. Find a Cardigann YAML definition from a community repo (e.g. Prowlarr-indexers on GitHub)
2. Copy the YAML
3. On `/indexers`, click **Add indexer** → choose Cardigann
4. Paste the YAML into the definition textarea
5. Save and test

**What works**:
- Static `search.paths[0].path`
- `search.rows.selector` (CSS selectors)
- Field extraction: `title`, `download`, `size`, `infohash`, `category`
- Basic filters: `replace`, `regexp`, `append`, `prepend`

**What doesn't work yet**:
- Login flows (cookie, form, POST)
- Multi-page pagination
- Custom headers beyond what httpx sends by default
- JavaScript-heavy sites that need Playwright/Puppeteer

## Priority and ordering

Each indexer has a **priority** field (default 50). Lower numbers run first in the fan-out, but since Trove queries all enabled indexers in parallel, priority mainly matters for tie-breaking when the same release appears from multiple sources — the higher-priority indexer's copy is kept.

## Testing

Click **Test** next to an indexer to fetch `/api?t=caps` and verify credentials. The test result shows the server version and any supported categories.

Common errors:
- **invalid api key** → 401 from the indexer. Double-check the key
- **empty response** → usually wrong base URL, often because `/api` got appended twice. Trove detects double `/api` and strips it, but sanity-check the URL
- **non-XML response (content-type=text/html)** → you hit a login page, not the API. The URL is wrong
- **indexer error: daily limit exceeded** → rate-limited. Most Newznab indexers have daily search caps on free tiers

## Editing indexers

Same pattern as clients: click **Edit** on the `/indexers` page. API key is write-only — leave it blank to keep the stored key.
