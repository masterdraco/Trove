---
title: Indexers
order: 3
description: Configure Newznab, Torznab, Cardigann, UNIT3D, and RarTracker sources for live search.
---

# Indexers

An **indexer** is a site Trove can query for releases in real time. Think of it as your "search backend" — when you run a search on `/search`, Trove fans out to every enabled indexer in parallel and merges the results. Indexers are strictly preferred over RSS feeds for anything but "standing filter rules" — see [RSS vs. indexers](#rss-vs-indexers) at the bottom of this page.

Trove supports five indexer types out of the box:

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

## UNIT3D (Aither, Blutopia, Nordicbytes, …)

[UNIT3D](https://github.com/HDInnovations/UNIT3D) is the codebase that powers a growing number of private torrent trackers — Aither, Blutopia, ANT, MorethanTV, Nordicbytes, and many more. It exposes a first-class JSON search API at `/api/torrents/filter` that Trove talks to directly.

**Why prefer it over Torznab**: UNIT3D trackers support metadata-based filtering (`tmdbId`, `imdbId`, `tvdbId`, `seasonNumber`, `episodeNumber`) at the source, so a search for "The Boys" pinned to TMDB id 76479 returns **only** episodes of that specific show — no more Fringe episodes whose title happens to contain "The Boy". The full back-catalogue is reachable, not just whatever's sitting in the last day of RSS output.

**URL**: the bare host, e.g. `https://nordicbytes.org`. Leave `/api` off — the driver appends `/api/torrents/filter` itself.

**API key**: Generate one from your tracker profile page (usually under *Settings → API Tokens* or similar). It's a Bearer token, **not** the same thing as your torrent passkey.

**Protocol**: always `torrent`.

**Category mapping**: Every UNIT3D install defines its own numeric category IDs. The driver ships with defaults that match the Aither/Blutopia layout (`movies=1, tv=2, music=3, games=4, software=5, anime=6, books=8`). If your tracker uses different IDs, override via the credentials JSON: add a `category_map` key when creating the indexer programmatically, or edit the row in the database. A misaligned mapping just means category-scoped searches return nothing — the driver won't crash.

**Testing**: Click **Test**. A successful connection returns `200 OK` and the driver confirms the response shape is UNIT3D-compatible. Failures usually mean either the API key is wrong (`401 invalid api key`) or the host is not actually a UNIT3D install (`non-JSON response (content-type=text/html)`).

## RarTracker (Superbits, ScenePalace, …)

[RarTracker](https://github.com/bubis73/rartracker) is the Swedish AngularJS-SPA codebase behind Superbits and a cluster of Scandinavian private trackers. It has its own JSON API at `/api/v1/torrents` that accepts `searchText` plus a long list of language/sub/audio/freeleech flags.

**Auth is cookie-based, not token-based**. There's no passkey or bearer token that unlocks search, and the login form is typically protected by hCaptcha, so Trove can't automate the login flow. Instead, you paste the session cookie from your browser devtools.

**How to get the cookie**:

1. Log in to the tracker in your browser as normal
2. Open DevTools (F12) → **Network** tab → refresh the page
3. Click any request to the tracker domain
4. Under **Request Headers**, find the `Cookie:` line
5. Copy everything after `Cookie: ` to the end of the line

You'll typically end up with something like `pass=abc123; PHPSESSID=def456; vid=ghi789` (Superbits sets exactly those three). Paste the full string verbatim into the indexer's **Session cookie** field — keep the semicolon separators, drop the `Cookie: ` prefix.

**Passkey**: A separate value from your profile page, used only to build download URLs (`/api/v1/torrents/download/{id}/{passkey}`). Optional for testing the search connection; required for actually grabbing torrents.

**URL**: `https://superbits.org` (or whichever host). No `/api` suffix — the driver appends the path.

**Protocol**: always `torrent`.

**When the cookie expires** — and it will, eventually, typically after hours or days of inactivity — searches start failing with a clear `session cookie expired or invalid — re-copy it from your browser devtools after logging in` error. Go re-grab the cookie and paste it via **Edit** on the indexer row.

**Search quirk**: if RarTracker's API finds zero rows matching your `searchText`, it returns a generic alphabetical dump of random torrents from across the whole site instead of an empty list. Trove applies a client-side sanity filter to drop anything whose title doesn't actually contain every token from the query, so you get an honest empty result and not XBOX360 scene packs when searching for "Scream 6".

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

Same pattern as clients: click **Edit** on the `/indexers` page. API key / session cookie / passkey fields are write-only — leave them blank to keep the stored value.

## RSS vs. indexers

Trove supports two very different ways of getting release metadata into the system, and it's worth understanding when each makes sense.

| | **Indexer (live search)** | **RSS feed (polled)** |
|---|---|---|
| Coverage | The tracker's full back-catalogue | Only items posted since you started polling |
| Query surface | `searchText`, `tmdbid`, `imdbid`, `season`, `episode`, category filters | None — you get whatever lands |
| Per-request cost | One API call with low limit | None during polling; RSS cache is local |
| Back-fill older content | ✅ yes, `seasons: auto` even iterates season by season | ❌ no — items that predate your first poll never exist |
| Used by task type | `kind: search` | `kind: rss_items` |
| Good for | "find Scream 7", "add all Dune movies", "grab every new Below Deck episode" | "accept every new 4K movie from my nordic tracker", standing filter rules |

**Rule of thumb**: if you already have an indexer for a given tracker (Newznab / Torznab / UNIT3D / RarTracker), you almost certainly don't also need its RSS feed running. The indexer can find everything the RSS can, plus everything older. Feeds only shine when you want a continuous "accept anything that matches this filter" pipeline across the whole tracker — then the local RSS cache is faster and cheaper to scan than hammering the search API every cron cycle.

In Trove you can have both enabled without conflict — they just produce duplicate hits that the dedup pass collapses into one. If you're trying to cut API load, disable the RSS feed for any tracker whose indexer you've added.
