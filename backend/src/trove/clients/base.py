from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Protocol(StrEnum):
    TORRENT = "torrent"
    USENET = "usenet"


class ClientType(StrEnum):
    DELUGE = "deluge"
    TRANSMISSION = "transmission"
    SABNZBD = "sabnzbd"
    NZBGET = "nzbget"

    @property
    def protocol(self) -> Protocol:
        return {
            ClientType.DELUGE: Protocol.TORRENT,
            ClientType.TRANSMISSION: Protocol.TORRENT,
            ClientType.SABNZBD: Protocol.USENET,
            ClientType.NZBGET: Protocol.USENET,
        }[self]


@dataclass(slots=True)
class Release:
    """A downloadable item from any indexer.

    Exactly one of ``download_url`` / ``content`` should carry the payload.
    ``download_url`` may be a magnet link, an http URL to a .torrent/.nzb
    file, or a direct .torrent/.nzb URL behind tracker auth.
    """

    title: str
    protocol: Protocol
    download_url: str | None = None
    content: bytes | None = None
    size: int | None = None
    infohash: str | None = None
    category: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_magnet(self) -> bool:
        return self.download_url is not None and self.download_url.startswith("magnet:")


@dataclass(slots=True)
class AddOptions:
    category: str | None = None
    label: str | None = None
    save_path: str | None = None
    paused: bool = False
    priority: int | None = None


@dataclass(slots=True)
class AddResult:
    ok: bool
    identifier: str | None = None  # infohash, nzo_id, download id, etc.
    message: str | None = None


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class DownloadState:
    """Snapshot of a single download's current state in its client.

    Returned by ``DownloadClient.get_state()`` so the periodic poller
    can track state transitions (``queued → downloading → completed``)
    and fire notification events. All fields except ``status`` are
    optional because not every client exposes every field — e.g.
    Transmission doesn't report ETA on seed-queue items, NZBGet
    reports bytes in different units per section, etc. Callers should
    treat missing fields as "unknown, leave prior value".
    """

    status: DownloadStatus
    progress: float = 0.0  # 0.0 .. 1.0
    size_bytes: int | None = None
    downloaded_bytes: int | None = None
    eta_seconds: int | None = None
    error_message: str | None = None
    # The actual on-disk title the client is using, if different from
    # the one we submitted — useful for notifications that want to show
    # the release name the user will see in their media library.
    display_title: str | None = None


@dataclass(slots=True)
class ClientHealth:
    ok: bool
    version: str | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ClientError(Exception):
    """Raised when a client driver hits an unrecoverable error."""


class DownloadClient(abc.ABC):
    """Abstract base class for all download client drivers."""

    client_type: ClientType

    @abc.abstractmethod
    async def test_connection(self) -> ClientHealth: ...

    @abc.abstractmethod
    async def list_categories(self) -> list[str]: ...

    async def get_state(self, identifier: str) -> DownloadState:
        """Return the current download state for a previously-submitted item.

        Identifier is whatever ``AddResult.identifier`` the original
        ``add_torrent`` / ``add_nzb`` call returned — NZBGet's nzb_id,
        a torrent's infohash, SABnzbd's nzo_id, etc. Drivers must
        implement this; the default just returns ``UNKNOWN`` so old
        subclasses keep working without crashing the poller.
        """
        return DownloadState(status=DownloadStatus.UNKNOWN)

    async def remove_download(self, identifier: str, *, delete_data: bool = True) -> bool:
        """Remove a previously-added download from the client.

        Returns ``True`` if the item was found and removed, ``False`` if
        it was already gone. Used by the quality upgrade path to evict
        a lower-quality grab before replacing it with a better one.

        ``delete_data`` controls whether files on disk are also removed
        (default ``True``). Subclasses that don't support this flag
        should always delete data.
        """
        return False

    async def close(self) -> None:
        """Release any resources (http clients, sessions). Safe to call repeatedly."""
        return None


class TorrentClient(DownloadClient):
    @abc.abstractmethod
    async def add_torrent(self, release: Release, options: AddOptions) -> AddResult: ...


class UsenetClient(DownloadClient):
    @abc.abstractmethod
    async def add_nzb(self, release: Release, options: AddOptions) -> AddResult: ...
