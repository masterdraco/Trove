"""Quality profile storage + resolution.

A "quality profile" is a named bundle of ranking weights that
``task_engine.score_hit`` uses to pick the best release for a task.
Shape:

    {
        "name": "default-2160p",
        "quality_tiers": {"2160p": 4, "1080p": 3, "720p": 2, "sd": 1},
        "source_tiers": {"remux": 6, "bluray": 5, "web-dl": 4, "cam": -10, ...},
        "codec_bonus": {"x265": 2, "hevc": 2, "x264": 1},
        "reject_tokens": ["cam", "telesync", "hdcam", "workprint", "hdts"],
        "prefer_quality": "2160p",
        "min_acceptable_tier": 0,
    }

Profiles are persisted as a single JSON blob in the ``app_setting``
table under the key ``quality_profiles``. One blob holds the full
list plus the name of the default profile, e.g.

    {
        "default": "default-2160p",
        "profiles": {
            "default-2160p": { ... },
            "1080p-budget": { ... },
        }
    }

This keeps profiles self-contained without needing a dedicated
table and migration.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from trove.models.app_setting import AppSettingRow

SETTING_KEY = "quality_profiles"

# The historical hardcoded behaviour, used as both the default profile
# and the fallback when a task references a profile that no longer
# exists (deleted but the task's config_yaml still names it).
DEFAULT_PROFILE_NAME = "default-2160p"

DEFAULT_PROFILE: dict[str, Any] = {
    "name": DEFAULT_PROFILE_NAME,
    "quality_tiers": {
        "2160p": 4,
        "4k": 4,
        "uhd": 4,
        "1080p": 3,
        "720p": 2,
        "576p": 1,
        "480p": 1,
        "sd": 1,
    },
    "source_tiers": {
        "remux": 6,
        "bluray": 5,
        "blu-ray": 5,
        "bdrip": 4,
        "web-dl": 4,
        "webdl": 4,
        "webrip": 3,
        "hdtv": 2,
        "dvdrip": 1,
        "hdts": -5,
        "telesync": -5,
        "cam": -10,
    },
    "codec_bonus": {
        "x265": 2,
        "h265": 2,
        "h.265": 2,
        "hevc": 2,
        "x264": 1,
        "h264": 1,
    },
    "reject_tokens": ["cam", "telesync", "hdcam", "workprint"],
    "prefer_quality": "2160p",
    "min_acceptable_tier": 0,
}


def _load_store(session: Session) -> dict[str, Any]:
    row = session.exec(select(AppSettingRow).where(AppSettingRow.key == SETTING_KEY)).first()
    if row is None or not row.value:
        return {
            "default": DEFAULT_PROFILE_NAME,
            "profiles": {DEFAULT_PROFILE_NAME: DEFAULT_PROFILE},
        }
    try:
        data = json.loads(row.value)
    except Exception:
        return {
            "default": DEFAULT_PROFILE_NAME,
            "profiles": {DEFAULT_PROFILE_NAME: DEFAULT_PROFILE},
        }
    if not isinstance(data, dict) or "profiles" not in data:
        return {
            "default": DEFAULT_PROFILE_NAME,
            "profiles": {DEFAULT_PROFILE_NAME: DEFAULT_PROFILE},
        }
    # Ensure the default profile is always available so tasks can
    # fall back to it cleanly.
    profiles = data.get("profiles") or {}
    if DEFAULT_PROFILE_NAME not in profiles:
        profiles[DEFAULT_PROFILE_NAME] = DEFAULT_PROFILE
        data["profiles"] = profiles
    if not data.get("default"):
        data["default"] = DEFAULT_PROFILE_NAME
    return data


def _save_store(session: Session, data: dict[str, Any]) -> None:
    row = session.exec(select(AppSettingRow).where(AppSettingRow.key == SETTING_KEY)).first()
    serialised = json.dumps(data, separators=(",", ":"))
    if row is None:
        session.add(AppSettingRow(key=SETTING_KEY, value=serialised))
    else:
        row.value = serialised
        session.add(row)
    session.commit()


def list_profiles(session: Session) -> dict[str, Any]:
    return _load_store(session)


def get_profile(session: Session, name: str | None) -> dict[str, Any]:
    """Return a profile by name, falling back to default + hardcoded.

    Never raises; always returns a usable dict. Callers can trust the
    shape (quality_tiers, source_tiers, codec_bonus, reject_tokens,
    prefer_quality).
    """
    store = _load_store(session)
    profiles = store.get("profiles") or {}
    if name and name in profiles:
        return profiles[name]
    default_name = store.get("default") or DEFAULT_PROFILE_NAME
    if default_name in profiles:
        return profiles[default_name]
    return DEFAULT_PROFILE


def upsert_profile(session: Session, profile: dict[str, Any]) -> None:
    """Insert or replace a profile by name."""
    name = profile.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("profile.name is required")
    store = _load_store(session)
    store["profiles"][name] = profile
    _save_store(session, store)


def delete_profile(session: Session, name: str) -> None:
    if name == DEFAULT_PROFILE_NAME:
        raise ValueError("cannot delete the built-in default profile")
    store = _load_store(session)
    profiles = store.get("profiles") or {}
    profiles.pop(name, None)
    # If the default pointed at the one we just removed, reset it.
    if store.get("default") == name:
        store["default"] = DEFAULT_PROFILE_NAME
    store["profiles"] = profiles
    _save_store(session, store)


def set_default(session: Session, name: str) -> None:
    store = _load_store(session)
    if name not in (store.get("profiles") or {}):
        raise ValueError(f"unknown profile: {name}")
    store["default"] = name
    _save_store(session, store)
