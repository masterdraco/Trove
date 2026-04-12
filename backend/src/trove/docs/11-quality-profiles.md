---
title: Quality Profiles
order: 11
description: Customize how Trove ranks releases — quality tiers, source weights, codec bonuses, and reject tokens.
---

# Quality Profiles

A **quality profile** is a named bundle of ranking weights that the task engine uses to score and sort releases. When a task references a profile, the engine uses its quality tiers, source tiers, codec bonuses, and reject tokens instead of the built-in defaults.

Profiles are managed from **Settings → Quality Profiles** in the sidebar.

## How scoring works

Every release title is scored by `score_hit()`:

| Factor | Weight | Example |
|---|---|---|
| Quality tier | `tier * 100` | 2160p (tier 4) = 400 pts |
| Preferred quality bonus | `+500` | If title contains `prefer_quality` value |
| Source tier | `tier * 30` | Remux (tier 6) = 180 pts |
| Codec bonus | `bonus * 10` | x265 (bonus 2) = 20 pts |
| Size (relative) | up to `20` | Proportional to max_size_mb |
| Seeders (torrent) | `log1p(seeders) * 5` | 100 seeders = ~24 pts |

The release with the highest total score is grabbed first.

## Default profile

Trove ships with `default-2160p` which prefers 4K content:

- **Quality tiers**: 2160p/4k/uhd=4, 1080p=3, 720p=2, sd/480p/576p=1
- **Source tiers**: remux=6, bluray=5, web-dl=4, webrip=3, hdtv=2, dvdrip=1, cam=-10
- **Codec bonus**: x265/hevc=2, x264=1
- **Reject tokens**: cam, telesync, hdcam, workprint
- **Prefer quality**: 2160p

This profile cannot be deleted but can be edited.

## Creating a profile

1. Go to **Settings → Quality Profiles**
2. Click **New profile**, enter a name
3. Adjust tiers, bonuses, and reject tokens
4. Click **Save**

## Using in a task

Reference the profile name in your task YAML:

```yaml
filters:
  quality_profile: "my-profile"
```

The profile's `reject_tokens` are merged with any `reject:` list in the task's filters. Its `prefer_quality` overrides the task-level `prefer_quality` if both are set.

## Quality tiers explained

The tier number is used both for ranking and for the **upgrade cutoff** (see below). Higher = better:

| Tier | Resolutions |
|---|---|
| 4 | 2160p, 4K, UHD |
| 3 | 1080p |
| 2 | 720p |
| 1 | 480p, 576p, SD |
| 0 | Unknown / not detected |

## Quality upgrade path

Tasks can automatically **replace** a previously-grabbed release with a better one. This is opt-in per task:

```yaml
filters:
  quality_profile: "default-2160p"
  enable_upgrades: true
  upgrade_until_tier: 4       # stop upgrading once you have 2160p
  max_upgrades_per_run: 3     # safety throttle
```

### How upgrades work

On each task run, when the engine finds a hit for a key that's already been grabbed:

1. **Score comparison** — is the new hit's `score_hit()` better than the existing grab's stored score?
2. **Tier cutoff** — is the existing grab's quality tier still below `upgrade_until_tier`?
3. **Throttle** — have we done fewer than `max_upgrades_per_run` upgrades this run?

If all three pass:

- The old release is **removed from the download client** (files deleted)
- The new release is **sent to the client**
- The old seen_release row is marked `outcome=upgraded`
- A `task.upgraded` notification is fired

### Safety features

- **Per-task opt-in** — upgrades never happen unless `enable_upgrades: true` is in the YAML
- **Tier cutoff** — once you have the target quality, the engine stops looking
- **Max per run** — `max_upgrades_per_run` (default 3) prevents runaway replacement storms
- **Dry run** — test with dry run first to see what WOULD be upgraded without touching anything
- **Notifications** — every upgrade fires a `task.upgraded` event so you know what happened

### Example upgrade scenario

1. Task grabs `Movie.2026.720p.WEB-DL` (tier 2, score 280)
2. Next run finds `Movie.2026.1080p.BluRay.x265` (tier 3, score 590)
3. Since tier 2 < `upgrade_until_tier: 4` and score 590 > 280:
   - Removes 720p from Transmission
   - Sends 1080p BluRay to Transmission
   - Fires upgrade notification
4. Later run finds `Movie.2026.2160p.Remux` (tier 4, score 920)
   - Same process, replaces 1080p with 2160p
5. Next run: tier 4 >= `upgrade_until_tier: 4` → skips, target quality reached
