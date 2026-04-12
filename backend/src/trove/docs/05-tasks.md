---
title: Tasks
order: 5
description: Automate recurring searches and filter rules with YAML-configured tasks.
---

# Tasks

A **task** is a recurring job that runs on a schedule (cron), reads from one or more inputs (search or RSS feeds), applies filters, and sends matches to one or more download clients. Tasks are how you automate "grab new episodes of The Bear" or "download all 4K movies from 2023+".

## YAML format

Tasks are configured with YAML. Here's the basic shape:

```yaml
inputs:
  - kind: search
    query: "the bear"
    categories: [tv]

filters:
  min_seeders: 3
  require: [1080p]
  reject: [cam, telesync]

outputs:
  - my-transmission
```

### Inputs

**`kind: search`** — Runs a live search across all enabled indexers (and the local RSS cache).

```yaml
- kind: search
  query: "ubuntu 24.04"
  categories: [other]
```

For TV shows and movies, you can also pin the search to a specific TMDB / IMDB id. Indexers that honor `tmdbid` / `imdbid` (most modern Newznab indexers do) then filter to *only* that title at the source — no more "The Boys" matching every Fringe episode whose title contains the words. Watchlist-promoted tasks set these automatically from the TMDB metadata.

```yaml
- kind: search
  query: "The Boys"
  categories: [tv]
  tmdb_id: 76479
```

For TV shows with `tmdb_id`, the engine also iterates `season=1..N` on the indexer so older seasons are backfilled — a single Newznab call caps at ~100 hits, which usually only covers the latest season. The first run does a full sweep (capped at 20 seasons); subsequent runs only check the latest grabbed season + the next one to keep API usage low.

You can override the season-iteration explicitly:

```yaml
- kind: search
  query: "The Boys"
  categories: [tv]
  tmdb_id: 76479
  seasons: [1, 2, 3]   # only these seasons
  # seasons: 4         # only this one
  # seasons: auto      # the same as omitting the field when tmdb_id is set
```

**`kind: rss_items`** — Reads from the local RSS cache without hitting indexers. Much faster, and the basis for "standing filter rules" created by the AI agent.

```yaml
- kind: rss_items
  protocol: torrent       # optional: filter to torrent-typed feeds
  feeds: [private-hd]     # optional: only these feeds (by name)
  limit: 1000             # how many recent items to consider
```

### Filters

All filters are optional and combine as AND. An item must pass every defined filter to be accepted.

| Key | Type | Meaning |
|---|---|---|
| `min_seeders` | int | Drop if seeders < N (torrents only — NZBs are exempt) |
| `min_size_mb` | int | Drop if size < N MB |
| `max_size_mb` | int | Drop if size > N MB |
| `year_min` | int | Parse year from title; drop if year < N |
| `year_max` | int | Parse year from title; drop if year > N |
| `kind` | string | `movie` or `series`; rejects the wrong type (uses SxxExx detection) |
| `categories` | list | Only accept items whose category matches one of these |
| `require` | list | Each token must appear in title (case-insensitive) |
| `reject` | list | None of these tokens may appear in title |
| `require_title` | string | Strict show/movie name match. The hit's normalized title prefix (everything up to the SxxExx for series, or up to the year for movies) must equal the normalized filter value. Embedded years are stripped, so "The.Boys.2019.S01E01" and "The.Boys.S01E01" both match `require_title: "The Boys"`. Rejects spinoffs like "The Boys Presents Diabolical" and false positives like Fringe episodes whose episode title contains "The Boy". |
| `require_episode` | bool | Drop releases that don't carry an explicit SxxExx marker. Filters out season packs ("The.Boys.Season.4"), bundles ("The.Boys.S01.Complete"), and the weird `(The Boys S03 E05 T&M E08)` multi-episode formats. Set automatically by watchlist-promoted series tasks. |
| `prefer_quality` | string | Soft ranking boost (not a hard filter). The release whose title contains this token wins the rank tie-break — if "2160p" releases exist, they're picked first; if not, the engine still grabs the best lower-quality match. |

### Outputs

A list of client names (exactly as they appear on `/clients`). The first client whose protocol matches the release gets it. If none match, the release is logged as "no output accepted".

```yaml
outputs:
  - home-transmission
  - backup-deluge
```

## Scheduling

Each task has an optional `schedule_cron` field in standard cron format (UTC). Common patterns:

- `0 * * * *` — every hour on the hour
- `*/15 * * * *` — every 15 minutes
- `0 */2 * * *` — every 2 hours
- `15 3 * * *` — daily at 03:15 UTC

Without a schedule, the task only runs when you trigger it manually from the `/tasks` page.

## Running a task

On `/tasks`:

- **Run now** — triggers the task immediately with the current config
- **Dry run** — same as Run but never actually sends releases to clients. Perfect for testing filters before going live — you'll see which releases WOULD be accepted in the run log
- **History** — expand past runs to see a per-release trace showing why each item was accepted or dropped

## The seen-release database

Trove tracks every release it has ever sent (or attempted to send) for each task in the `seen_release` table. When a task runs, it automatically skips any release it's seen before — so recurring tasks don't re-download the same thing every hour.

The dedup key is episode-level for series (`e:<show>:s01e01`), so 2160p, 1080p, and HEVC variants of the same episode all collapse to one entry — only the highest-ranked one is grabbed. Movies dedup by `m:<title>:<year>`.

Deletes cascade: removing a task from the `/tasks` page also drops its run history and seen-release entries. Same for removing a series/movie from the watchlist when nothing else points at the backing task.

## Complete example — TV show by name

```yaml
inputs:
  - kind: search
    query: "the bear"
    categories: [tv]

filters:
  kind: series
  min_seeders: 3
  require: [1080p, web-dl]
  reject: [cam, telesync, hdcam]
  max_size_mb: 4000

outputs:
  - home-transmission
```

Schedule: `0 * * * *` (hourly)

## Complete example — TV show by TMDB id (watchlist style)

This is what the watchlist promote and the AI agent build for you when you add a series. The key bits are `tmdb_id` (so the indexer scopes the search), `require_title` + `require_episode` (so spinoffs and season packs are dropped), and the implicit `seasons: auto` from having `tmdb_id` set on a `tv` search (so older seasons get backfilled on the first run).

```yaml
inputs:
  - kind: search
    query: "The Boys"
    categories: [tv]
    tmdb_id: 76479

filters:
  min_seeders: 2
  reject: [cam, telesync, hdcam, workprint]
  require_title: "The Boys"
  require_episode: true
  prefer_quality: 2160p

outputs:
  - home-nzbget
  - home-transmission
```

## Complete example — all new 4K movies

```yaml
inputs:
  - kind: rss_items
    protocol: torrent
    limit: 2000

filters:
  kind: movie
  year_min: 2022
  min_seeders: 2
  require: [2160p]
  reject: [cam, telesync, hdcam, workprint]

outputs:
  - home-transmission
```

This is exactly what the AI agent generates for *"grab all 4K movies from 2022 and newer"*.

## Complete example — linux isos

```yaml
inputs:
  - kind: rss_items
    protocol: torrent
    limit: 500

filters:
  kind: software
  min_seeders: 1
  require: [linux, iso]

outputs:
  - home-transmission
```
