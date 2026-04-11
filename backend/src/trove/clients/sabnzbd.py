from __future__ import annotations

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


class SabnzbdClient(UsenetClient):
    """SABnzbd driver using the documented HTTP API (mode=...)."""

    client_type = ClientType.SABNZBD

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api"
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        merged = {"output": "json", "apikey": self.api_key, **params}
        try:
            resp = await self._client.get(self.api_url, params=merged)
        except httpx.HTTPError as e:
            raise ClientError(f"sabnzbd: request failed: {e}") from e
        if resp.status_code == 401:
            raise ClientError("sabnzbd: invalid api key")
        if resp.status_code >= 400:
            raise ClientError(f"sabnzbd: HTTP {resp.status_code}: {resp.text}")
        body: Any = resp.json()
        if isinstance(body, dict) and body.get("status") is False:
            raise ClientError(f"sabnzbd: {body.get('error', 'unknown error')}")
        return body if isinstance(body, dict) else {"result": body}

    async def _post(
        self,
        params: dict[str, Any],
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        merged = {"output": "json", "apikey": self.api_key, **params}
        try:
            resp = await self._client.post(self.api_url, data=merged, files=files)
        except httpx.HTTPError as e:
            raise ClientError(f"sabnzbd: request failed: {e}") from e
        if resp.status_code >= 400:
            raise ClientError(f"sabnzbd: HTTP {resp.status_code}: {resp.text}")
        body: Any = resp.json()
        if isinstance(body, dict) and body.get("status") is False:
            raise ClientError(f"sabnzbd: {body.get('error', 'unknown error')}")
        return body if isinstance(body, dict) else {"result": body}

    async def test_connection(self) -> ClientHealth:
        try:
            body = await self._get({"mode": "version"})
        except ClientError as e:
            return ClientHealth(ok=False, message=str(e))
        return ClientHealth(
            ok=True,
            version=str(body.get("version") or body.get("result") or "") or None,
        )

    async def list_categories(self) -> list[str]:
        try:
            body = await self._get({"mode": "get_cats"})
        except ClientError:
            return []
        cats = body.get("categories") or []
        return [c for c in cats if isinstance(c, str) and c != "*"]

    async def add_nzb(self, release: Release, options: AddOptions) -> AddResult:
        params: dict[str, Any] = {"nzbname": release.title}
        if options.category:
            params["cat"] = options.category
        if options.priority is not None:
            params["priority"] = options.priority
        if options.paused:
            params["pp"] = 0
            params["script"] = "None"

        if release.download_url and release.download_url.startswith(("http://", "https://")):
            params["mode"] = "addurl"
            params["name"] = release.download_url
            body = await self._get(params)
        elif release.content is not None:
            params["mode"] = "addfile"
            files = {
                "name": (
                    (release.title or "release") + ".nzb",
                    release.content,
                    "application/x-nzb",
                )
            }
            body = await self._post(params, files=files)
        else:
            raise ClientError("sabnzbd: release has no url/content")

        nzo_ids = body.get("nzo_ids") or []
        identifier = nzo_ids[0] if nzo_ids else None
        return AddResult(ok=bool(body.get("status", True)), identifier=identifier)
