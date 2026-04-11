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

    async def close(self) -> None:
        """Release any resources (http clients, sessions). Safe to call repeatedly."""
        return None


class TorrentClient(DownloadClient):
    @abc.abstractmethod
    async def add_torrent(self, release: Release, options: AddOptions) -> AddResult: ...


class UsenetClient(DownloadClient):
    @abc.abstractmethod
    async def add_nzb(self, release: Release, options: AddOptions) -> AddResult: ...
