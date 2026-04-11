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
    TorrentClient,
)

SESSION_HEADER = "X-Transmission-Session-Id"


class TransmissionClient(TorrentClient):
    """Transmission RPC driver.

    Handles the CSRF-style session id: if the server responds 409 we pick
    up the new X-Transmission-Session-Id header and retry once.
    """

    client_type = ClientType.TRANSMISSION

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rpc_url = f"{self.base_url}/transmission/rpc"
        auth: tuple[str, str] | None = None
        if username is not None:
            auth = (username, password or "")
        self._client = httpx.AsyncClient(timeout=timeout, auth=auth)
        self._session_id: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def _rpc(self, method: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"method": method}
        if arguments is not None:
            payload["arguments"] = arguments
        for attempt in range(2):
            headers = {}
            if self._session_id:
                headers[SESSION_HEADER] = self._session_id
            try:
                resp = await self._client.post(self.rpc_url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                raise ClientError(f"transmission: request failed: {e}") from e
            if resp.status_code == 409 and attempt == 0:
                self._session_id = resp.headers.get(SESSION_HEADER)
                if not self._session_id:
                    raise ClientError("transmission: 409 without session-id header")
                continue
            if resp.status_code == 401:
                raise ClientError("transmission: authentication failed")
            if resp.status_code >= 400:
                raise ClientError(f"transmission: HTTP {resp.status_code}: {resp.text}")
            body = resp.json()
            if body.get("result") != "success":
                raise ClientError(f"transmission: {body.get('result')}")
            return body.get("arguments") or {}
        raise ClientError("transmission: session handshake loop exhausted")

    async def test_connection(self) -> ClientHealth:
        try:
            args = await self._rpc(
                "session-get",
                {"fields": ["version", "rpc-version", "download-dir"]},
            )
        except ClientError as e:
            return ClientHealth(ok=False, message=str(e))
        return ClientHealth(
            ok=True,
            version=str(args.get("version", "")) or None,
            details={
                "rpc_version": args.get("rpc-version"),
                "download_dir": args.get("download-dir"),
            },
        )

    async def list_categories(self) -> list[str]:
        # Transmission has no real category concept; the "download-dir" is
        # the closest analogue. Return an empty list and let the UI show
        # a free-text "save path" field.
        return []

    async def add_torrent(self, release: Release, options: AddOptions) -> AddResult:
        arguments: dict[str, Any] = {"paused": options.paused}
        if release.is_magnet() or (
            release.download_url and release.download_url.startswith(("http://", "https://"))
        ):
            arguments["filename"] = release.download_url
        elif release.content is not None:
            arguments["metainfo"] = base64.b64encode(release.content).decode("ascii")
        else:
            raise ClientError("transmission: release has no magnet/url/content")

        if options.save_path:
            arguments["download-dir"] = options.save_path
        if options.label:
            arguments["labels"] = [options.label]

        result = await self._rpc("torrent-add", arguments)
        info = result.get("torrent-added") or result.get("torrent-duplicate")
        if not info:
            return AddResult(ok=False, message="transmission: no torrent returned")
        return AddResult(
            ok=True,
            identifier=info.get("hashString") or str(info.get("id")),
            message="added" if "torrent-added" in result else "duplicate",
        )
