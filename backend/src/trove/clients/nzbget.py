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
    DownloadState,
    DownloadStatus,
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

    async def remove_download(self, identifier: str, *, delete_data: bool = True) -> bool:
        try:
            nzb_id = int(identifier)
        except ValueError:
            return False
        # Try removing from active queue first, then history.
        try:
            result = await self._call("editqueue", ["GroupDelete", "", [nzb_id]])
            if result:
                return True
        except ClientError:
            pass
        try:
            result = await self._call("editqueue", ["HistoryDelete", "", [nzb_id]])
            return bool(result)
        except ClientError:
            return False

    async def get_state(self, identifier: str) -> DownloadState:
        """Resolve an nzb_id back to a DownloadState.

        NZBGet splits state across two RPC calls:
        - ``listgroups`` for things still in the queue or currently
          downloading (each group has Kind, Status, FileSizeMB,
          RemainingSizeMB, DownloadedSizeMB, DownloadTimeSec, etc.)
        - ``history`` for finished and failed items (ParStatus,
          UnpackStatus, ScriptStatus, MoveStatus, Status)

        We check listgroups first. If the id is there it's still
        active. If not, we walk history and map the status strings to
        our enum.
        """
        try:
            nzb_id = int(identifier)
        except ValueError:
            return DownloadState(
                status=DownloadStatus.UNKNOWN,
                error_message=f"nzbget: invalid identifier {identifier!r}",
            )

        # Active queue — listgroups
        try:
            groups = await self._call("listgroups", [0])
        except ClientError as e:
            return DownloadState(status=DownloadStatus.UNKNOWN, error_message=str(e))

        for g in groups or []:
            if int(g.get("NZBID") or 0) != nzb_id:
                continue
            status_code = str(g.get("Status") or "").upper()
            # Known statuses: QUEUED, PAUSED, DOWNLOADING, FETCHING,
            # PP_QUEUED, LOADING_PARS, VERIFYING_SOURCES, REPAIRING,
            # VERIFYING_REPAIRED, UNPACKING, CLEANING, RENAMING, MOVING,
            # EXECUTING_SCRIPT, POSTPROCESS
            if "PAUSED" in status_code:
                status = DownloadStatus.PAUSED
            elif status_code == "QUEUED":
                status = DownloadStatus.QUEUED
            elif "DOWNLOAD" in status_code or "FETCHING" in status_code:
                status = DownloadStatus.DOWNLOADING
            elif any(
                tok in status_code
                for tok in (
                    "VERIFY",
                    "REPAIR",
                    "UNPACK",
                    "MOVING",
                    "RENAMING",
                    "CLEANING",
                    "LOADING_PARS",
                    "EXECUTING",
                    "POSTPROCESS",
                    "PP_",
                )
            ):
                status = DownloadStatus.VERIFYING
            else:
                status = DownloadStatus.DOWNLOADING
            # NZBGet reports sizes in MB (as strings or ints). Prefer
            # the "Lo"/"Hi" 64-bit pair when available, fall back to
            # the MB field.
            total_mb = int(g.get("FileSizeMB") or 0)
            remaining_mb = int(g.get("RemainingSizeMB") or 0)
            downloaded_mb = max(total_mb - remaining_mb, 0)
            total_bytes = total_mb * 1024 * 1024 if total_mb else None
            downloaded_bytes = downloaded_mb * 1024 * 1024 if total_mb else None
            progress = (downloaded_mb / total_mb) if total_mb > 0 else 0.0
            return DownloadState(
                status=status,
                progress=progress,
                size_bytes=total_bytes,
                downloaded_bytes=downloaded_bytes,
                display_title=g.get("NZBName") or g.get("NZBFilename"),
            )

        # Not in the active queue — look in history
        try:
            history = await self._call("history", [False])
        except ClientError as e:
            return DownloadState(status=DownloadStatus.UNKNOWN, error_message=str(e))

        for h in history or []:
            if int(h.get("NZBID") or 0) != nzb_id:
                continue
            status_code = str(h.get("Status") or "").upper()
            # History statuses look like "SUCCESS/ALL", "FAILURE/PAR",
            # "DELETED/HEALTH", "WARNING/DAMAGED", etc.
            head = status_code.split("/")[0] if "/" in status_code else status_code
            if head == "SUCCESS":
                status = DownloadStatus.COMPLETED
            elif head in ("FAILURE", "DELETED"):
                status = DownloadStatus.FAILED
            elif head == "WARNING":
                # Warnings still land on disk, treat as completed.
                status = DownloadStatus.COMPLETED
            else:
                status = DownloadStatus.UNKNOWN

            total_mb = int(h.get("FileSizeMB") or 0)
            total_bytes = total_mb * 1024 * 1024 if total_mb else None

            return DownloadState(
                status=status,
                progress=1.0 if status == DownloadStatus.COMPLETED else 0.0,
                size_bytes=total_bytes,
                downloaded_bytes=total_bytes if status == DownloadStatus.COMPLETED else None,
                error_message=status_code if status == DownloadStatus.FAILED else None,
                display_title=h.get("NZBName") or h.get("NZBFilename"),
            )

        return DownloadState(status=DownloadStatus.NOT_FOUND)
