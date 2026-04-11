from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlmodel import Session, select

from trove.config import get_settings
from trove.db import get_engine
from trove.models.ai_cache import AiCacheRow
from trove.services import app_settings

log = structlog.get_logger()


@dataclass(slots=True)
class AiConfig:
    enabled: bool
    endpoint: str
    model: str
    temperature: float


def get_effective_config(session: Session | None = None) -> AiConfig:
    """Return the effective AI config with three-tier precedence:

        1. Explicit user override in app_setting table (Settings UI)
        2. Env var (FLEXREPLACE_/TROVE_AI_ENDPOINT etc.)
        3. Spec default in app_settings.REGISTRY

    Using get_override() instead of get() is critical here — get()
    returns the spec default when no DB row exists, which would shadow
    the env var fallback and leave users stuck on localhost even when
    they set TROVE_AI_ENDPOINT explicitly.
    """
    env_settings = get_settings()
    close_session = False
    if session is None:
        session = Session(get_engine())
        close_session = True
    try:
        enabled_override = app_settings.get_override(session, "ai.enabled")
        enabled = bool(enabled_override) if enabled_override is not None else True

        endpoint_override = app_settings.get_override(session, "ai.endpoint")
        endpoint = str(endpoint_override or env_settings.ai_endpoint)

        model_override = app_settings.get_override(session, "ai.model")
        model = str(model_override or env_settings.ai_model)

        temp_int = int(app_settings.get(session, "ai.default_temperature"))
        temperature = max(0.0, min(1.0, temp_int / 100.0)) if temp_int else 0.2

        # Env-level global disable has veto power regardless of DB
        enabled = enabled and env_settings.ai_enabled
    finally:
        if close_session:
            session.close()
    return AiConfig(enabled=enabled, endpoint=endpoint, model=model, temperature=temperature)


def _hash(model: str, system: str | None, prompt: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update((system or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def _read_cache(prompt_hash: str) -> str | None:
    settings = get_settings()
    with Session(get_engine()) as session:
        row = session.exec(select(AiCacheRow).where(AiCacheRow.prompt_hash == prompt_hash)).first()
        if row is None:
            return None
        ttl = row.ttl_seconds or settings.ai_cache_ttl_seconds
        if ttl > 0 and row.created_at + timedelta(seconds=ttl) < datetime.now(UTC):
            session.delete(row)
            session.commit()
            return None
        return row.response


def _write_cache(prompt_hash: str, model: str, response: str, ttl: int) -> None:
    with Session(get_engine()) as session:
        existing = session.exec(
            select(AiCacheRow).where(AiCacheRow.prompt_hash == prompt_hash)
        ).first()
        if existing is not None:
            existing.response = response
            existing.model = model
            existing.created_at = datetime.now(UTC)
            existing.ttl_seconds = ttl
            session.add(existing)
        else:
            session.add(
                AiCacheRow(
                    prompt_hash=prompt_hash,
                    model=model,
                    response=response,
                    ttl_seconds=ttl,
                )
            )
        session.commit()


async def complete(
    prompt: str,
    *,
    system: str | None = None,
    cache: bool = True,
    temperature: float | None = None,
    max_tokens: int | None = 1024,
    config: AiConfig | None = None,
) -> str:
    effective = config or get_effective_config()
    if not effective.enabled:
        raise RuntimeError("AI layer is disabled in settings")

    env_settings = get_settings()
    prompt_hash = _hash(effective.model, system, prompt)
    if cache:
        cached = _read_cache(prompt_hash)
        if cached is not None:
            return cached

    import litellm  # lazy import so settings are loaded first

    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    effective_temp = temperature if temperature is not None else effective.temperature
    try:
        resp = await litellm.acompletion(
            model=effective.model,
            api_base=effective.endpoint,
            messages=messages,
            temperature=effective_temp,
            max_tokens=max_tokens,
        )
    except Exception as e:
        log.warning("ai.complete.failed", error=str(e))
        raise

    content = ""
    try:
        content = resp.choices[0].message.content or ""
    except (AttributeError, IndexError):
        content = str(resp)

    if cache and content:
        _write_cache(prompt_hash, effective.model, content, env_settings.ai_cache_ttl_seconds)

    return content
