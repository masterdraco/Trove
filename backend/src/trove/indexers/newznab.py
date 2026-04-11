from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from lxml import etree

from trove.clients.base import Protocol, Release
from trove.indexers.base import (
    Category,
    Indexer,
    IndexerError,
    IndexerHealth,
    IndexerType,
    SearchQuery,
)

# Newznab category ID ranges. Torznab reuses the same mapping.
CATEGORY_ID_TO_LOCAL: dict[int, Category] = {
    1000: Category.GAMES,  # console
    2000: Category.MOVIES,
    3000: Category.MUSIC,
    4000: Category.SOFTWARE,  # PC software + games
    5000: Category.TV,
    6000: Category.OTHER,  # xxx
    7000: Category.BOOKS,
    8000: Category.OTHER,
}

LOCAL_TO_CATEGORY_IDS: dict[Category, list[int]] = {
    Category.MOVIES: [2000],
    Category.TV: [5000],
    Category.MUSIC: [3000],
    Category.BOOKS: [7000],
    Category.AUDIOBOOKS: [3030, 7030],
    Category.COMICS: [7030],
    Category.ANIME: [5070],
    Category.GAMES: [1000, 4050],
    Category.SOFTWARE: [4000],
    Category.OTHER: [8000],
}


def _normalize_download_url(url: str | None) -> str | None:
    """Clean up download URLs returned by quirky newznab implementations.

    Nzbplanet (and a few others) return links like
    ``https://api.nzbplanet.net/getnzb/HASH.nzb&i=USER&r=KEY`` — using
    ``&`` between the path and the query string instead of ``?``. The
    indexer then ignores the credentials, redirects to ``/login``, and
    we get an HTML page back instead of a real NZB. Some also pad the
    URL with trailing whitespace inside the XML element. Sonarr/Radarr
    silently fix both quirks; mirror that behavior here.
    """
    if not url:
        return url
    url = url.strip()
    if "?" not in url and "&" in url:
        # Promote the first '&' to '?' so query params are recognized.
        url = url.replace("&", "?", 1)
    return url


class NewznabIndexer(Indexer):
    """Newznab/Torznab adapter.

    Works with any indexer that speaks the Newznab API ``/api?t=search`` (for
    Usenet NZB) or the Torznab variant (for torrents). Set ``protocol``
    explicitly — we cannot guess because both speak the same XML schema.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        *,
        api_key: str,
        protocol: Protocol = Protocol.USENET,
        timeout: float = 20.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        # Many Newznab instances expose the API at /api, but some accept
        # requests directly at the base URL. Callers can include /api in
        # the base URL; we only append it if it's missing.
        if self.base_url.rstrip("/").endswith("/api"):
            self.api_url = self.base_url
        else:
            self.api_url = f"{self.base_url}/api"
        self.api_key = api_key
        self.protocol = protocol
        self.indexer_type = (
            IndexerType.TORZNAB if protocol is Protocol.TORRENT else IndexerType.NEWZNAB
        )
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, params: dict[str, Any]) -> bytes:
        merged = {"apikey": self.api_key, **params}
        try:
            resp = await self._client.get(self.api_url, params=merged)
        except httpx.HTTPError as e:
            raise IndexerError(f"{self.name}: request failed: {e}") from e
        if resp.status_code == 401:
            raise IndexerError(f"{self.name}: invalid api key")
        if resp.status_code >= 400:
            raise IndexerError(f"{self.name}: HTTP {resp.status_code}")
        body = resp.content
        if not body or not body.strip():
            raise IndexerError(
                f"{self.name}: empty response from {self.api_url} "
                f"(check that the URL is correct and ends before '/api')"
            )
        ctype = resp.headers.get("content-type", "").lower()
        if (
            "xml" not in ctype
            and "rss" not in ctype
            and not body.lstrip().startswith((b"<?xml", b"<rss", b"<caps", b"<error"))
        ):
            snippet = body[:160].decode("utf-8", errors="replace").replace("\n", " ")
            raise IndexerError(
                f"{self.name}: non-XML response (content-type={ctype!r}). "
                f"Likely wrong URL. First 160 bytes: {snippet}"
            )
        return body

    async def test_connection(self) -> IndexerHealth:
        try:
            body = await self._get({"t": "caps"})
        except IndexerError as e:
            return IndexerHealth(ok=False, message=str(e))
        try:
            root = etree.fromstring(body)
        except etree.XMLSyntaxError as e:
            return IndexerHealth(ok=False, message=f"invalid XML: {e}")

        # Newznab can return <error code="100" description="..."/> instead of caps
        if root.tag == "error":
            desc = root.get("description") or root.get("code") or "unknown error"
            return IndexerHealth(ok=False, message=f"indexer error: {desc}")

        server = root.find("server")
        version = None
        if server is not None:
            version = server.get("version") or server.get("title")

        supported: list[Category] = []
        categories = root.find("categories")
        if categories is not None:
            for cat in categories.findall("category"):
                cid_attr = cat.get("id")
                if cid_attr and cid_attr.isdigit():
                    mapped = CATEGORY_ID_TO_LOCAL.get(int(cid_attr))
                    if mapped and mapped not in supported:
                        supported.append(mapped)

        return IndexerHealth(ok=True, version=version, supported_categories=supported)

    async def search(self, query: SearchQuery) -> list[Release]:
        params: dict[str, Any] = {
            "t": "tvsearch" if query.season is not None or query.episode is not None else "search",
            "q": query.terms,
            "limit": query.limit,
        }
        if query.season is not None:
            params["season"] = query.season
        if query.episode is not None:
            params["ep"] = query.episode
        if query.imdb_id:
            params["imdbid"] = query.imdb_id.lstrip("t")
        if query.tmdb_id:
            params["tmdbid"] = query.tmdb_id

        if query.categories:
            ids: list[int] = []
            for cat in query.categories:
                ids.extend(LOCAL_TO_CATEGORY_IDS.get(cat, []))
            if ids:
                params["cat"] = ",".join(str(i) for i in ids)

        body = await self._get(params)
        try:
            root = etree.fromstring(body)
        except etree.XMLSyntaxError as e:
            raise IndexerError(f"{self.name}: invalid XML: {e}") from e

        if root.tag == "error":
            desc = root.get("description") or root.get("code") or "unknown error"
            raise IndexerError(f"{self.name}: indexer error: {desc}")

        releases: list[Release] = []
        for item in root.iter("item"):
            release = self._parse_item(item)
            if release is not None:
                releases.append(release)
        return releases

    def _parse_item(self, item: Any) -> Release | None:
        title_el = item.find("title")
        title = title_el.text if title_el is not None else None
        if not title:
            return None

        link_el = item.find("link")
        download_url = link_el.text if link_el is not None else None

        enclosure = item.find("enclosure")
        if download_url is None and enclosure is not None:
            download_url = enclosure.get("url")

        download_url = _normalize_download_url(download_url)

        size: int | None = None
        if enclosure is not None:
            length = enclosure.get("length")
            if length and length.isdigit():
                size = int(length)

        infohash: str | None = None
        category: str | None = None
        ns = "{http://torznab.com/schemas/2015/feed}"
        newznab_ns = "{http://www.newznab.com/DTD/2010/feeds/attributes/}"
        for attr in item.iterfind(f"{ns}attr"):
            name = attr.get("name")
            value = attr.get("value")
            if name == "size" and value and value.isdigit() and size is None:
                size = int(value)
            elif name == "infohash" and value:
                infohash = value
            elif name == "category" and value:
                category = value
        for attr in item.iterfind(f"{newznab_ns}attr"):
            name = attr.get("name")
            value = attr.get("value")
            if name == "size" and value and value.isdigit() and size is None:
                size = int(value)
            elif name == "category" and value:
                category = value

        published_at: datetime | None = None
        pub_el = item.find("pubDate")
        if pub_el is not None and pub_el.text:
            try:
                from email.utils import parsedate_to_datetime

                published_at = parsedate_to_datetime(pub_el.text)
            except (TypeError, ValueError):
                published_at = None

        metadata: dict[str, Any] = {}
        if published_at is not None:
            metadata["published_at"] = published_at.isoformat()

        return Release(
            title=title,
            protocol=self.protocol,
            download_url=download_url,
            size=size,
            infohash=infohash,
            category=category,
            source=self.name,
            metadata=metadata,
        )
