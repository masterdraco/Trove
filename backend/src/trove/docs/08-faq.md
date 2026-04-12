---
title: FAQ & Troubleshooting
order: 8
description: Common issues, gotchas, and how to debug them.
---

# FAQ & Troubleshooting

## Where does Trove store data?

- **Database**: `config/trove.db` — SQLite, WAL-mode. Contains users, clients, indexers, feeds, cached RSS items, tasks, task run history, watchlist, AI cache, settings
- **Session secret**: `config/session.secret` — 48-byte random token generated on first run, used for session cookies AND credential encryption
- **Working data**: `data/` — temporary torrent/NZB files during processing

For proper backup and migration use the **[Backup & Restore](backup)** page — it produces a single zip with the DB + session secret + a manifest, and can restore it in one click on another host.

## I changed the AI model and chat still uses the old one

The effective AI config is read from the `app_setting` table. Save your changes in `/settings` → AI Assistant panel (click the **Save AI settings** button at the bottom of the panel). Refresh the `/ai` page and the header should show the new model name.

If it still doesn't work, your environment variables may be overriding the DB. Check `docker-compose.yml` for `TROVE_AI_MODEL=...` and remove it — env vars take priority for the `ai_enabled` flag only.

## My Transmission client works in the browser but Trove can't reach it

Most likely causes in order:

1. **Wrong URL** — Trove wants the web-interface URL, e.g. `http://192.168.0.10:9091`. Not the torrent-listen port (51413), not with a trailing `/transmission/rpc` (Trove appends that itself)
2. **RPC auth mismatch** — if you have `rpc-authentication-required: true` in settings.json, you need both username AND password in Trove
3. **RPC whitelist** — Transmission has an `rpc-whitelist` of allowed IPs. Either add Trove's host or set `rpc-whitelist-enabled: false`
4. **Firewall** — confirm the port is reachable: `curl http://<host>:9091` from the Trove host

## Task runs but accepts 0 releases every time

Turn on **Dry run** mode and expand the log in `/history` or on the task's detail panel. You'll see one line per release explaining *why* it was filtered out. Common reasons:

- `seeders<3` — your `min_seeders` is too high
- `no year in title` — the release title doesn't contain a 4-digit year and you have a `year_min` filter
- `kind:not-movie` — the release looks like a TV episode (has SxxExx) but `kind: movie` is set
- `missing:1080p` — the release title doesn't contain "1080p"
- `reject:cam` — the title contains a rejected token
- `title!=The Boys` — the hit's normalized title prefix doesn't match `require_title`. Common cause: the hit is a spinoff ("The Boys Presents Diabolical") or a different show whose episode title contains the words you searched for ("Fringe S05E11 The Boy Must Live"). If you actually want both, drop the `require_title` filter
- `no episode marker` — `require_episode: true` is set but the hit has no SxxExx (it's a season pack or full-show bundle)
- `already grabbed` — the dedup key matches an earlier `sent` row in `seen_release`. Wipe the relevant entries from the DB if you want to re-grab

Adjust the filters and dry-run again until accepted count is > 0.

If a TV-show task only finds 2-4 unique episodes when dozens exist on the indexer, the cause is almost always that the watchlist promote didn't have a TMDB id to bake in. Open the task config and add `tmdb_id: <id>` to the search input — the engine will automatically iterate `season=1..N` on the indexer and backfill all available seasons. See the [Tasks](tasks) doc for the full shape.

## "Empty response" when testing an indexer

The URL is probably wrong. Common mistakes:

- Including `/api` twice (Trove appends `/api` automatically, except when the URL already ends with `/api`)
- Pointing at a web UI page instead of the API root
- Using `http://` when the indexer requires HTTPS (Trove follows redirects but some indexers just return empty body on plain HTTP)

Sanity check: `curl 'https://api.example.com/api?t=caps&apikey=YOUR_KEY'` — it should return XML starting with `<?xml`. If it returns HTML or is empty, your URL is wrong.

## I see the onboarding wizard every time I log in

Probably means `flexreplace_onboarding_dismissed` / `trove_onboarding_dismissed` isn't being saved to localStorage. Check if your browser is blocking storage for the origin, or in private-browsing mode.

To force-dismiss, open DevTools → Application → Local Storage → set `trove_onboarding_dismissed` to `"1"`.

## Scheduler runs tasks but the AI chat is broken

AI and scheduler are independent. If the AI test button fails but tasks still run, it means:

- Ollama is unreachable (wrong endpoint, server down, model not installed)
- The `ai.enabled` setting is off
- The `TROVE_AI_ENABLED=false` env var is set (overrides DB)

Go to `/settings` → AI Assistant → click **Test connection**. The error message tells you exactly what litellm sees.

## Docker container keeps restarting

Check logs: `docker compose logs -f trove`. Most common startup errors:

- **Database migration failed** — usually from a mid-upgrade crash. Back up `config/trove.db`, then run `docker compose run --rm trove uv run alembic upgrade head` to manually apply migrations
- **Port already in use** — another service is on 8000. Change the `ports:` mapping in compose
- **Permission denied on /config** — volume mount permissions. Make sure the host `config/` directory is writable by the container user

## How do I back up and restore?

**Use the UI** — see the dedicated **[Backup & Restore](backup)** guide. In short: Settings → Backup & restore → **Download .zip** on the old host, **Restore from backup** on the new host. Everything comes across including credentials.

If you prefer the manual route, the whole `config/` directory is self-contained — copy it across, preserve the `0600` permission on `session.secret`, and start the container. But the UI route is safer because it checkpoints the WAL, validates checksums, and handles the scheduler restart for you.

The `data/` directory is transient — no need to back it up.

## My torrent client doesn't have a "category" but Trove keeps sending empty category

Harmless. Categories are a SABnzbd / NZBGet concept. For Transmission and Deluge they map to labels if the label plugin is installed; otherwise they're silently ignored.
