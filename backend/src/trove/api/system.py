"""System-level endpoints: version info, update checks."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from trove import __version__
from trove.api.deps import current_user
from trove.models.user import User

router = APIRouter()

GITHUB_OWNER = "masterdraco"
GITHUB_REPO = "Trove"
GITHUB_API = "https://api.github.com"
PYPROJECT_VERSION_RE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


class UpdateCheck(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    source: str | None
    release_notes: str | None
    release_url: str | None
    checked_at: float
    error: str | None = None


@dataclass
class _CacheEntry:
    result: UpdateCheck
    ts: float


_CACHE: _CacheEntry | None = None
_CACHE_TTL = 30 * 60  # 30 minutes


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
