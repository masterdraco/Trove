"""RarTracker indexer driver.

RarTracker is the AngularJS-SPA codebase behind Superbits, ScenePalace,
and several other Swedish/Nordic private torrent trackers. It exposes a
JSON API at ``/api/v1/torrents`` that accepts a ``searchText`` query
plus a long list of filter flags (language audio/sub, freeleech,
extended, etc.).

Auth is cookie-based — there's no passkey or bearer token that unlocks
the search API. The user has to log in through the web UI (hCaptcha
stops us from automating it) and paste the resulting session cookie
into the indexer's credentials. The download endpoint also uses
cookie auth; the task engine's prefetch step attaches the session
cookie automatically so download clients don't need tracker auth.

Credentials layout:

    {
        "session_cookie": "PHPSESSID=abc; rartracker=def",   # raw Cookie header value
        "passkey": "025c82...",                              # from /profile
    }

The cookie string can contain one or more cookies — whatever the
browser was sending when the user copied it. We forward it verbatim.
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

# RarTracker doesn't share a standardised category scheme — each install
# wires its own ids. Superbits uses string "section" names instead of
# numeric ids, so the default map here is string-based. Users can
# override via credentials.category_map if their install is different.
DEFAULT_SECTION_MAP: dict[Category, list[str]] = {
    Category.MOVIES: ["movies"],
    Category.TV: ["tv"],
    Category.MUSIC: ["music"],
    Category.BOOKS: ["books"],
    Category.AUDIOBOOKS: ["audiobooks"],
    Category.GAMES: ["games"],
    Category.SOFTWARE: ["apps"],
    Category.ANIME: ["anime"],
    Category.COMICS: ["comics"],
    Category.OTHER: ["other"],
}


class RartrackerIndexer(Indexer):
    """Session-cookie driver for RarTracker-based private torrent sites."""

    indexer_type = IndexerType.CUSTOM
    protocol = Protocol.TORRENT

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        session_cookie: str,
        passkey: str | None = None,
        timeout: float = 20.0,
        section_map: dict[Category, list[str]] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1/torrents"
        self.passkey = passkey
        self.section_map = section_map or DEFAULT_SECTION_MAP
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Trove/indexer)",
                "Cookie": session_cookie,
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _default_params(self) -> dict[str, Any]:
        # The SPA sends this long list on every search — several of the
        # flags are required (the backend errors out if they're missing).
        # We set all of them to conservative defaults so the search
        # behaves like "all content, all languages, all sections".
        return {
            "index": 0,
            "limit": 50,
            "page": "search",
            "section": "all",
            "sort": "n",
            "order": "desc",
            "extendedSearch": "false",
            "freeleech": "false",
            "dkaudio": "false",
            "dksub": "false",
            "enaudio": "false",
            "fiaudio": "false",
            "fisub": "false",
            "noaudio": "false",
            "nosub": "false",
            "sweaudio": "false",
            "swesub": "false",
            "stereoscopic": "false",
            "watchview": "false",
        }

    async def _get(self, params: dict[str, Any]) -> Any:
        merged = {**self._default_params(), **params}
        try:
            resp = await self._client.get(self.api_url, params=merged)
        except httpx.HTTPError as e:
            raise IndexerError(f"{self.name}: request failed: {e}") from e
        if resp.status_code == 401:
            raise IndexerError(
                f"{self.name}: session cookie expired or invalid — re-copy it "
                f"from your browser devtools after logging in to the tracker "
                f"and update the indexer credentials"
            )
        if 300 <= resp.status_code < 400:
            # follow_redirects=False — a 302 here almost always means the
            # session cookie expired and the tracker redirected us to /login.
            raise IndexerError(
                f"{self.name}: redirected to {resp.headers.get('location', '?')} — "
                f"session cookie likely expired, re-copy it from your browser"
            )
        if resp.status_code >= 400:
            snippet = resp.text[:160].replace("\n", " ")
            raise IndexerError(
                f"{self.name}: HTTP {resp.status_code} from {self.api_url}: {snippet}"
            )
        # Some RarTracker installs return 200 + application/json with an
        # empty body when a search has zero matches. Treat that as "no
        # results" instead of crashing on the JSON parse.
        if not resp.content or not resp.text.strip():
            return []
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
            body = await self._get({"searchText": "", "limit": 1})
        except IndexerError as e:
            return IndexerHealth(ok=False, message=str(e))
        # RarTracker returns either a list directly or a dict like
        # {"torrents": [...], "total": N}. Either shape is fine.
        if not isinstance(body, (list, dict)):
            return IndexerHealth(
                ok=False, message=f"unexpected response shape: {type(body).__name__}"
            )
        return IndexerHealth(
            ok=True,
            supported_categories=list(self.section_map.keys()),
        )

    def _build_params(self, query: SearchQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "searchText": query.terms or "",
            "limit": min(query.limit, 100),
        }
        # Season/episode can't be separately filtered by RarTracker's API —
        # bake them into the search text if set.
        if query.season is not None and query.episode is not None:
            params["searchText"] = f"{query.terms} S{query.season:02d}E{query.episode:02d}"
        elif query.season is not None:
            params["searchText"] = f"{query.terms} S{query.season:02d}"

        if query.categories:
            sections: list[str] = []
            for cat in query.categories:
                sections.extend(self.section_map.get(cat, []))
            if len(sections) == 1:
                params["section"] = sections[0]
            # RarTracker only supports a single section per call, so when
            # more than one is requested we fall back to "all" and rely on
            # the task-level filters to narrow down.
        return params

    async def search(self, query: SearchQuery) -> list[Release]:
        body = await self._get(self._build_params(query))
        rows = self._extract_rows(body)
        releases: list[Release] = []
        for row in rows:
            release = self._parse_row(row)
            if release is not None:
                releases.append(release)
        # Client-side sanity filter: when RarTracker's API finds zero
        # real matches for the searchText, it falls back to returning a
        # generic alphabetical list of torrents from across the site.
        # Drop anything whose name doesn't contain every token from the
        # query, so callers see an honest empty result instead of noise.
        if query.terms:
            import re as _re

            def _toks(s: str) -> list[str]:
                return [t for t in _re.split(r"[^a-z0-9]+", s.lower()) if t]

            wanted = _toks(query.terms)
            releases = [r for r in releases if all(t in _toks(r.title) for t in wanted)]
        return releases

    def _extract_rows(self, body: Any) -> list[Any]:
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in ("torrents", "data", "results", "items"):
                if isinstance(body.get(key), list):
                    return body[key]
        return []

    def _parse_row(self, row: Any) -> Release | None:
        if not isinstance(row, dict):
            return None

        title = row.get("name") or row.get("title")
        if not title:
            return None

        torrent_id = row.get("id")
        download_url: str | None = None
        if torrent_id is not None:
            # The download endpoint is cookie-authenticated — no passkey
            # in the path. The task engine's prefetch step adds the
            # session cookie automatically based on the indexer's stored
            # credentials.
            download_url = f"{self.base_url}/api/v1/torrents/download/{torrent_id}"
        elif row.get("download_url"):
            download_url = row["download_url"]

        size_raw = row.get("size")
        size: int | None = None
        if isinstance(size_raw, (int, float)) or (isinstance(size_raw, str) and size_raw.isdigit()):
            size = int(size_raw)

        seeders = row.get("seeders") or row.get("seeds")
        leechers = row.get("leechers") or row.get("peers")
        info_hash = row.get("info_hash") or row.get("hash") or row.get("infohash")

        meta: dict[str, Any] = {}
        if seeders is not None:
            meta["seeders"] = seeders
        if leechers is not None:
            meta["leechers"] = leechers
        added = row.get("added") or row.get("created_at")
        if isinstance(added, str):
            meta["published_at"] = added

        category_label: str | None = None
        section = row.get("section") or row.get("category")
        if isinstance(section, str):
            category_label = section
        elif isinstance(section, dict):
            category_label = section.get("name")

        return Release(
            title=str(title),
            protocol=Protocol.TORRENT,
            download_url=download_url,
            size=size,
            infohash=str(info_hash) if info_hash else None,
            category=category_label,
            source=self.name,
            metadata=meta,
        )
