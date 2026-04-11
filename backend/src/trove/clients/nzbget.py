from __future__ import annotations

import base64
import gzip
from typing import Any

import httpx

from trove.clients.base import (
    AddOptions,
    AddResult,
    ClientError,
    ClientHealth,
    ClientType,
    Release,
    UsenetClient,
)


def _looks_like_nzb(data: bytes) -> bool:
    head = data.lstrip()[:512].lower()
    return head.startswith(b"<?xml") or head.startswith(b"<nzb")


class NzbgetClient(UsenetClient):
    """NZBGet JSON-RPC driver."""

    client_type = ClientType.NZBGET

    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rpc_url = f"{self.base_url}/jsonrpc"
        self._client = httpx.AsyncClient(timeout=timeout, auth=(username, password))
        self._id = 0

    async def close(self) -> None:
        await self._client.aclose()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _call(self, method: str, params: list[Any]) -> Any:
        payload = {"method": method, "params": params, "id": self._next_id()}
        try:
            resp = await self._client.post(self.rpc_url, json=payload)
        except httpx.HTTPError as e:
            raise ClientError(f"nzbget: request failed: {e}") from e
        if resp.status_code == 401:
            raise ClientError("nzbget: authentication failed")
        if resp.status_code >= 400:
            raise ClientError(f"nzbget: HTTP {resp.status_code}: {resp.text}")
        body = resp.json()
        if body.get("error"):
            raise ClientError(f"nzbget: {body['error']}")
        return body.get("result")

    async def test_connection(self) -> ClientHealth:
        try:
            version = await self._call("version", [])
        except ClientError as e:
            return ClientHealth(ok=False, message=str(e))
        return ClientHealth(ok=True, version=str(version))

    async def list_categories(self) -> list[str]:
        try:
            cfg = await self._call("config", [])
        except ClientError:
            return []
        categories: list[str] = []
        for item in cfg or []:
            name = item.get("Name", "")
            if name.startswith("Category") and name.endswith(".Name"):
                value = item.get("Value")
                if isinstance(value, str) and value:
                    categories.append(value)
        return categories

    async def _fetch_nzb(self, url: str) -> bytes:
        # Use a fresh client so we don't send NZBGet's Basic auth header to
        # the indexer.
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                resp = await c.get(url)
        except httpx.HTTPError as e:
            raise ClientError(f"nzbget: failed to fetch nzb: {e}") from e
        if resp.status_code >= 400:
            raise ClientError(f"nzbget: indexer returned HTTP {resp.status_code} for nzb url")
        data = resp.content
        # Some indexers serve .nzb.gz directly without Content-Encoding.
        if data[:2] == b"\x1f\x8b":
            try:
                data = gzip.decompress(data)
            except OSError as e:
                raise ClientError(f"nzbget: failed to gunzip nzb: {e}") from e
        if not _looks_like_nzb(data):
            ctype = resp.headers.get("content-type", "?")
            snippet = data[:120].decode("utf-8", "replace").strip()
            raise ClientError(
                f"nzbget: indexer did not return an nzb file "
                f"(content-type={ctype}, starts with: {snippet!r})"
            )
        return data

    async def add_nzb(self, release: Release, options: AddOptions) -> AddResult:
        # NZBGet append signature:
        # append(NZBFilename, NZBContent, Category, Priority, AddToTop,
        #        AddPaused, DupeKey, DupeScore, DupeMode, PPParameters)
        nzb_filename = (release.title or "release") + ".nzb"
        category = options.category or ""
        priority = options.priority if options.priority is not None else 0

        if release.content is not None:
            raw = release.content
            if raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except OSError as e:
                    raise ClientError(f"nzbget: failed to gunzip nzb: {e}") from e
            if not _looks_like_nzb(raw):
                snippet = raw[:120].decode("utf-8", "replace").strip()
                raise ClientError(
                    f"nzbget: release.content is not an nzb file (starts with: {snippet!r})"
                )
            nzb_content = base64.b64encode(raw).decode("ascii")
        elif release.download_url and release.download_url.startswith(("http://", "https://")):
            # Fetch and validate ourselves rather than handing the URL to
            # NZBGet — indexers often return HTML error pages on auth/quota
            # failure, which NZBGet then chokes on with "xmlParseStartTag:
            # invalid element name".
            raw = await self._fetch_nzb(release.download_url)
            nzb_content = base64.b64encode(raw).decode("ascii")
        else:
            raise ClientError("nzbget: release has no url/content")

        nzb_id = await self._call(
            "append",
            [
                nzb_filename,
                nzb_content,
                category,
                priority,
                False,  # add-to-top
                options.paused,
                "",  # dupe key
                0,  # dupe score
                "score",  # dupe mode
                [],  # pp-parameters
            ],
        )
        ok = bool(nzb_id) and nzb_id != -1
        return AddResult(
            ok=ok,
            identifier=str(nzb_id) if ok else None,
            message="added" if ok else "nzbget refused release",
        )
