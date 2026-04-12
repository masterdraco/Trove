from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from trove.clients.base import Protocol, Release


class Category(StrEnum):
    MOVIES = "movies"
    TV = "tv"
    MUSIC = "music"
    BOOKS = "books"
    AUDIOBOOKS = "audiobooks"
    COMICS = "comics"
    ANIME = "anime"
    GAMES = "games"
    SOFTWARE = "software"
    OTHER = "other"


class IndexerType(StrEnum):
    NEWZNAB = "newznab"
    TORZNAB = "torznab"
    CARDIGANN = "cardigann"
    UNIT3D = "unit3d"
    RARTRACKER = "rartracker"
    CUSTOM = "custom"


@dataclass(slots=True)
class SearchQuery:
    terms: str
    categories: list[Category] = field(default_factory=list)
    limit: int = 100
    season: int | None = None
    episode: int | None = None
    imdb_id: str | None = None
    tmdb_id: str | None = None


@dataclass(slots=True)
class IndexerHealth:
    ok: bool
    version: str | None = None
    message: str | None = None
    supported_categories: list[Category] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class IndexerError(Exception):
    """Raised when an indexer driver hits an unrecoverable error."""


class Indexer(abc.ABC):
    """Abstract base class for all indexer drivers."""

    indexer_type: IndexerType
    protocol: Protocol
    name: str

    @abc.abstractmethod
    async def test_connection(self) -> IndexerHealth: ...

    @abc.abstractmethod
    async def search(self, query: SearchQuery) -> list[Release]: ...

    async def close(self) -> None:
        return None
