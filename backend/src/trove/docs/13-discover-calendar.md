---
title: Discover & Calendar
order: 13
description: Browse TMDB for movies and TV shows, and track release dates on a calendar.
---

# Discover

The **Discover** page lets you browse trending, popular, and upcoming releases from TMDB and add them to your watchlist with one click.

## Tabs

| Tab | Source | Content |
|---|---|---|
| Trending | TMDB trending (week) | All media, sorted by current popularity |
| Popular movies | TMDB popular movies | All-time popular movies |
| Popular TV | TMDB popular TV | All-time popular TV shows |
| Upcoming movies | TMDB discover (date filter) | Movies releasing from today to 6 months ahead |
| On the air | TMDB on-the-air TV | TV shows currently airing new episodes |

## Per-page selector

Use the **10 / 20 / 50 / 100** buttons next to the tabs to control how many results are shown. TMDB returns 20 per page internally — when you request more, Trove fetches multiple pages and merges the results.

## Adding to watchlist

Click any poster to open the detail view with overview, genres, rating, and release date. Click **Add to watchlist** to create a watchlist entry. Items already on your watchlist show a green checkmark instead.

## Setup

Discover requires a TMDB API read token. Get one for free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) (look for "API Read Access Token v4") and paste it in **Settings → TMDB**.

---

# Calendar

The **Calendar** page shows a Sonarr-style month grid with release dates for everything on your watchlist.

## What it shows

- **Movies** — release date from the watchlist entry (originally from TMDB)
- **TV series** — per-episode air dates fetched live from TMDB. Shows the current season's episodes plus the next season (if announced)

## Grab state

Each event is color-coded:

| State | Meaning |
|---|---|
| **Pending** | Release date is in the future, not grabbed yet |
| **Grabbed** | Trove has already sent this episode/movie to a client |
| **Missed** | Release date has passed and Trove hasn't grabbed it |

Grab state is determined by matching the calendar event's dedup key (same format as the task engine uses: `e:show:s01e01` for TV, `m:title:year` for movies) against the `seen_release` table.

## Navigation

Use the **< >** arrows to move between months. Click **Today** to jump back to the current month.

## Requirements

- Items must be on your **watchlist** to appear on the calendar
- TMDB must be configured (same token as Discover)
- TV series need a `tmdb_id` and `tmdb_type=tv` on the watchlist entry (set automatically when adding via Discover)
