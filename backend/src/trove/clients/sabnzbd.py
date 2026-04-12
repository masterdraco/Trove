from __future__ import annotations

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

    async def remove_download(self, identifier: str, *, delete_data: bool = True) -> bool:
        # Try removing from active queue first, then history.
        del_files = "del_files" if delete_data else ""
        try:
            await self._get(
                {"mode": "queue", "name": "delete", "value": identifier, "del_files": del_files}
            )
            return True
        except ClientError:
            pass
        try:
            await self._get(
                {"mode": "history", "name": "delete", "value": identifier, "del_files": del_files}
            )
            return True
        except ClientError:
            return False

    async def get_state(self, identifier: str) -> DownloadState:
        """Resolve a SABnzbd nzo_id to a DownloadState.

        SAB splits work into a live queue (``mode=queue``) and a
        completed/failed history (``mode=history``). We check the
        queue first, then the history, then give up with NOT_FOUND.
        """
        try:
            queue = await self._get({"mode": "queue"})
        except ClientError as e:
            return DownloadState(status=DownloadStatus.UNKNOWN, error_message=str(e))

        slots = ((queue.get("queue") or {}).get("slots")) or []
        for slot in slots:
            if slot.get("nzo_id") != identifier:
                continue
            sab_status = str(slot.get("status") or "").lower()
            # SAB queue statuses: Queued, Paused, Downloading, Fetching,
            # Grabbing, Checking, QuickCheck, Repairing, Extracting,
            # Moving, Running (post-processing), Verifying
            if sab_status == "paused":
                status = DownloadStatus.PAUSED
            elif sab_status in ("queued", "grabbing"):
                status = DownloadStatus.QUEUED
            elif sab_status in ("downloading", "fetching"):
                status = DownloadStatus.DOWNLOADING
            elif sab_status in (
                "checking",
                "quickcheck",
                "repairing",
                "extracting",
                "moving",
                "running",
                "verifying",
            ):
                status = DownloadStatus.VERIFYING
            else:
                status = DownloadStatus.UNKNOWN

            total_mb = float(slot.get("mb") or 0)
            remaining_mb = float(slot.get("mbleft") or 0)
            downloaded_mb = max(total_mb - remaining_mb, 0)
            total_bytes = int(total_mb * 1024 * 1024) if total_mb > 0 else None
            downloaded_bytes = int(downloaded_mb * 1024 * 1024) if total_mb > 0 else None
            progress = downloaded_mb / total_mb if total_mb > 0 else 0.0
            # SAB gives timeleft as "HH:MM:SS" — parse to seconds
            eta: int | None = None
            timeleft = slot.get("timeleft")
            if isinstance(timeleft, str) and ":" in timeleft:
                try:
                    parts = [int(p) for p in timeleft.split(":")]
                    while len(parts) < 3:
                        parts.insert(0, 0)
                    eta = parts[0] * 3600 + parts[1] * 60 + parts[2]
                    if eta <= 0:
                        eta = None
                except ValueError:
                    eta = None

            return DownloadState(
                status=status,
                progress=progress,
                size_bytes=total_bytes,
                downloaded_bytes=downloaded_bytes,
                eta_seconds=eta,
                display_title=slot.get("filename") or slot.get("name"),
            )

        # Fall through to history
        try:
            history_body = await self._get({"mode": "history", "limit": 100})
        except ClientError as e:
            return DownloadState(status=DownloadStatus.UNKNOWN, error_message=str(e))
        history_slots = ((history_body.get("history") or {}).get("slots")) or []
        for slot in history_slots:
            if slot.get("nzo_id") != identifier:
                continue
            sab_status = str(slot.get("status") or "").lower()
            fail_message = slot.get("fail_message") or None
            if sab_status == "completed":
                status = DownloadStatus.COMPLETED
            elif sab_status == "failed":
                status = DownloadStatus.FAILED
            else:
                status = DownloadStatus.UNKNOWN
            bytes_raw = slot.get("bytes") or slot.get("size") or 0
            size_bytes: int | None = None
            try:
                size_bytes = int(bytes_raw)
            except (TypeError, ValueError):
                size_bytes = None
            return DownloadState(
                status=status,
                progress=1.0 if status == DownloadStatus.COMPLETED else 0.0,
                size_bytes=size_bytes,
                downloaded_bytes=(size_bytes if status == DownloadStatus.COMPLETED else None),
                error_message=fail_message,
                display_title=slot.get("name"),
            )

        return DownloadState(status=DownloadStatus.NOT_FOUND)
