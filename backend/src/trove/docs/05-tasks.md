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
| `min_seeders` | int | Drop if seeders < N |
| `min_size_mb` | int | Drop if size < N MB |
| `max_size_mb` | int | Drop if size > N MB |
| `year_min` | int | Parse year from title; drop if year < N |
| `year_max` | int | Parse year from title; drop if year > N |
| `kind` | string | `movie` or `series`; rejects the wrong type (uses SxxExx detection) |
| `categories` | list | Only accept items whose category matches one of these |
| `require` | list | Each token must appear in title (case-insensitive) |
| `reject` | list | None of these tokens may appear in title |

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

If you want to "forget" the history for a task (e.g., after changing filters drastically), delete the task and recreate it with the same config. Or ask in the forum for a `trove seen clear` helper — it's on the roadmap.

## Complete example — weekly TV

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
