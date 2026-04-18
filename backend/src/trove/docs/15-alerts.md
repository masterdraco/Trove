---
title: Alerts
order: 15
description: Save a browse query and get notified when new releases match.
---

# Alerts

The **Alerts** page lets you save a browse query — category plus optional keywords — and receive a notification the moment a new release matches. Think of it as "RSS for a specific thing you care about" without wiring a dedicated feed.

## How it works

Every 5 minutes a background sweeper walks each enabled alert:

1. Re-runs the browse fan-out for the alert's category.
2. Filters the hits by the alert's keywords (case-insensitive substring match; OR between comma-separated terms).
3. Diffs the current matching titles against the last 200 it saw for this alert.
4. Dispatches one `alert.new_match` notification per genuinely new title.

Alerts with a custom `check_interval_minutes` (default 30) are simply skipped on sweeper ticks where they're not due yet — so you can set some alerts to check every 10 min and others every 6 hours without burning indexer quota.

## Creating an alert

Go to **Alerts → New alert** and fill in:

| Field | Meaning |
|---|---|
| Name | Your label. Shown in notifications. |
| Category | One of the browse tabs (movies, tv, games, software, …). |
| Keywords | Comma-separated, e.g. `elden ring, shadow of the erdtree`. Empty = match everything in the category. |
| Protocol | Optional — restrict to `torrent` or `usenet`. |
| Check every | How often the sweeper runs this alert (5–1440 min). |
| Enabled | Paused alerts still exist but aren't swept. |

Click **Run** on the alert list to trigger a sweep manually — useful for verifying keywords before you wait for the next scheduled tick.

## Notifications

Alerts re-use the same notification providers as tasks and downloads. Whatever Discord webhook / Telegram bot / ntfy topic / generic webhook is subscribed to the `alert.new_match` event will receive one notification per new release, including the title, your alert name, size, and (when parsed) the release group.

Configure providers under **Settings → Notifications** — same page as for download and task events.
