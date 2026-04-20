from __future__ import annotations

import logging
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

log = logging.getLogger(__name__)
_WARNED_FILTERS: set[str] = set()

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
    config_defaults: dict[str, str] = field(default_factory=dict)  # from settings: block


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
        raw_cat = cat.get("cat", 0)
        try:
            numeric_cat = int(raw_cat)
        except (ValueError, TypeError):
            numeric_cat = 0
        mapped = _map_category(numeric_cat)
        if cat_id and mapped is not None:
            category_mapping[cat_id] = mapped

    protocol_str = (data.get("type") or "").lower()
    protocol = Protocol.USENET if "usenet" in protocol_str else Protocol.TORRENT

    config_defaults: dict[str, str] = {}
    for item in data.get("settings") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        default = item.get("default")
        if default is None:
            continue
        # Normalize bools to Go-template casing
        if isinstance(default, bool):
            config_defaults[name] = "True" if default else "False"
        else:
            config_defaults[name] = str(default)

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
        config_defaults=config_defaults,
    )


def load_definition_yaml(text: str) -> CardigannDefinition:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise IndexerError("cardigann: YAML root must be a mapping")
    return load_definition(data)


# ---------------------------------------------------------------------------
# Minimal Go-template subset evaluator for Prowlarr YAMLs.
#
# Supported:
#   {{ .Keywords }}                                -> query terms or ""
#   {{ .Query.IMDBID }}, {{ .Query.TMDBID }}       -> always ""
#   {{ .Config.X }}                                -> config[X] or ""
#   {{ if .Keywords }}A{{ else }}B{{ end }}        -> A if keywords non-empty, else B
#   {{ if and .Keywords ... }}A{{ else }}B{{ end }}-> same (conservative: keywords-present check)
#   {{ if or .Query.IMDBID .Keywords }}...{{ end }}-> keywords-present check
#   {{ range .Categories }}...{{ end }}            -> "" (categories not piped through)
#   {{ join .Categories "," }}                     -> ""
#
# NOT supported: arbitrary nested ifs, function calls inside template
# expressions, range loops over arbitrary collections.
# Unrecognized templates pass through unchanged (never crash).
# ---------------------------------------------------------------------------

_IF_ELSE_END_RE = re.compile(
    r"\{\{\s*if\s+(.+?)\s*\}\}(.*?)\{\{\s*else\s*\}\}(.*?)\{\{\s*end\s*\}\}",
    re.DOTALL,
)
_IF_END_RE = re.compile(
    r"\{\{\s*if\s+(.+?)\s*\}\}(.*?)\{\{\s*end\s*\}\}",
    re.DOTALL,
)
_RANGE_END_RE = re.compile(
    r"\{\{\s*range\s+.+?\s*\}\}.*?\{\{\s*end\s*\}\}",
    re.DOTALL,
)
_JOIN_RE = re.compile(
    r'\{\{\s*join\s+\.Categories\s+"[^"]*"\s*\}\}',
)
# Go template `or` expression used as a value (not inside an if condition).
# Example: {{ or .Query.IMDBID .Keywords }}
# Returns the first truthy arg. We only support .Query.* (always empty) and
# .Keywords — enough for the YAMLs in the current catalog.
_OR_EXPR_RE = re.compile(r"\{\{\s*or\s+(.+?)\s*\}\}")
# Go template `re_replace` function call used inline (not as a field filter).
# Example: {{ re_replace .Config.sort "_" "" }}
_RE_REPLACE_INLINE_RE = re.compile(
    r'\{\{\s*re_replace\s+\.Config\.([\w\-]+)\s+"([^"]*)"\s+"([^"]*)"\s*\}\}'
)
_KEYWORDS_RE = re.compile(r"\{\{\s*\.Keywords\s*\}\}")
_QUERY_IMDB_RE = re.compile(r"\{\{\s*\.Query\.(IMDBID|TMDBID|TVDBID)\s*\}\}")
_CONFIG_RE = re.compile(r"\{\{\s*\.Config\.([\w\-]+)\s*\}\}")


def expand_template(
    text: str,
    *,
    keywords: str = "",
    config: dict[str, str] | None = None,
) -> str:
    """Expand a Cardigann/Go-template string.

    See the module comment above for the supported subset. Anything unrecognized
    passes through unchanged so upstream failures are visible rather than
    silently producing wrong URLs.
    """
    if "{{" not in text:
        return text
    cfg = config or {}
    keywords_present = bool(keywords)

    # Drop range blocks entirely (categories-iter is the only real use).
    text = _RANGE_END_RE.sub("", text)
    # join .Categories -> empty
    text = _JOIN_RE.sub("", text)

    # Repeatedly resolve if/else/end from the innermost occurrence outward.
    # Prowlarr chains them, so loop until stable.
    for _ in range(10):
        before = text

        def _ifelse(m: re.Match[str]) -> str:
            return m.group(2) if keywords_present else m.group(3)

        text = _IF_ELSE_END_RE.sub(_ifelse, text)
        if text == before:
            break

    # Bare {{ if ... }}X{{ end }} without else -> X if keywords else ""
    for _ in range(10):
        before = text

        def _if(m: re.Match[str]) -> str:
            return m.group(2) if keywords_present else ""

        text = _IF_END_RE.sub(_if, text)
        if text == before:
            break

    # `or` expression as value: return first truthy arg.
    def _or_value(m: re.Match[str]) -> str:
        args = m.group(1).split()
        for arg in args:
            if arg == ".Keywords":
                if keywords_present:
                    return keywords
            elif arg.startswith(".Query."):
                # .Query.IMDBID, .Query.TMDBID, etc. are always empty here.
                continue
            elif arg.startswith(".Config."):
                name = arg[len(".Config.") :]
                val = cfg.get(name, "")
                if val:
                    return val
            # Unknown reference → skip and try next arg.
        return ""

    text = _OR_EXPR_RE.sub(_or_value, text)

    # Inline re_replace on a Config value.
    def _inline_re_replace(m: re.Match[str]) -> str:
        config_name, pattern, replacement = m.group(1), m.group(2), m.group(3)
        source = cfg.get(config_name, "")
        try:
            return re.sub(pattern, replacement, source)
        except re.error:
            return source

    text = _RE_REPLACE_INLINE_RE.sub(_inline_re_replace, text)

    # Variable substitutions.
    text = _KEYWORDS_RE.sub(lambda _: keywords, text)
    text = _QUERY_IMDB_RE.sub("", text)

    def _cfg(m: re.Match[str]) -> str:
        return cfg.get(m.group(1), "")

    text = _CONFIG_RE.sub(_cfg, text)

    # .Result.* is not a request-time substitution — leave intact for
    # field-extraction-time expansion (a separate call site).

    return text


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
        cfg = self.definition.config_defaults
        kw = query.terms or ""
        params: dict[str, Any] = {}
        for key, template in (self.definition.search_params or {}).items():
            if isinstance(template, str):
                params[key] = expand_template(template, keywords=kw, config=cfg)
            else:
                params[key] = template
        if "q" not in params and "search" not in params and "query" not in params:
            params["q"] = kw

        path = expand_template(self.definition.search_path, keywords=kw, config=cfg)
        # Prowlarr YAMLs commonly emit paths like "search/all/..." (no leading
        # slash) that fuse into the hostname via string concatenation and break
        # DNS resolution. Normalize before joining; pass absolute URLs through.
        if path.startswith(("http://", "https://")):
            url = path
        else:
            if path and not path.startswith("/"):
                path = "/" + path
            url = self.base_url + path
        try:
            resp = await self._client.get(url, params=params)
        except httpx.HTTPError as e:
            raise IndexerError(f"{self.name}: request failed: {e}") from e
        if resp.status_code >= 400:
            raise IndexerError(f"{self.name}: HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "lxml")
        rows_selector = expand_template(self.definition.rows_selector, keywords=kw, config=cfg)
        rows = soup.select(rows_selector)

        releases: list[Release] = []
        for row in rows[: query.limit]:
            release = self._extract_release(row, keywords=kw, config=cfg)
            if release is not None:
                releases.append(release)
        return releases

    def _extract_release(
        self,
        row: Tag,
        *,
        keywords: str = "",
        config: dict[str, str] | None = None,
    ) -> Release | None:
        title = self._extract_field(row, "title", keywords=keywords, config=config)
        if not title:
            return None
        download_url = self._extract_field(
            row, "download", keywords=keywords, config=config
        ) or self._extract_field(row, "details", keywords=keywords, config=config)
        if download_url and not download_url.startswith(("http://", "https://", "magnet:")):
            download_url = self.base_url + (
                download_url if download_url.startswith("/") else f"/{download_url}"
            )

        size = _parse_size(self._extract_field(row, "size", keywords=keywords, config=config))
        infohash = self._extract_field(row, "infohash", keywords=keywords, config=config) or None
        category = self._extract_field(row, "category", keywords=keywords, config=config)

        return Release(
            title=title,
            protocol=self.protocol,
            download_url=download_url,
            size=size,
            infohash=infohash,
            category=category,
            source=self.name,
        )

    def _extract_field(
        self,
        row: Tag,
        key: str,
        *,
        keywords: str = "",
        config: dict[str, str] | None = None,
    ) -> str | None:
        spec = self.definition.fields.get(key)
        if spec is None:
            return None
        if spec.text is not None:
            return spec.text

        target: Tag | None = row
        selector = (
            expand_template(spec.selector, keywords=keywords, config=(config or {}))
            if spec.selector
            else None
        )
        if selector:
            target = row.select_one(selector)
        if target is None:
            return None

        value: str | None
        attribute = (
            expand_template(spec.attribute, keywords=keywords, config=(config or {}))
            if spec.attribute
            else None
        )
        if attribute:
            raw = target.get(attribute)
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
        if name == "urldecode":
            from urllib.parse import unquote

            return unquote(value)
        if name == "split" and isinstance(args, list) and len(args) >= 2:
            delimiter = str(args[0])
            try:
                index = int(args[1])
            except (TypeError, ValueError):
                return value
            parts = value.split(delimiter)
            if not parts:
                return value
            try:
                return parts[index]
            except IndexError:
                return value
        if name == "trim":
            if isinstance(args, str) and args:
                return value.strip(args)
            return value.strip()
        if name == "tolower":
            return value.lower()
        if name == "re_replace" and isinstance(args, list) and len(args) >= 2:
            pattern = str(args[0])
            replacement = str(args[1])
            try:
                return re.sub(pattern, replacement, value)
            except re.error:
                return value
        if name and name not in _WARNED_FILTERS:
            _WARNED_FILTERS.add(name)
            log.warning("cardigann: unknown filter %r — passing value through unchanged", name)
        return value
