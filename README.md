# Trove

A modern replacement for FlexGet with built-in multi-tracker search, Usenet support, a polished web UI, and optional local AI assistance.

## Features

- **Multi-tracker search** across torrent trackers (Cardigann-compatible) and Usenet indexers (Newznab/Torznab) — no Prowlarr/Jackett required.
- **Download client integration**: Deluge, Transmission, SABnzbd, NZBGet.
- **Task engine**: input → filter → output pipeline with cron scheduling, dry-run, and per-release trace.
- **Modern web UI** (SvelteKit + shadcn-svelte) — everything configurable from the browser.
- **Optional AI layer** via [litellm](https://github.com/BerriAI/litellm) — default configured for Ollama. Used for query expansion, result ranking, fuzzy title matching, and a "why didn't X download?" chat.
- **Torznab export** so Sonarr/Radarr can use Trove as their indexer.

## Status

Early development — functional but not yet stable. See the in-app docs at `/docs` after first boot for feature walkthroughs.

## Quick start (Docker)

```bash
docker compose up -d
```

Then open http://localhost:8000 (or http://<host-ip>:8000 from any other
device on your LAN) and complete the setup wizard.

### LAN access

By default Docker publishes port 8000 on all interfaces, so Trove is
reachable from every device on your local network. On first run a random
session secret is generated and stored in `./config/session.secret` — back
it up together with `./config/trove.db`.

If you want to lock the service to a single interface, change the `ports`
mapping in `docker-compose.yml` to e.g. `"192.168.0.50:8000:8000"`. For
remote/Internet access, put a reverse proxy (Caddy, Traefik, nginx) with
HTTPS in front of the container.

## Development

Backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn trove.main:app --reload
```

Frontend:

```bash
cd web
pnpm install
pnpm dev
```

The Svelte dev server proxies `/api/*` to `http://localhost:8000`.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
