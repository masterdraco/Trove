"""System-level endpoints: version info, update checks, self-update."""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from trove import __version__
from trove.api.deps import current_user
from trove.config import get_settings
from trove.models.user import User

log = structlog.get_logger()

router = APIRouter()

GITHUB_OWNER = "masterdraco"
GITHUB_REPO = "Trove"
GITHUB_API = "https://api.github.com"
PYPROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


Environment = Literal["docker", "source", "unknown"]


class UpdateCheck(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    source: str | None
    release_notes: str | None
    release_url: str | None
    checked_at: float
    error: str | None = None
    environment: Environment = "unknown"
    # True when POST /api/system/update is expected to succeed. False when
    # we detect a missing prerequisite (e.g. docker mode without socket
    # mounted) so the UI can explain what to do instead of offering a
    # button that fails.
    update_ready: bool = False
    # Human-readable reason when update_ready is False.
    update_blocker: str | None = None


@dataclass
class _CacheEntry:
    result: UpdateCheck
    ts: float


_CACHE: _CacheEntry | None = None
_CACHE_TTL = 30 * 60  # 30 minutes

_ENVIRONMENT: Environment | None = None


def _find_repo_root() -> Path | None:
    """Walk upward from this file until we find .git or scripts/update.sh."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        script = parent / "scripts" / "update.sh"
        if script.is_file():
            return parent
    return None


def _running_in_container() -> bool:
    """Heuristic: are we inside a Docker/OCI container? Cheap syscalls only."""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except OSError:
        return False
    return any(marker in cgroup for marker in ("docker", "containerd", "kubepods", "podman"))


def _detect_environment() -> Environment:
    """Decide whether self-update is possible.

    ``source``  running from a host checkout we can git-pull —
                scripts/update.sh is reachable AND we're not in a container.
    ``docker``  running inside a container (scripts/ is copied in by the
                image build); update runs via docker socket + helper.
    ``unknown`` neither — probably pip-installed into a venv.
    """
    global _ENVIRONMENT
    if _ENVIRONMENT is not None:
        return _ENVIRONMENT
    in_container = _running_in_container()
    has_script = _find_repo_root() is not None
    if in_container and has_script:
        _ENVIRONMENT = "docker"
    elif has_script:
        _ENVIRONMENT = "source"
    else:
        _ENVIRONMENT = "unknown"
    return _ENVIRONMENT


def _update_readiness() -> tuple[bool, str | None]:
    """Return (ready, blocker) for POST /update in the current environment.

    Source mode is ready when scripts/update.sh is executable.
    Docker mode is ready when the daemon socket is mounted AND the docker
    CLI is present in PATH — both are needed for the helper-container
    hand-off to work. Unknown mode is never ready.
    """
    env = _detect_environment()
    if env == "source":
        root = _find_repo_root()
        if root is None or not os.access(root / "scripts" / "update.sh", os.X_OK):
            return False, "scripts/update.sh is missing or not executable"
        return True, None
    if env == "docker":
        if not Path("/var/run/docker.sock").exists():
            return False, (
                "Docker socket is not mounted. Add "
                "'- /var/run/docker.sock:/var/run/docker.sock' to the trove "
                "service volumes in docker-compose.yml and restart."
            )
        if shutil.which("docker") is None:
            return False, (
                "docker CLI is missing from the image — rebuild with the "
                "v0.10.1+ Dockerfile so the CLI is copied in."
            )
        return True, None
    return False, (
        "Self-update is only available when Trove runs from a git checkout "
        "or a compose-managed container. Upgrade via your package manager."
    )


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' into a comparable tuple. Drops any pre-release suffix."""
    base = raw.strip().lstrip("v").split("-")[0].split("+")[0]
    parts: list[int] = []
    for component in base.split("."):
        digits = re.match(r"\d+", component)
        if digits:
            parts.append(int(digits.group(0)))
    return tuple(parts) or (0,)


def _is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


async def _fetch_latest_release(client: httpx.AsyncClient) -> dict | None:
    resp = await client.get(
        f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
    )
    if resp.status_code == 200:
        return resp.json()
    return None


async def _fetch_pyproject_version(client: httpx.AsyncClient) -> str | None:
    resp = await client.get(
        f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/backend/pyproject.toml",
        headers={"Accept": "application/vnd.github+json"},
        params={"ref": "main"},
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    content_b64 = data.get("content")
    if not content_b64:
        return None
    try:
        text = base64.b64decode(content_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    match = PYPROJECT_VERSION_RE.search(text)
    return match.group(1) if match else None


async def _run_check() -> UpdateCheck:
    """Resolve the latest version by taking the highest of:

    1. The tag on GitHub Releases (/releases/latest)
    2. The version field in backend/pyproject.toml on main

    Either is fine on its own — when both exist, pick the newer. This
    means a plain git push with a bumped pyproject.toml is enough to
    surface an update, and creating a GitHub Release is only needed
    when you want release notes shown inline.
    """
    now = time.time()
    env = _detect_environment()
    ready, blocker = _update_readiness()
    release_data: dict | None = None
    release_version: str | None = None
    pyproject_version: str | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            release_data = await _fetch_latest_release(client)
            if release_data is not None:
                tag = release_data.get("tag_name") or release_data.get("name") or ""
                release_version = tag.lstrip("v") or None

            pyproject_version = await _fetch_pyproject_version(client)
    except httpx.HTTPError as e:
        return UpdateCheck(
            current=__version__,
            latest=None,
            update_available=False,
            source=None,
            release_notes=None,
            release_url=None,
            checked_at=now,
            error=f"http error: {e}",
            environment=env,
            update_ready=ready,
            update_blocker=blocker,
        )

    # Neither resolver returned anything — repo is probably private or
    # we hit the unauthenticated rate limit
    if release_version is None and pyproject_version is None:
        return UpdateCheck(
            current=__version__,
            latest=None,
            update_available=False,
            source=None,
            release_notes=None,
            release_url=None,
            checked_at=now,
            error=(
                "Could not reach GitHub — repo may be private or rate-limited. "
                "Make sure masterdraco/Trove is public."
            ),
            environment=env,
            update_ready=ready,
            update_blocker=blocker,
        )

    # Pick the higher of the two, preferring release when equal because
    # it carries richer metadata (release notes, html_url).
    candidates: list[tuple[str, str, dict | None]] = []
    if pyproject_version:
        candidates.append((pyproject_version, "github_pyproject", None))
    if release_version:
        candidates.append((release_version, "github_releases", release_data))
    candidates.sort(key=lambda c: _parse_version(c[0]), reverse=True)
    latest, source, winning_release = candidates[0]

    return UpdateCheck(
        current=__version__,
        latest=latest,
        update_available=_is_newer(latest, __version__),
        source=source,
        release_notes=(winning_release or {}).get("body") or None,
        release_url=(winning_release or {}).get("html_url")
        or f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}",
        checked_at=now,
        environment=env,
        update_ready=ready,
        update_blocker=blocker,
    )


@router.get("/version", response_model=UpdateCheck)
async def version_info(
    force: bool = Query(default=False, description="Skip cache and fetch fresh"),
    _user: User = Depends(current_user),
) -> UpdateCheck:
    """Return the running version and check GitHub for a newer one.

    Result is cached for 30 minutes. Use ?force=true to bypass the cache
    and hit GitHub immediately.
    """
    global _CACHE
    now = time.time()
    if not force and _CACHE is not None and (now - _CACHE.ts) < _CACHE_TTL:
        return _CACHE.result
    result = await _run_check()
    _CACHE = _CacheEntry(result=result, ts=now)
    return result


class TorznabInfo(BaseModel):
    apikey: str
    path: str


@router.get("/torznab-info", response_model=TorznabInfo)
async def torznab_info(_user: User = Depends(current_user)) -> TorznabInfo:
    """Return the Torznab apikey (first 32 chars of the session secret).

    Used by the Settings UI to render a copy-pasteable Sonarr/Radarr URL
    without making the user dig through config/session.secret.
    """
    settings = get_settings()
    if not settings.session_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="session secret is not initialised",
        )
    return TorznabInfo(apikey=settings.session_secret[:32], path="/torznab/api")


class UpdateTriggerResponse(BaseModel):
    ok: bool
    message: str
    log_path: str
    pid: int | None


@router.post("/update", response_model=UpdateTriggerResponse)
async def trigger_update(_user: User = Depends(current_user)) -> UpdateTriggerResponse:
    """Spawn scripts/update.sh detached; it decides source vs docker mode.

    In source mode the script does:
      git pull → uv pip install → alembic → pnpm build → restart uvicorn

    In docker mode the script launches a short-lived helper container
    (via the mounted docker socket) that runs
      docker compose pull trove && docker compose up -d trove
    on behalf of the host, so the update survives even when this
    container is replaced.

    Returns immediately after spawning — the frontend polls /api/health
    until the reported version changes to detect completion.
    """
    ready, blocker = _update_readiness()
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=blocker or "Self-update is not available in this environment.",
        )

    repo_root = _find_repo_root()
    if repo_root is None:  # pragma: no cover — _update_readiness guarantees this
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="scripts/update.sh not found — are we running from source?",
        )

    script = repo_root / "scripts" / "update.sh"
    if not os.access(script, os.X_OK):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{script} is not executable",
        )

    log.info("system.update.triggered", script=str(script))

    # Make sure the log file exists and is writable before we detach
    log_path = "/tmp/trove-update.log"
    try:
        Path(log_path).touch(exist_ok=True)
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"cannot create update log: {e}",
        ) from e

    # Spawn detached — start_new_session=True is setsid(). The child
    # survives when we kill the current uvicorn a few seconds later.
    env = os.environ.copy()
    try:
        proc = subprocess.Popen(
            ["/usr/bin/env", "bash", str(script)],
            cwd=str(repo_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to spawn update script: {e}",
        ) from e

    return UpdateTriggerResponse(
        ok=True,
        message="Update started. Server will restart shortly.",
        log_path=log_path,
        pid=proc.pid,
    )
