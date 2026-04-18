---
title: Self-update
order: 17
description: How the in-app "Update now" button works in Docker and source installs.
---

# Self-update

Trove checks GitHub for a newer release every 30 minutes and shows an **Update available** chip in Settings when the running version is behind. Click **Update now** and Trove upgrades itself in place — no SSH required.

The flow is different depending on how Trove was installed. Settings reports the detected install type (*docker*, *source*, or *unknown*) below the update button.

## Docker (ghcr.io image)

This is the default path from v0.10.1 onwards. `docker-compose.yml` uses the published image `ghcr.io/masterdraco/trove:latest`, and the container has the Docker socket mounted:

```yaml
services:
  trove:
    image: ghcr.io/masterdraco/trove:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      # …plus your ./config and ./data mounts
```

When you click **Update now**:

1. The backend spawns `scripts/update.sh` inside the container. It detects the container environment and switches to docker mode.
2. The script reads the compose labels on its own container (`com.docker.compose.project.working_dir`, `project`, `service`) to find where the compose file lives on the host.
3. It launches a short-lived helper container (`docker:27-cli`) with the host's compose directory bind-mounted and the same socket forwarded.
4. The helper sleeps 3 seconds so the HTTP response to the browser can flush, then runs `docker compose pull` + `docker compose up -d` for the `trove` service.
5. Docker replaces the trove container with one running the new image. The helper keeps running after trove dies because it lives in its own container.
6. The frontend polls `/api/health` every 2 s; once the reported version changes, it reloads the page.

Why the helper container? If the script tried to do `docker compose up -d` directly from inside trove, Docker would kill our process (the one running the script) the moment it replaces our container. The helper is detached so the update actually finishes.

**Prerequisites:**
- `/var/run/docker.sock` must be mounted (the default compose file does this).
- The image must include the Docker CLI (v0.10.1+ ships with it).
- The container must be started via `docker compose` (not `docker run …`) — the helper relies on compose labels.

If any prerequisite is missing, the Update button is disabled and Settings shows a specific blocker message.

**Security note:** Mounting the Docker socket grants root-equivalent access to the host. It's safe for a single-user hjemmelab; do not mount it in multi-tenant deployments. To opt out, comment out the socket mount in `docker-compose.yml` and upgrade manually instead:

```bash
cd <your trove checkout>
git pull
docker compose pull
docker compose up -d
```

## Source (git checkout)

If you run Trove directly via `uv run uvicorn trove.main:app` (typical for development), the same button does:

1. `git fetch origin main && git reset --hard origin/main`
2. `uv pip install --upgrade -e ".[dev]"` to pick up new backend deps
3. `uv run alembic upgrade head` to apply any new migrations
4. `pnpm install && pnpm build` for the web UI
5. Copy the web build into `backend/src/trove/static`
6. Gracefully stop the current uvicorn process, then start a fresh one

The script is spawned with `start_new_session=True` so it survives the uvicorn kill in step 6.

**Prerequisites:**
- `uv`, `pnpm`, and `git` on PATH
- `scripts/update.sh` executable
- The uvicorn process must match `pgrep -f "uvicorn trove.main:app"`

## Other installs (pip / wheel)

If Trove was installed into a venv via `pip install trove`, self-update is disabled. There's no git checkout to pull and no container to replace. Upgrade via your package manager: `pip install --upgrade trove` and restart however you started the process.

## Troubleshooting

**Update button is greyed out.** Hover over it to see the tooltip, or check Settings for the blocker message under the button. The usual causes:
- Docker mode without the socket mounted — add it to `docker-compose.yml` and restart.
- Older image that doesn't ship the Docker CLI — `docker compose pull && up -d` once to get v0.10.1+, then the button works.

**Update started but never finished.** Check `/tmp/trove-update.log` inside the container (or on the host, for source installs). In docker mode, also check the helper container's logs: `docker logs trove-updater-<timestamp>` — the name is timestamped because multiple upgrades could overlap.

**New image pulls but compose doesn't restart.** The helper uses the compose project name from the container labels. If you started Trove with a custom project (`docker compose -p myname …`), make sure the helper can see that project — currently it does, by reading the label `com.docker.compose.project`.

**Want automatic updates instead of a button.** Point [Watchtower](https://containrrr.dev/watchtower/) at the trove container:

```yaml
services:
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --label-enable --interval 3600

  trove:
    labels:
      - com.centurylinklabs.watchtower.enable=true
    # …rest as usual
```

Watchtower polls ghcr hourly and replaces Trove whenever a new image is published. The in-app Update button still works alongside it.
