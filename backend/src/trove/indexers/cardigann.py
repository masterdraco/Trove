from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import yaml
from bs4 import BeautifulSoup, Tag

from trove.clients.base import Protocol, Release
from trove.indexers.base import (
    Category,
    Indexer,
    IndexerError,
    IndexerHealth,
    IndexerType,
    SearchQuery,
)

SIZE_RE = re.compile(r"([\d.,]+)\s*(TB|GB|MB|KB|B)", re.IGNORECASE)
SIZE_MULTIPLIERS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}


def _parse_size(value: str | None) -> int | None:
    if not value:
        return None
    match = SIZE_RE.search(value)
    if not match:
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None
    number = float(match.group(1).replace(",", ""))
    unit = match.group(2).upper()
    return int(number * SIZE_MULTIPLIERS.get(unit, 1))


@dataclass(slots=True)
class FieldSpec:
    selector: str | None = None
    attribute: str | None = None
    remove: str | None = None
    filters: list[dict[str, Any]] = field(default_factory=list)
    text: str | None = None


@dataclass(slots=True)
class CardigannDefinition:
    site: str
    name: str
    links: list[str]
    search_path: str
    search_params: dict[str, Any]
    rows_selector: str
    fields: dict[str, FieldSpec]
    category_mapping: dict[str, Category] = field(default_factory=dict)
    protocol: Protocol = Protocol.TORRENT


def _coerce_field(spec_data: dict[str, Any] | str) -> FieldSpec:
    if isinstance(spec_data, str):
        return FieldSpec(text=spec_data)
    return FieldSpec(
        selector=spec_data.get("selector"),
        attribute=spec_data.get("attribute"),
        remove=spec_data.get("remove"),
        filters=spec_data.get("filters") or [],
        text=spec_data.get("text"),
    )


def load_definition(data: dict[str, Any]) -> CardigannDefinition:
    search_block = data.get("search") or {}
    paths = search_block.get("paths") or []
    if not paths:
        raise IndexerError("cardigann: definition has no search.paths")
    first_path = paths[0]
    search_path = first_path.get("path", "") if isinstance(first_path, dict) else str(first_path)

    rows_block = search_block.get("rows") or {}
    rows_selector = rows_block.get("selector") if isinstance(rows_block, dict) else None
    if not rows_selector:
        raise IndexerError("cardigann: definition has no search.rows.selector")

    raw_fields = search_block.get("fields") or {}
    fields_map = {key: _coerce_field(value) for key, value in raw_fields.items()}

    category_mapping: dict[str, Category] = {}
    for cat in data.get("caps", {}).get("categorymappings") or []:
        if not isinstance(cat, dict):
            continue
        cat_id = str(cat.get("id", ""))
        mapped = _map_category(int(cat.get("cat", 0)) if cat.get("cat") else 0)
        if cat_id and mapped is not None:
            category_mapping[cat_id] = mapped

    protocol_str = (data.get("type") or "").lower()
    protocol = Protocol.USENET if "usenet" in protocol_str else Protocol.TORRENT

    return CardigannDefinition(
        site=str(data.get("site", "")),
        name=str(data.get("name") or data.get("site", "")),
        links=[str(link) for link in (data.get("links") or []) if link],
        search_path=search_path,
        search_params=search_block.get("inputs") or {},
        rows_selector=rows_selector,
        fields=fields_map,
        category_mapping=category_mapping,
        protocol=protocol,
    )


def load_definition_yaml(text: str) -> CardigannDefinition:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise IndexerError("cardigann: YAML root must be a mapping")
    return load_definition(data)


def _map_category(cat_id: int) -> Category | None:
    if 2000 <= cat_id < 3000:
        return Category.MOVIES
    if 5000 <= cat_id < 6000:
        return Category.TV
    if 3000 <= cat_id < 4000:
        return Category.MUSIC
    if 7000 <= cat_id < 8000:
        return Category.BOOKS
    return None


class CardigannIndexer(Indexer):
    """Minimal-subset Cardigann adapter.

    Supports ``search``-only sites that do not require login. Good enough
    for public/open trackers and a proof of the pipeline. Login, session
    cookies, pagination and the full selector/filter language are deferred
    until we need them.
    """

    def __init__(
        self,
        definition: CardigannDefinition,
        *,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.definition = definition
        self.name = definition.name
        self.indexer_type = IndexerType.CARDIGANN
        self.protocol = definition.protocol
        self.base_url = (base_url or (definition.links[0] if definition.links else "")).rstrip("/")
        if not self.base_url:
            raise IndexerError(f"cardigann({definition.name}): no base URL configured")
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def test_connection(self) -> IndexerHealth:
        try:
            resp = await self._client.get(self.base_url)
        except httpx.HTTPError as e:
            return IndexerHealth(ok=False, message=str(e))
        if resp.status_code >= 400:
            return IndexerHealth(ok=False, message=f"HTTP {resp.status_code}")
        return IndexerHealth(ok=True)

    async def search(self, query: SearchQuery) -> list[Release]:
        params: dict[str, Any] = {}
        for key, template in (self.definition.search_params or {}).items():
            if isinstance(template, str):
                params[key] = template.replace("{{.Query.Keywords}}", query.terms)
            else:
                params[key] = template
        if "q" not in params and "search" not in params and "query" not in params:
            params["q"] = query.terms

        url = self.base_url + self.definition.search_path
        try:
            resp = await self._client.get(url, params=params)
        except httpx.HTTPError as e:
            raise IndexerError(f"{self.name}: request failed: {e}") from e
        if resp.status_code >= 400:
            raise IndexerError(f"{self.name}: HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select(self.definition.rows_selector)

        releases: list[Release] = []
        for row in rows[: query.limit]:
            release = self._extract_release(row)
            if release is not None:
                releases.append(release)
        return releases

    def _extract_release(self, row: Tag) -> Release | None:
        title = self._extract_field(row, "title")
        if not title:
            return None
        download_url = self._extract_field(row, "download") or self._extract_field(row, "details")
        if download_url and not download_url.startswith(("http://", "https://", "magnet:")):
            download_url = self.base_url + (
                download_url if download_url.startswith("/") else f"/{download_url}"
            )

        size = _parse_size(self._extract_field(row, "size"))
        infohash = self._extract_field(row, "infohash") or None
        category = self._extract_field(row, "category")

        return Release(
            title=title,
            protocol=self.protocol,
            download_url=download_url,
            size=size,
            infohash=infohash,
            category=category,
            source=self.name,
        )

    def _extract_field(self, row: Tag, key: str) -> str | None:
        spec = self.definition.fields.get(key)
        if spec is None:
            return None
        if spec.text is not None:
            return spec.text

        target: Tag | None = row
        if spec.selector:
            target = row.select_one(spec.selector)
        if target is None:
            return None

        value: str | None
        if spec.attribute:
            raw = target.get(spec.attribute)
            value = (raw[0] if raw else None) if isinstance(raw, list) else raw
        else:
            value = target.get_text(" ", strip=True)

        if spec.remove and value:
            value = re.sub(spec.remove, "", value).strip()

        for flt in spec.filters:
            value = self._apply_filter(value, flt)

        return value

    def _apply_filter(self, value: str | None, flt: dict[str, Any]) -> str | None:
        if value is None:
            return None
        name = flt.get("name")
        args = flt.get("args")
        if name == "replace" and isinstance(args, list) and len(args) == 2:
            return value.replace(args[0], args[1])
        if name == "regexp" and isinstance(args, str):
            match = re.search(args, value)
            return match.group(0) if match else value
        if name == "append" and isinstance(args, str):
            return value + args
        if name == "prepend" and isinstance(args, str):
            return args + value
        return value
