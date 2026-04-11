"""Persistent app-level settings stored in the app_setting table.

Unlike the env-driven :class:`trove.config.Settings`, these values
are editable at runtime from the UI and persist across restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlmodel import Session, select

from trove.models.app_setting import AppSettingRow

SettingType = Literal["int", "str", "bool"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type: SettingType
    default: Any
    label: str
    description: str
    group: str = "general"
    min_value: int | None = None
    max_value: int | None = None


_SENTINEL_AI_ENDPOINT = "http://localhost:11434"
_SENTINEL_AI_MODEL = "ollama/gemma4:latest"


REGISTRY: dict[str, SettingSpec] = {
    "rss.default_retention_days": SettingSpec(
        key="rss.default_retention_days",
        type="int",
        default=90,
        label="Default retention (days)",
        description=(
            "How many days newly-added RSS feeds should keep cached items before "
            "cleanup. Individual feeds can override this."
        ),
        group="rss",
        min_value=1,
        max_value=3650,
    ),
    "rss.default_poll_interval_seconds": SettingSpec(
        key="rss.default_poll_interval_seconds",
        type="int",
        default=600,
        label="Default poll interval (seconds)",
        description=("Default polling interval for newly-added RSS feeds. Minimum 60s."),
        group="rss",
        min_value=60,
        max_value=86400,
    ),
    "search.default_min_seeders": SettingSpec(
        key="search.default_min_seeders",
        type="int",
        default=0,
        label="Default minimum seeders",
        description="Pre-fill the search page with this minimum-seeders filter.",
        group="search",
        min_value=0,
        max_value=10000,
    ),
    "ai.enabled": SettingSpec(
        key="ai.enabled",
        type="bool",
        default=True,
        label="Enabled",
        description="Turn the AI assistant on or off globally.",
        group="ai",
    ),
    "ai.endpoint": SettingSpec(
        key="ai.endpoint",
        type="str",
        default=_SENTINEL_AI_ENDPOINT,
        label="Endpoint URL",
        description="Base URL of the Ollama server (e.g. http://localhost:11434).",
        group="ai",
    ),
    "ai.model": SettingSpec(
        key="ai.model",
        type="str",
        default=_SENTINEL_AI_MODEL,
        label="Model",
        description=(
            "LiteLLM model identifier. For Ollama use 'ollama/<tag>', e.g. "
            "'ollama/gemma4:latest' or 'ollama/llama3.1:8b'."
        ),
        group="ai",
    ),
    "ai.default_temperature": SettingSpec(
        key="ai.default_temperature",
        type="int",
        default=20,
        label="Temperature (0-100)",
        description=("LLM creativity setting x100. 20 = 0.2 (focused), 70 = 0.7 (creative)."),
        group="ai",
        min_value=0,
        max_value=100,
    ),
    "tmdb.api_token": SettingSpec(
        key="tmdb.api_token",
        type="str",
        default="",
        label="TMDB API read token",
        description=(
            "Bearer token from your TMDB account (v4 read access token). Get one for free at "
            "https://www.themoviedb.org/settings/api — required for the Discover page and "
            "poster-rich watchlist. Leave blank to disable."
        ),
        group="tmdb",
    ),
}


def _coerce(spec: SettingSpec, raw: str) -> Any:
    if spec.type == "int":
        try:
            return int(raw)
        except ValueError:
            return spec.default
    if spec.type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    return raw


def _serialize(spec: SettingSpec, value: Any) -> str:
    if spec.type == "int":
        return str(int(value))
    if spec.type == "bool":
        return "1" if value else "0"
    return str(value)


def get(session: Session, key: str) -> Any:
    """Return the effective value — DB row if present, otherwise the
    registered spec default. Callers that always want *some* value use
    this. Callers that need to distinguish "explicitly saved" from
    "unset" should use get_override() instead.
    """
    spec = REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"unknown setting: {key}")
    row = session.get(AppSettingRow, key)
    if row is None:
        return spec.default
    return _coerce(spec, row.value)


def get_override(session: Session, key: str) -> Any | None:
    """Return the DB value only, or None if the user has never saved an
    explicit override. Used for three-tier precedence where env vars
    should be able to shadow the spec default but be themselves
    shadowed by user-saved values.
    """
    spec = REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"unknown setting: {key}")
    row = session.get(AppSettingRow, key)
    if row is None:
        return None
    return _coerce(spec, row.value)


def get_int(session: Session, key: str) -> int:
    value = get(session, key)
    return int(value) if isinstance(value, (int, float, str)) else 0


def set_value(session: Session, key: str, value: Any) -> None:
    spec = REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"unknown setting: {key}")
    if spec.type == "int":
        ival = int(value)
        if spec.min_value is not None and ival < spec.min_value:
            raise ValueError(f"{key} must be >= {spec.min_value}")
        if spec.max_value is not None and ival > spec.max_value:
            raise ValueError(f"{key} must be <= {spec.max_value}")
        value = ival
    serialized = _serialize(spec, value)
    row = session.get(AppSettingRow, key)
    if row is None:
        row = AppSettingRow(key=key, value=serialized, updated_at=datetime.now(UTC))
    else:
        row.value = serialized
        row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()


def list_all(session: Session) -> list[dict[str, Any]]:
    # Ensure every registered key has a current value (either stored or default).
    stored: dict[str, str] = {}
    for row in session.exec(select(AppSettingRow)).all():
        stored[row.key] = row.value
    out: list[dict[str, Any]] = []
    for spec in REGISTRY.values():
        raw = stored.get(spec.key)
        value = _coerce(spec, raw) if raw is not None else spec.default
        out.append(
            {
                "key": spec.key,
                "type": spec.type,
                "label": spec.label,
                "description": spec.description,
                "group": spec.group,
                "default": spec.default,
                "value": value,
                "min_value": spec.min_value,
                "max_value": spec.max_value,
            }
        )
    return out
