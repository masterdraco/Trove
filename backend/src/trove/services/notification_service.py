"""Notification fan-out service.

Producers (task engine, download poller, scheduler) call
``dispatch(session, event)`` with a structured :class:`Event`. This
module loads every enabled :class:`NotificationProviderRow` that has
subscribed to the event's ``kind``, converts the event to each
provider's native payload shape, and fires the HTTP request.

Failures in delivery are **always swallowed** — a broken webhook must
never crash the task run that produced the event. Every provider
write-back also updates ``last_sent_*`` on the row so the UI can
show freshness and errors.

Events (see :data:`EVENT_KINDS`):
  task.grabbed        — task successfully handed a release to a client
  task.send_failed    — task found a match but the client rejected it
  task.error          — task crashed with an unhandled exception
  download.started    — state transition queued → downloading
  download.completed  — state transition → completed
  download.failed     — state transition → failed
  download.removed    — state transition → not_found (user removed it)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlmodel import Session, select

from trove.models.notification import NotificationProviderRow
from trove.utils.crypto import decrypt_json, encrypt_json

log = structlog.get_logger()


EVENT_KINDS: tuple[str, ...] = (
    "task.grabbed",
    "task.upgraded",
    "task.send_failed",
    "task.error",
    "download.started",
    "download.completed",
    "download.failed",
    "download.removed",
)

PROVIDER_TYPES: tuple[str, ...] = (
    "discord_webhook",
    "discord_bot",
    "telegram",
    "ntfy",
    "webhook",
)

# Discord embed colors (decimal).
_COLORS = {
    "task.grabbed": 0x3498DB,
    "task.upgraded": 0x9B59B6,
    "task.send_failed": 0xE74C3C,
    "task.error": 0xE74C3C,
    "download.started": 0x95A5A6,
    "download.completed": 0x2ECC71,
    "download.failed": 0xE74C3C,
    "download.removed": 0xF39C12,
}


@dataclass(slots=True)
class Event:
    kind: str
    title: str
    description: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    link: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def color(self) -> int:
        return _COLORS.get(self.kind, 0x3498DB)


def _short_error(e: Exception) -> str:
    return (type(e).__name__ + ": " + str(e))[:240]


async def dispatch(session: Session, event: Event) -> None:
    """Broadcast an event to every enabled provider subscribed to it.

    Runs fire-and-forget. Any provider failure is logged and persisted
    to ``last_sent_*`` but never re-raised. Callers don't need a
    try/except around this.
    """
    try:
        providers = session.exec(
            select(NotificationProviderRow).where(
                NotificationProviderRow.enabled == True  # noqa: E712
            )
        ).all()
    except Exception as e:  # pragma: no cover - defensive
        log.warning("notifications.list_failed", error=str(e))
        return

    for provider in providers:
        try:
            subs = json.loads(provider.events or "[]")
            if event.kind not in subs:
                continue
        except Exception:
            continue
        try:
            await _deliver(provider, event)
            provider.last_sent_at = datetime.now(UTC).replace(tzinfo=None)
            provider.last_sent_ok = True
            provider.last_sent_message = f"{event.kind} -> ok"
            session.add(provider)
        except Exception as e:
            log.warning(
                "notifications.delivery_failed",
                provider=provider.name,
                type=provider.type,
                error=str(e),
            )
            provider.last_sent_at = datetime.now(UTC).replace(tzinfo=None)
            provider.last_sent_ok = False
            provider.last_sent_message = _short_error(e)
            session.add(provider)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover
        log.warning("notifications.commit_failed", error=str(e))
        session.rollback()


async def _deliver(provider: NotificationProviderRow, event: Event) -> None:
    cfg = decrypt_json(provider.config_cipher)
    t = provider.type
    if t == "discord_webhook":
        await _deliver_discord_webhook(cfg, event)
    elif t == "discord_bot":
        await _deliver_discord_bot(cfg, event)
    elif t == "telegram":
        await _deliver_telegram(cfg, event)
    elif t == "ntfy":
        await _deliver_ntfy(cfg, event)
    elif t == "webhook":
        await _deliver_webhook(cfg, event)
    else:
        raise ValueError(f"unknown provider type: {t}")


def _discord_embed(event: Event) -> dict[str, Any]:
    embed: dict[str, Any] = {
        "title": event.title,
        "description": event.description or None,
        "color": event.color,
        "timestamp": event.timestamp.isoformat(),
    }
    if event.fields:
        embed["fields"] = [
            {"name": k, "value": str(v)[:1024], "inline": True} for k, v in event.fields.items()
        ]
    if event.link:
        embed["url"] = event.link
    # Strip None values Discord rejects them.
    return {k: v for k, v in embed.items() if v is not None}


async def _deliver_discord_webhook(cfg: dict[str, Any], event: Event) -> None:
    url = cfg.get("webhook_url")
    if not url:
        raise ValueError("discord_webhook: webhook_url missing")
    payload = {"username": "Trove", "embeds": [_discord_embed(event)]}
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(str(url), json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"discord_webhook HTTP {resp.status_code}: {resp.text[:160]}")


async def _deliver_discord_bot(cfg: dict[str, Any], event: Event) -> None:
    token = cfg.get("bot_token")
    channel_id = cfg.get("channel_id")
    if not token or not channel_id:
        raise ValueError("discord_bot: bot_token and channel_id required")
    api = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = {"embeds": [_discord_embed(event)]}
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(
            api,
            json=payload,
            headers={"Authorization": f"Bot {token}"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"discord_bot HTTP {resp.status_code}: {resp.text[:160]}")


def _telegram_body(event: Event) -> str:
    lines = [f"*{event.title}*"]
    if event.description:
        lines.append(event.description)
    for k, v in event.fields.items():
        lines.append(f"*{k}*: {v}")
    if event.link:
        lines.append(f"[Open]({event.link})")
    return "\n".join(lines)


async def _deliver_telegram(cfg: dict[str, Any], event: Event) -> None:
    token = cfg.get("bot_token")
    chat_id = cfg.get("chat_id")
    if not token or not chat_id:
        raise ValueError("telegram: bot_token and chat_id required")
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": _telegram_body(event),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(api, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"telegram HTTP {resp.status_code}: {resp.text[:160]}")


async def _deliver_ntfy(cfg: dict[str, Any], event: Event) -> None:
    base = str(cfg.get("server_url") or "https://ntfy.sh").rstrip("/")
    topic = cfg.get("topic")
    if not topic:
        raise ValueError("ntfy: topic missing")
    url = f"{base}/{topic}"
    headers: dict[str, str] = {"Title": event.title[:120]}
    if event.link:
        headers["Click"] = event.link
    auth = cfg.get("auth_token")
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    body = event.description or event.title
    if event.fields:
        body += "\n\n" + "\n".join(f"{k}: {v}" for k, v in event.fields.items())
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.post(url, content=body.encode("utf-8"), headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"ntfy HTTP {resp.status_code}: {resp.text[:160]}")


async def _deliver_webhook(cfg: dict[str, Any], event: Event) -> None:
    url = cfg.get("url")
    if not url:
        raise ValueError("webhook: url missing")
    method = str(cfg.get("method") or "POST").upper()
    headers = dict(cfg.get("headers") or {})
    headers.setdefault("Content-Type", "application/json")
    payload = {
        "kind": event.kind,
        "title": event.title,
        "description": event.description,
        "fields": event.fields,
        "link": event.link,
        "timestamp": event.timestamp.isoformat(),
    }
    async with httpx.AsyncClient(timeout=15.0) as c:
        resp = await c.request(method, str(url), json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"webhook HTTP {resp.status_code}: {resp.text[:160]}")


def encrypt_config(cfg: dict[str, Any]) -> str:
    return encrypt_json(cfg)
