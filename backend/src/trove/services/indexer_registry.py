from __future__ import annotations

from typing import Any

from trove.clients.base import Protocol
from trove.indexers.base import Category, Indexer, IndexerError, IndexerType
from trove.indexers.cardigann import CardigannIndexer, load_definition_yaml
from trove.indexers.newznab import NewznabIndexer
from trove.indexers.rartracker import RartrackerIndexer
from trove.indexers.unit3d import Unit3dIndexer
from trove.models.indexer import IndexerRow
from trove.utils.crypto import decrypt_json, encrypt_json


def encrypt_credentials(creds: dict[str, Any]) -> str:
    return encrypt_json(creds)


def _build(
    indexer_type: IndexerType,
    protocol: Protocol,
    name: str,
    base_url: str,
    creds: dict[str, Any],
    definition_yaml: str | None,
) -> Indexer:
    if indexer_type in (IndexerType.NEWZNAB, IndexerType.TORZNAB):
        api_key = creds.get("api_key")
        if not api_key:
            raise IndexerError(f"{name}: api_key required")
        return NewznabIndexer(
            name,
            base_url,
            api_key=api_key,
            protocol=protocol,
        )
    if indexer_type is IndexerType.CARDIGANN:
        if not definition_yaml:
            raise IndexerError(f"{name}: cardigann definition_yaml required")
        definition = load_definition_yaml(definition_yaml)
        definition.name = name
        return CardigannIndexer(definition, base_url=base_url)
    if indexer_type is IndexerType.RARTRACKER:
        session_cookie = creds.get("session_cookie")
        if not session_cookie:
            raise IndexerError(
                f"{name}: session_cookie required — paste it from your browser "
                f"devtools after logging in to the tracker"
            )
        return RartrackerIndexer(
            name=name,
            base_url=base_url,
            session_cookie=session_cookie,
            passkey=creds.get("passkey"),
        )
    if indexer_type is IndexerType.UNIT3D:
        api_key = creds.get("api_key")
        if not api_key:
            raise IndexerError(f"{name}: api_key required")
        # Optional per-tracker category mapping. Stored in credentials so
        # the user can override the defaults without editing code:
        # {"api_key": "...", "category_map": {"movies": [1], "tv": [2]}}
        raw_map = creds.get("category_map")
        category_map: dict[Category, list[int]] | None = None
        if isinstance(raw_map, dict):
            category_map = {}
            for k, v in raw_map.items():
                try:
                    cat = Category(k)
                except ValueError:
                    continue
                if isinstance(v, list):
                    category_map[cat] = [int(i) for i in v if isinstance(i, (int, str))]
        return Unit3dIndexer(
            name=name,
            base_url=base_url,
            api_key=api_key,
            category_map=category_map,
        )
    raise IndexerError(f"unsupported indexer type: {indexer_type}")


def build_driver(row: IndexerRow) -> Indexer:
    try:
        indexer_type = IndexerType(row.type)
    except ValueError as e:
        raise IndexerError(f"unknown indexer type: {row.type}") from e
    try:
        protocol = Protocol(row.protocol)
    except ValueError as e:
        raise IndexerError(f"unknown protocol: {row.protocol}") from e
    creds = decrypt_json(row.credentials_cipher)
    return _build(indexer_type, protocol, row.name, row.base_url, creds, row.definition_yaml)


def build_transient(
    indexer_type: IndexerType,
    protocol: Protocol,
    name: str,
    base_url: str,
    credentials: dict[str, Any],
    definition_yaml: str | None,
) -> Indexer:
    return _build(indexer_type, protocol, name, base_url, credentials, definition_yaml)
