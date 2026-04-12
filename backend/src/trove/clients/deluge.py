from __future__ import annotations

import base64
import contextlib
from typing import Any

import httpx

from trove.clients.base import (
    AddOptions,
    AddResult,
    ClientError,
    ClientHealth,
    ClientType,
    DownloadState,
    DownloadStatus,
    Release,
    TorrentClient,
)


class DelugeClient(TorrentClient):
    """Deluge Web JSON-RPC driver (deluge-web on :8112 by default)."""

    client_type = ClientType.DELUGE

    def __init__(
        self,
        base_url: str,
        *,
        password: str,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.json_url = f"{self.base_url}/json"
        self.password = password
        self._client = httpx.AsyncClient(timeout=timeout)
        self._request_id = 0
        self._logged_in = False

    async def close(self) -> None:
        await self._client.aclose()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _call(self, method: str, params: list[Any]) -> Any:
        payload = {"method": method, "params": params, "id": self._next_id()}
        try:
            resp = await self._client.post(self.json_url, json=payload)
        except httpx.HTTPError as e:
            raise ClientError(f"deluge: request failed: {e}") from e
        if resp.status_code >= 400:
            raise ClientError(f"deluge: HTTP {resp.status_code}: {resp.text}")
        body = resp.json()
        if body.get("error"):
            raise ClientError(f"deluge: {body['error']}")
        return body.get("result")

    async def _ensure_login(self) -> None:
        if self._logged_in:
            return
        ok = await self._call("auth.login", [self.password])
        if not ok:
            raise ClientError("deluge: authentication failed")
        self._logged_in = True
        # Ensure we're actually connected to a daemon (deluge-web can run
        # detached). Best-effort; ignore failures.
        with contextlib.suppress(ClientError):
            connected = await self._call("web.connected", [])
            if not connected:
                hosts = await self._call("web.get_hosts", [])
                if hosts:
                    host_id = hosts[0][0]
                    await self._call("web.connect", [host_id])

    async def test_connection(self) -> ClientHealth:
        try:
            await self._ensure_login()
            # core.get_free_space is cheap and works on all versions.
            free = await self._call("core.get_free_space", [])
        except ClientError as e:
            return ClientHealth(ok=False, message=str(e))
        return ClientHealth(ok=True, details={"free_space": free})

    async def list_categories(self) -> list[str]:
        try:
            await self._ensure_login()
            labels = await self._call("label.get_labels", [])
        except ClientError:
            return []
        return list(labels or [])

    async def add_torrent(self, release: Release, options: AddOptions) -> AddResult:
        await self._ensure_login()

        opts: dict[str, Any] = {"add_paused": options.paused}
        if options.save_path:
            opts["download_location"] = options.save_path

        torrent_id: str | None = None
        if release.is_magnet():
            assert release.download_url is not None
            torrent_id = await self._call("core.add_torrent_magnet", [release.download_url, opts])
        elif release.download_url and release.download_url.startswith(("http://", "https://")):
            torrent_id = await self._call("core.add_torrent_url", [release.download_url, opts])
        elif release.content is not None:
            filename = (release.title or "release") + ".torrent"
            filedump = base64.b64encode(release.content).decode("ascii")
            torrent_id = await self._call("core.add_torrent_file", [filename, filedump, opts])
        else:
            raise ClientError("deluge: release has no magnet/url/content")

        if not torrent_id:
            return AddResult(ok=False, message="deluge: daemon returned null torrent id")

        label = options.label or options.category
        if label:
            # label plugin may not be enabled; best-effort
            with contextlib.suppress(ClientError):
                await self._call("label.set_torrent", [torrent_id, label])

        return AddResult(ok=True, identifier=str(torrent_id), message="added")

    async def get_state(self, identifier: str) -> DownloadState:
        await self._ensure_login()
        try:
            status = await self._call(
                "core.get_torrent_status",
                [
                    identifier,
                    [
                        "name",
                        "state",
                        "progress",
                        "total_size",
                        "total_done",
                        "eta",
                        "error",
                        "error_string",
                        "is_finished",
                    ],
                ],
            )
        except ClientError as e:
            return DownloadState(status=DownloadStatus.UNKNOWN, error_message=str(e))
        # Deluge returns an empty dict when the torrent is not found.
        if not status:
            return DownloadState(status=DownloadStatus.NOT_FOUND)
        state_str = str(status.get("state") or "").lower()
        # Deluge state strings: "Downloading", "Seeding", "Queued",
        # "Checking", "Allocating", "Paused", "Error", "Moving".
        error = status.get("error") or status.get("error_string") or None
        if error or state_str == "error":
            status_enum = DownloadStatus.FAILED
        elif state_str == "paused":
            status_enum = DownloadStatus.PAUSED
        elif state_str in ("checking", "allocating", "moving"):
            status_enum = DownloadStatus.VERIFYING
        elif state_str == "queued":
            status_enum = DownloadStatus.QUEUED
        elif state_str == "downloading":
            status_enum = DownloadStatus.DOWNLOADING
        elif state_str == "seeding" or status.get("is_finished"):
            status_enum = DownloadStatus.COMPLETED
        else:
            status_enum = DownloadStatus.UNKNOWN

        # Deluge reports progress as 0-100, not 0-1
        progress_pct = float(status.get("progress") or 0.0)
        progress = progress_pct / 100.0 if progress_pct > 1.0 else progress_pct
        total = int(status.get("total_size") or 0) or None
        done = int(status.get("total_done") or 0) or None
        eta = int(status.get("eta") or 0) or None

        return DownloadState(
            status=status_enum,
            progress=progress,
            size_bytes=total,
            downloaded_bytes=done,
            eta_seconds=eta,
            error_message=str(error) if error else None,
            display_title=status.get("name"),
        )
