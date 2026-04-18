---
title: Browse
order: 14
description: See the newest releases on your indexers, enriched with Steam/TMDB lookups.
---

# Browse

The **Browse** page shows what just landed on your indexers — no search query needed. It fans out a keyword-less request across every enabled indexer and sorts the combined result by publish date, so the top of each tab is whatever's freshest from your usenet and torrent sources right now.

## Tabs

| Tab | Backed by | Enrichment |
|---|---|---|
| Movies | TMDB category | TMDB poster + rating + year |
| TV | TMDB category | TMDB poster + SxxExx chip |
| Anime | TMDB (TV) | TMDB poster + SxxExx chip |
| Games | Newznab `cat=1000/4050`, UNIT3D/RarTracker sections | Steam store lookup |
| Apps | Newznab `cat=4000`, tracker "apps" section | Google search link |

Each row renders the raw release title plus a metadata badge that links to the matching catalog entry. For movies and games the badge includes a confidence score:

- **Strong** (≥75%) — shown in primary colour, clearly linked to the catalog item
- **Maybe** (40–75%) — shown in yellow; click through to verify it's the right title
- **Below 40%** — no badge; a plain "Search Steam / TMDB" link is shown instead

The title cleaner strips release group tags (`-FitGirl`, `-RARBG`, …), version numbers, quality markers, and bracketed noise before querying the catalog. Most mainstream releases match on the first attempt.

## Release groups

The badge next to each title shows the parsed release group. You can colour-code groups you trust or want to avoid in **Settings → preferences**:

- **Trusted release groups** — comma-separated list. Matching rows get a green chip.
- **Blocked release groups** — comma-separated list. Matching rows are hidden by default; a "Show N from blocked groups" toggle reveals them.

Case insensitive. Example: `FitGirl, DODI, RARBG, SubsPlease`.

## Plex integration

When Plex is configured (see the *Plex library* page), Movies/TV/Anime rows that already exist in your library get a small green **✓ In Plex** badge next to the TMDB match — and a ✓ Plex overlay on the poster thumbnail. Lets you avoid downloading what you already own.

## Browse limitations

- Drivers that reject empty searches (some older Newznab installs, many Cardigann site definitions) show up in a yellow banner at the top of the page with the exact error from the indexer. The rest of your enabled indexers still load.
- Results are limited to 50 items per tab. Refresh re-fans-out the requests.
- Steam matches cache for 24h; TMDB for 6h; Plex presence for 5 min. Clear the `external_cache` namespace via SQL if you need to bust them manually.
