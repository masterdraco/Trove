---
title: Getting started
order: 1
description: Install Trove, create your admin account, and connect your first sources.
---

# Getting started

Welcome to **Trove** — a modern FlexGet replacement with search, RSS caching, task automation and an optional AI assistant. This guide walks you through the 5-minute setup.

## Install

The recommended way to run Trove is with Docker Compose. From the project root:

```bash
docker compose up -d
```

This publishes port **8000** on all network interfaces, so Trove is reachable from any device on your LAN at `http://<server-ip>:8000`. On first run, Trove automatically generates a random session secret and stores it in `./config/session.secret` — back that file up together with `./config/trove.db`.

If you want to limit access to a single interface, change the `ports` mapping in `docker-compose.yml` to something like `"192.168.0.50:8000:8000"`.

For remote access, put a reverse proxy (Caddy, Traefik, nginx) with HTTPS in front of Trove.

## Create your admin account

Open your browser and navigate to `http://<server-ip>:8000`. The first time you visit, you'll see a **setup wizard** asking you to create an admin account. Pick a username and a strong password — they're the only credentials for Trove, so don't lose them.

After creating the account, you'll be redirected to a guided onboarding flow that walks you through adding:

1. **Download clients** — Deluge, Transmission, SABnzbd, or NZBGet
2. **Indexers** — Newznab/Torznab APIs for searching
3. **AI check** — verify the local Ollama connection (optional)

You can add more clients and indexers on the same step before moving forward — the "Add another" button resets the form while keeping the previously-saved entries visible.

## Next steps

Once setup is done, check the other docs in this sidebar for details on each feature:

- [Download clients](clients) — how to configure Deluge, Transmission, SABnzbd, NZBGet
- [Indexers](indexers) — Newznab, Torznab, Cardigann
- [RSS Feeds](feeds) — poll tracker RSS and build a searchable local cache
- [Tasks](tasks) — YAML format, filters, scheduling
- [AI Assistant](ai-agent) — natural-language commands that create tasks for you
- [Backup & Restore](backup) — snapshot your install and migrate to another host

## LAN access troubleshooting

If you can't reach Trove from another device:

- Make sure your firewall allows inbound TCP 8000 on the Trove host
- Verify the container is published on `0.0.0.0:8000` (that's the default)
- Check that your LAN devices can actually reach the Trove host (`ping <trove-host>`)
