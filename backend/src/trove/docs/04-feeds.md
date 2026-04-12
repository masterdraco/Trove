---
title: RSS Feeds
order: 4
description: Poll tracker RSS feeds and build a searchable local cache.
---

# RSS Feeds

While **indexers** let you search in real time, **RSS feeds** let you continuously pull new releases from trackers and store them in a local searchable cache. Useful for standing filter rules ("every new 4K movie my nordic tracker posts, automatically") where a continuous stream is cheaper than running the full search every cron cycle.

> **Prefer an indexer when you can.** If your tracker speaks Newznab, Torznab, UNIT3D, or RarTracker, set it up as an **indexer** on the [Indexers](indexers) page instead of (or in addition to) an RSS feed. Indexers can reach the full back-catalogue and accept structured queries (`tmdbId`, `season`, etc.); RSS feeds only see what's been posted since you started polling. See the [RSS vs. indexers](indexers#rss-vs-indexers) section on the indexers page for the full trade-off table.

## How it works

1. You add an RSS URL (`https://tracker.example/rss.php?uid=123&key=abc`)
2. Trove polls it on a configurable interval (default 10 minutes)
3. Each new entry is parsed and stored in the `rss_item` table with title, size, seeders, infohash, category, and published date
4. Retention cleanup removes items older than N days automatically
5. The `/search` page queries both live indexers AND your local RSS cache simultaneously
6. **Tasks** can read from RSS items via `kind: rss_items` input, which is what the AI agent generates for standing filter rules

## Adding a feed

On `/feeds`:

1. Click **Add feed**
2. Paste the full RSS URL including any authentication tokens (uid, passkey, rsskey)
3. Pick the **protocol** — torrent or usenet. This determines which download clients are compatible
4. Set **poll interval** (minimum 60 seconds)
5. Set **retention** (days, default 90)
6. Click **Preview feed** to fetch a live sample and verify the URL works — this shows the 10 most recent items before you save
7. Click **Save feed**

The scheduler starts polling immediately on the interval — the first fetch happens after one interval, not right away. Click the **Poll** button on the feed row to force an immediate fetch.

## Enable / disable

Each feed row has an inline **Enabled** / **Disabled** toggle button (Power icon). Disabling stops polling but keeps the feed configuration, the cached items, and the retention schedule intact — useful when you want to temporarily pause a feed (rate-limit issues, tracker maintenance) without deleting it. Toggle back on and polling resumes on the configured interval.

## Expanding a feed

Click a feed row on `/feeds` to expand it. You'll see a searchable table of all cached items with title, size, S/L, and publication time. Type in the search box to filter locally — this is much faster than running a full search since it queries only that feed's cache.

## Content categories

Every feed has a `protocol_hint` (torrent | usenet) and an optional `category_hint`. The category hint is used by task-engine filters — for example, an "all games" filter task only considers items from feeds tagged as `games`.

Supported categories:

- **movies** — film
- **tv** — TV episodes
- **music** — music albums
- **audiobooks** — spoken-word audio
- **books** — ebooks
- **comics** — comic archives
- **anime** — anime
- **games** — console and PC games
- **software** — applications, OS isos, utilities
- **other** — everything else

## Retention and cleanup

Each feed has its own `retention_days` setting. At the end of every poll, Trove deletes items older than that many days. This keeps the database bounded even if you poll high-volume feeds. The default is 90 days; you can raise it to keep a longer history or lower it to save disk space.

Global defaults for new feeds live in `/settings` → Defaults panel: `rss.default_retention_days` and `rss.default_poll_interval_seconds`. New feeds inherit these values if you don't override them in the add form.

## Typical feed sources

- **Private torrent trackers**: most have `/rss.php` or similar with a per-user token. Check your profile settings
- **Newznab indexers**: `/rss` or `/api?t=search&extended=1&rss=1&apikey=...`
- **Public announce feeds**: EZRSS clones, Torrentz backups

## Troubleshooting

- **"empty response"** → URL is wrong or tracker is down. Try it in a browser first
- **"parse: ..."** → server returned HTML instead of RSS. Usually means the URL redirects to a login page
- **0 items cached after several polls** → open the feed, check "last poll message", and use Preview to compare against what's expected
