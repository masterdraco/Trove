---
title: Downloads
order: 12
description: Monitor active and completed downloads across all clients in real time.
---

# Downloads

The **Downloads** page (`/downloads` in the sidebar) gives you a live overview of every release Trove has sent to your download clients. It shows progress bars, transfer sizes, ETA, quality tier, and which task/client each download belongs to.

## What you see

Each download card shows:

- **Status icon** — downloading (pulsing), queued (clock), completed (check), failed (X), verifying (spinner)
- **Title** — the release name as the client sees it
- **Quality tier badge** — 2160p, 1080p, 720p, or SD (color-coded)
- **Task name** — which task grabbed it
- **Client name** — which download client has it (Transmission, Deluge, SABnzbd, NZBGet)
- **Size** — downloaded / total bytes
- **ETA** — estimated time remaining (downloading only)
- **Progress bar** — visual percentage (hidden when completed)
- **Error message** — shown for failed downloads

## Filters

Use the filter buttons at the top to narrow down:

- **All** — everything
- **Downloading** — active transfers
- **Queued** — waiting to start
- **Completed** — finished successfully
- **Failed** — something went wrong

## Auto-refresh

The page polls the API every 10 seconds automatically. Click **Refresh** to force an immediate update.

## How it works

The data comes from the **download state poller** — a background job that runs every 60 seconds. It checks every recent `seen_release` row (outcome=sent, within the last 48 hours) against its download client via the client's API. State transitions (queued → downloading → completed) are recorded and trigger notifications.

The `/api/downloads` endpoint joins `seen_release` with `task` and `client` tables to give you the full picture in one query.
