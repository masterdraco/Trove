---
title: Plex library check
order: 16
description: Flag movies and TV shows you already own so you stop re-downloading.
---

# Plex library check

When Plex is configured, Trove shows a **✓ Plex** badge on every title that's already in your library. Badges appear on:

- **Discover** — posters on trending / popular / upcoming / on-air / search, plus the detail modal.
- **Browse** — Movies, TV, and Anime tabs (next to the TMDB match badge and as an overlay on the poster thumbnail).
- **Watchlist** — movie cards.

Lets you avoid promoting or grabbing what you already own.

## Setup

Fill in two settings under **Settings → plex**:

| Setting | Value |
|---|---|
| `plex.url` | Base URL of your server, e.g. `http://192.168.0.100:32400` |
| `plex.token` | Your X-Plex-Token |

Finding the token: open any file in Plex Web, click **ⓘ → View XML**, and grab the `X-Plex-Token=...` value from the URL. [Full guide from Plex](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

Verify it works by hitting `POST /api/library/plex/test` from the API browser (or watch for badges on /discover after a refresh).

## How matching works

For each Movie or TV show Trove wants to check, it tries in order:

1. **Exact GUID match** — asks Plex `/library/all?type=1&guid=tmdb://<id>` (type=2 for TV). Works when your library is scraped with the TMDB agent, which is the modern default.
2. **Title + year fallback** — queries `/search?query=<title>`, accepts a match within ±1 year to absorb production-vs-release date drift.

Results are cached for 5 minutes, so a fresh Discover page load only hits Plex once per unique title. If Plex isn't configured, every check short-circuits to `False` at basically zero cost.

## Scope

- **Movies**: checked on Discover, Browse (Movies tab), Watchlist, and the Browse detail links.
- **TV shows**: checked on Discover and Browse (TV / Anime tabs). A show counts as "in library" if Plex has the show at all — Trove doesn't currently compare season coverage (so a show with only S01 in Plex will still flag when S03 is available on an indexer).
- **Games / apps / music / books**: not checked — Plex doesn't have a unified catalog for these.

Jellyfin and Kodi aren't wired up yet — open an issue if you need them.
