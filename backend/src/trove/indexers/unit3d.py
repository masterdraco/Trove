"""UNIT3D indexer driver.

Many private torrent trackers (Aither, Blutopia, ANT, MorethanTV,
Nordicbytes, etc.) run on the UNIT3D codebase, which exposes a
documented JSON search API at ``/api/torrents/filter``. This driver
talks to that endpoint directly so we can search the full back-catalogue
instead of being limited to whatever the tracker happened to push to
RSS recently.

The standard UNIT3D filter parameters we map onto our SearchQuery:

  name           ← query.terms
  tmdbId         ← query.tmdb_id
  imdbId         ← query.imdb_id (numeric, no "tt" prefix)
  seasonNumber   ← query.season
  episodeNumber  ← query.episode
  categories[]   ← LOCAL_TO_UNIT3D_CATEGORIES[query.categories]
  perPage        ← query.limit (capped at 100 by most installs)

Auth is a Bearer token in the Authorization header. The token is the
user's API key from their tracker profile.
"""

from __future__ import annotations

from typing import Any

import httpx

from trove.clients.base import Protocol, Release
from trove.indexers.base import (
    Category,
    Indexer,
    IndexerError,
    IndexerHealth,
    IndexerType,
    SearchQuery,
)

# UNIT3D doesn't have a single global category mapping — every install
# defines its own IDs. We default to the most common Aither/Blutopia
# layout but the user can override per-indexer via credentials
# ("category_map": {"movies": [1], "tv": [2]}).
DEFAULT_CATEGORY_MAP: dict[Category, list[int]] = {
    Category.MOVIES: [1],
    Category.TV: [2],
    Category.MUSIC: [3],
    Category.GAMES: [4],
    Category.SOFTWARE: [5],
    Category.BOOKS: [8],
    Category.ANIME: [6],
}


class Unit3dIndexer(Indexer):
    """JSON-API driver for UNIT3D-based torrent trackers."""

    indexer_type = IndexerType.CUSTOM
    protocol = Protocol.TORRENT

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        api_key: str,
        timeout: float = 20.0,
        category_map: dict[Category, list[int]] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        # UNIT3D's filter endpoint lives at /api/torrents/filter. The user
        # may give us either the bare host or a host with /api already on
        # it; normalise to the host so we can append the path ourselves.
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        self.api_url = f"{self.base_url}/api/torrents/filter"
        self.api_key = api_key
        self.category_map = category_map or DEFAULT_CATEGORY_MAP
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.get(self.api_url, params=params)
        except httpx.HTTPError as e:
            raise IndexerError(f"{self.name}: request failed: {e}") from e
        if resp.status_code == 401:
            raise IndexerError(f"{self.name}: invalid api key")
        if resp.status_code == 403:
            raise IndexerError(f"{self.name}: forbidden — api key lacks permission")
        if resp.status_code >= 400:
            snippet = resp.text[:160].replace("\n", " ")
            raise IndexerError(
                f"{self.name}: HTTP {resp.status_code} from {self.api_url}: {snippet}"
            )
        ctype = resp.headers.get("content-type", "").lower()
        if "json" not in ctype:
            snippet = resp.text[:160].replace("\n", " ")
            raise IndexerError(
                f"{self.name}: non-JSON response (content-type={ctype!r}). "
                f"First 160 bytes: {snippet}"
            )
        try:
            return resp.json()
        except ValueError as e:
            raise IndexerError(f"{self.name}: invalid JSON: {e}") from e

    async def test_connection(self) -> IndexerHealth:
        try:
            # Cheapest possible probe — ask for one row.
            body = await self._get({"perPage": 1})
        except IndexerError as e:
            return IndexerHealth(ok=False, message=str(e))
        # UNIT3D filter responses are wrapped in {"data": [...], "meta": {...}}
        if not isinstance(body, dict) or "data" not in body:
            return IndexerHealth(
                ok=False,
                message="unexpected response shape (no 'data' field)",
            )
        return IndexerHealth(
            ok=True,
            supported_categories=list(self.category_map.keys()),
        )

    def _build_params(self, query: SearchQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "perPage": min(query.limit, 100),
        }
        if query.terms:
            params["name"] = query.terms
        if query.tmdb_id:
            params["tmdbId"] = query.tmdb_id
        if query.imdb_id:
            # UNIT3D wants the numeric form without the "tt" prefix.
            params["imdbId"] = query.imdb_id.lstrip("t")
        if query.season is not None:
            params["seasonNumber"] = query.season
        if query.episode is not None:
            params["episodeNumber"] = query.episode
        if query.categories:
            cat_ids: list[int] = []
            for cat in query.categories:
                cat_ids.extend(self.category_map.get(cat, []))
            if cat_ids:
                # UNIT3D expects array params as `categories[]=1&categories[]=2`
                params["categories[]"] = cat_ids
        return params

    async def search(self, query: SearchQuery) -> list[Release]:
        body = await self._get(self._build_params(query))
        rows = body.get("data") or []
        releases: list[Release] = []
        for row in rows:
            release = self._parse_row(row)
            if release is not None:
                releases.append(release)
        return releases

    def _parse_row(self, row: Any) -> Release | None:
        # UNIT3D rows can be either flat objects or JSON:API-style envelopes
        # ({"type": "torrent", "id": ..., "attributes": {...}}). Handle both.
        if not isinstance(row, dict):
            return None
        attrs = row.get("attributes") if isinstance(row.get("attributes"), dict) else row

        title = attrs.get("name") or attrs.get("title")
        if not title:
            return None

        # Download URL — UNIT3D usually returns a download_link or
        # download_url field with the API key already baked in.
        download_url = (
            attrs.get("download_link") or attrs.get("download_url") or attrs.get("download")
        )
        if not download_url:
            # Some installs return a relative path; build it from the host.
            slug = attrs.get("slug") or row.get("id")
            if slug:
                download_url = f"{self.base_url}/torrent/download/{slug}.{self.api_key}"

        size_raw = attrs.get("size")
        size: int | None = None
        if isinstance(size_raw, (int, float)) or (isinstance(size_raw, str) and size_raw.isdigit()):
            size = int(size_raw)

        seeders_raw = attrs.get("seeders")
        leechers_raw = attrs.get("leechers")
        info_hash = attrs.get("info_hash") or attrs.get("infoHash")

        meta: dict[str, Any] = {}
        if seeders_raw is not None:
            meta["seeders"] = seeders_raw
        if leechers_raw is not None:
            meta["leechers"] = leechers_raw
        published_at = attrs.get("created_at") or attrs.get("createdAt")
        if isinstance(published_at, str):
            meta["published_at"] = published_at

        category_label: str | None = None
        cat_obj = attrs.get("category")
        if isinstance(cat_obj, dict):
            category_label = cat_obj.get("name")
        elif isinstance(cat_obj, str):
            category_label = cat_obj

        return Release(
            title=str(title),
            protocol=Protocol.TORRENT,
            download_url=str(download_url) if download_url else None,
            size=size,
            infohash=str(info_hash) if info_hash else None,
            category=category_label,
            source=self.name,
            metadata=meta,
        )
