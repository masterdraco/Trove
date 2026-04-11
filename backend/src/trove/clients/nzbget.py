from __future__ import annotations

import base64
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

    async def add_nzb(self, release: Release, options: AddOptions) -> AddResult:
        # NZBGet append signature:
        # append(NZBFilename, NZBContent, Category, Priority, AddToTop,
        #        AddPaused, DupeKey, DupeScore, DupeMode, PPParameters)
        nzb_filename = (release.title or "release") + ".nzb"
        category = options.category or ""
        priority = options.priority if options.priority is not None else 0

        if release.content is not None:
            nzb_content = base64.b64encode(release.content).decode("ascii")
        elif release.download_url and release.download_url.startswith(("http://", "https://")):
            # NZBGet also accepts a URL as the "NZBContent" field when it
            # starts with http/https.
            nzb_content = release.download_url
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
