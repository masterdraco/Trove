#!/usr/bin/env bash
#
# Trove self-update script.
#
# Invoked from POST /api/system/update as a detached subprocess. Runs
# the full update sequence: git pull → backend deps → alembic → web
# build → static copy → graceful uvicorn restart.
#
# Environment variables (TROVE_*) are inherited from the backend
# process that spawned this script, so the new uvicorn gets the same
# config (database path, AI endpoint, etc.).
#
# Log lines go to /tmp/trove-update.log so the user can tail the
# progress if something goes wrong.

set -euo pipefail

LOG=/tmp/trove-update.log
PORT=${PORT:-8000}

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"
}

# Resolve repo root from the script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

log "==== trove update started ===="
log "repo: $REPO_DIR"

export PATH="$HOME/.local/bin:$PATH"

# Capture the PID of the currently-running uvicorn so we can kill it
# after the build is ready. There may be a parent bash wrapper + a
# Python process — kill them both.
OLD_PIDS=$(pgrep -f "uvicorn trove.main:app" || true)
log "running uvicorn pids: ${OLD_PIDS:-none}"

cd "$REPO_DIR"

log "fetching from origin…"
git fetch origin main >> "$LOG" 2>&1

# Nuclear reset — we want to match origin/main exactly
log "resetting to origin/main…"
git reset --hard origin/main >> "$LOG" 2>&1

log "installing backend deps…"
cd "$REPO_DIR/backend"
uv pip install --upgrade -e ".[dev]" >> "$LOG" 2>&1

log "running alembic migrations…"
uv run alembic upgrade head >> "$LOG" 2>&1

log "installing web deps…"
cd "$REPO_DIR/web"
pnpm install --no-frozen-lockfile >> "$LOG" 2>&1

log "building web…"
pnpm build >> "$LOG" 2>&1

log "copying static into backend…"
rm -rf "$REPO_DIR/backend/src/trove/static"
cp -r "$REPO_DIR/web/build" "$REPO_DIR/backend/src/trove/static"

log "stopping old uvicorn…"
if [ -n "$OLD_PIDS" ]; then
    for pid in $OLD_PIDS; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    # Wait up to 15s for graceful shutdown + port release
    for i in $(seq 1 30); do
        if ! ss -ltn 2>/dev/null | grep -q ":$PORT "; then
            break
        fi
        sleep 0.5
    done
    # Force-kill if still alive
    for pid in $OLD_PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            log "force-killing $pid"
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
fi

log "starting new uvicorn…"
cd "$REPO_DIR/backend"
# setsid + nohup so the new process outlives this script
setsid nohup uv run uvicorn trove.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    >> /tmp/trove.log 2>&1 < /dev/null &

log "==== update complete ===="
