from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from trove.clients.base import Protocol
from trove.indexers.base import Category

_CATALOG_DIR = Path(__file__).parent.parent / "indexers" / "catalog"


class CatalogError(Exception):
    """Raised when the shipped catalog is malformed. This is always our bug,
    never user input — the registry is vendored code."""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    slug: str
    display_name: str
    description: str
    categories: list[Category]
    yaml_file: str
    upstream_path: str
    mirrors: list[str]
    default_mirror: str
    protocol: Protocol
    logo: str | None = None


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, CatalogEntry]:
    registry_path = _CATALOG_DIR / "registry.yaml"
    if not registry_path.exists():
        raise CatalogError(f"catalog registry missing at {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries_raw = raw.get("entries") or []
    if not isinstance(entries_raw, list):
        raise CatalogError("registry.yaml: `entries` must be a list")

    by_slug: dict[str, CatalogEntry] = {}
    for row in entries_raw:
        if not isinstance(row, dict):
            raise CatalogError("registry.yaml: each entry must be a mapping")
        slug = row.get("slug")
        if not slug or not isinstance(slug, str):
            raise CatalogError("registry.yaml: entry missing `slug`")
        if slug in by_slug:
            raise CatalogError(f"registry.yaml: duplicate slug {slug!r}")

        try:
            categories = [Category(c) for c in row.get("categories") or []]
        except ValueError as e:
            raise CatalogError(f"registry.yaml: {slug}: unknown category {e}") from e
        try:
            protocol = Protocol(row.get("protocol") or "torrent")
        except ValueError as e:
            raise CatalogError(f"registry.yaml: {slug}: unknown protocol {e}") from e

        mirrors = list(row.get("mirrors") or [])
        default_mirror = row.get("default_mirror") or ""
        if not mirrors:
            raise CatalogError(f"registry.yaml: {slug}: at least one mirror required")
        if default_mirror not in mirrors:
            raise CatalogError(f"registry.yaml: {slug}: default_mirror must be a member of mirrors")

        by_slug[slug] = CatalogEntry(
            slug=slug,
            display_name=str(row.get("display_name") or slug),
            description=str(row.get("description") or ""),
            categories=categories,
            yaml_file=str(row.get("yaml_file") or f"{slug}.yml"),
            upstream_path=str(row.get("upstream_path") or ""),
            mirrors=mirrors,
            default_mirror=default_mirror,
            protocol=protocol,
            logo=row.get("logo"),
        )

    return by_slug


def list_entries() -> list[CatalogEntry]:
    return list(load_catalog().values())


def get_entry(slug: str) -> CatalogEntry:
    entries = load_catalog()
    if slug not in entries:
        raise KeyError(slug)
    return entries[slug]


def read_yaml(slug: str) -> str:
    entry = get_entry(slug)
    path = _CATALOG_DIR / entry.yaml_file
    if not path.exists():
        raise CatalogError(f"catalog: {slug}: missing yaml file at {path}")
    return path.read_text(encoding="utf-8")


def reset_cache_for_tests() -> None:
    """pytest hook — the module-level cache would otherwise outlive test DBs."""
    load_catalog.cache_clear()
