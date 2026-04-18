#!/usr/bin/env bash
#
# Trove self-update script.
#
# Invoked from POST /api/system/update as a detached subprocess. Runs in
# one of two modes depending on environment:
#
#   source mode   running from a git checkout, e.g. 'uv run uvicorn …':
#                 git pull → uv pip install → alembic → web build → restart uvicorn
#
#   docker mode   running inside a container with docker.sock mounted:
#                 spawn a short-lived helper container that runs
#                 'docker compose pull + up -d' from the host's compose
#                 working directory. The helper survives when the trove
#                 container is replaced, so the update actually completes.
#
# The mode is auto-detected — presence of /.dockerenv or
# /proc/1/cgroup markers → docker, otherwise → source.
#
# Log lines go to /tmp/trove-update.log so the user can tail progress.

set -euo pipefail

LOG=/tmp/trove-update.log

log() {
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "$LOG"
}

running_in_container() {
    [[ -f /.dockerenv ]] && return 0
    if grep -qE '(docker|containerd|kubepods|podman)' /proc/1/cgroup 2>/dev/null; then
        return 0
    fi
    return 1
}

run_source_update() {
    local repo_dir script_dir port
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    repo_dir="$(cd "$script_dir/.." && pwd)"
    port=${PORT:-8000}

    log "==== trove source update started ===="
    log "repo: $repo_dir"

    export PATH="$HOME/.local/bin:$PATH"

    local old_pids
    old_pids=$(pgrep -f "uvicorn trove.main:app" || true)
    log "running uvicorn pids: ${old_pids:-none}"

    cd "$repo_dir"

    log "fetching from origin…"
    git fetch origin main >> "$LOG" 2>&1

    log "resetting to origin/main…"
    git reset --hard origin/main >> "$LOG" 2>&1

    log "installing backend deps…"
    cd "$repo_dir/backend"
    uv pip install --upgrade -e ".[dev]" >> "$LOG" 2>&1

    log "running alembic migrations…"
    uv run alembic upgrade head >> "$LOG" 2>&1

    log "installing web deps…"
    cd "$repo_dir/web"
    pnpm install --no-frozen-lockfile >> "$LOG" 2>&1

    log "building web…"
    pnpm build >> "$LOG" 2>&1

    log "copying static into backend…"
    rm -rf "$repo_dir/backend/src/trove/static"
    cp -r "$repo_dir/web/build" "$repo_dir/backend/src/trove/static"

    log "stopping old uvicorn…"
    if [[ -n "$old_pids" ]]; then
        for pid in $old_pids; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        for _ in $(seq 1 30); do
            if ! ss -ltn 2>/dev/null | grep -q ":$port "; then
                break
            fi
            sleep 0.5
        done
        for pid in $old_pids; do
            if kill -0 "$pid" 2>/dev/null; then
                log "force-killing $pid"
                kill -KILL "$pid" 2>/dev/null || true
            fi
        done
    fi

    log "starting new uvicorn…"
    cd "$repo_dir/backend"
    setsid nohup uv run uvicorn trove.main:app \
        --host 0.0.0.0 \
        --port "$port" \
        >> /tmp/trove.log 2>&1 < /dev/null &

    log "==== source update complete ===="
}

run_docker_update() {
    log "==== trove docker update started ===="

    if ! command -v docker >/dev/null 2>&1; then
        log "ERROR: docker CLI not found in container"
        log "Rebuild the image with docker-cli installed."
        exit 1
    fi

    if ! docker version --format '{{.Server.Version}}' >> "$LOG" 2>&1; then
        log "ERROR: cannot reach docker daemon"
        log "Mount /var/run/docker.sock into the trove container to enable self-update."
        exit 1
    fi

    # Find ourselves and our compose labels. The cgroup trick gives us
    # our own container ID reliably regardless of HOSTNAME overrides.
    local self_id
    self_id=$(cat /etc/hostname 2>/dev/null || true)
    if [[ -z "$self_id" ]]; then
        log "ERROR: cannot determine own container id"
        exit 1
    fi

    local workdir project service image
    workdir=$(docker inspect "$self_id" -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)
    project=$(docker inspect "$self_id" -f '{{ index .Config.Labels "com.docker.compose.project" }}' 2>/dev/null || true)
    service=$(docker inspect "$self_id" -f '{{ index .Config.Labels "com.docker.compose.service" }}' 2>/dev/null || true)
    image=$(docker inspect "$self_id" -f '{{ .Config.Image }}' 2>/dev/null || true)

    log "self: $self_id"
    log "compose workdir (host): ${workdir:-<missing>}"
    log "compose project:         ${project:-<missing>}"
    log "compose service:         ${service:-<missing>}"
    log "current image:           ${image:-<missing>}"

    if [[ -z "$workdir" || -z "$project" || -z "$service" ]]; then
        log "ERROR: container is not compose-managed (missing compose labels)"
        log "Start trove via 'docker compose up -d' for self-update to work."
        exit 1
    fi

    # Spawn a detached helper container. It:
    #   1. bind-mounts the host's compose working dir at /work
    #   2. uses the same docker socket to drive the update
    #   3. waits a moment so our HTTP response returns before we get killed
    #   4. pulls + restarts our service
    #
    # The helper is --rm so it cleans itself up; docker:27-cli ships with
    # both 'docker' and 'docker compose'.
    local helper
    helper="trove-updater-$(date +%s)"

    log "launching helper container: $helper"
    docker run --rm --detach \
        --name "$helper" \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "$workdir:/work" \
        -w /work \
        --entrypoint /bin/sh \
        docker:27-cli \
        -c "
            set -e
            echo '[helper] sleeping 3s so the HTTP response flushes…'
            sleep 3
            echo '[helper] docker compose pull $service (project=$project)'
            docker compose -p '$project' pull '$service'
            echo '[helper] docker compose up -d $service'
            docker compose -p '$project' up -d '$service'
            echo '[helper] done'
        " >> "$LOG" 2>&1

    log "helper running as $helper — this container will be replaced shortly"
    log "==== docker update handoff complete ===="
}

if running_in_container; then
    run_docker_update
else
    run_source_update
fi
