# syntax=docker/dockerfile:1.7

# ---- Stage 1: build Svelte UI ----
FROM node:20-alpine AS web-builder
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store && \
    (pnpm install --frozen-lockfile || pnpm install)
COPY web/ .
RUN pnpm build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy \
    TROVE_CONFIG_DIR=/config \
    TROVE_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI (no daemon) lifted from the official image, so the
# self-update flow can drive 'docker compose pull + up -d' via the
# host socket mounted at /var/run/docker.sock. Not required for normal
# operation — safe to remove in security-sensitive deployments.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# pyproject.toml references ../README.md, so the README must be present
# at /app/README.md before we install. Copy it first, then the backend
# source, then install in editable mode.
COPY README.md ./README.md
COPY backend/ ./backend/
RUN cd backend && uv pip install --system -e .

# The self-update flow looks for scripts/update.sh by walking up from
# __file__; shipping the scripts next to the backend makes it reachable.
COPY scripts/ ./scripts/
RUN chmod +x /app/scripts/*.sh

# Copy built web assets into the Python package's static dir
COPY --from=web-builder /web/build /app/backend/src/trove/static

WORKDIR /app/backend

VOLUME ["/config", "/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn trove.main:app --host 0.0.0.0 --port 8000"]
