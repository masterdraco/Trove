from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class NotificationProviderRow(SQLModel, table=True):
    __tablename__ = "notification_provider"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1, max_length=64)
    # discord_webhook | discord_bot | telegram | ntfy | webhook
    type: str = Field(max_length=32)
    # Encrypted JSON blob with provider-specific config:
    #   discord_webhook: {"webhook_url": "..."}
    #   discord_bot:     {"bot_token": "...", "channel_id": "..."}
    #   telegram:        {"bot_token": "...", "chat_id": "..."}
    #   ntfy:            {"server_url": "https://ntfy.sh", "topic": "...",
    #                     "auth_token": "..." (optional)}
    #   webhook:         {"url": "...", "method": "POST",
    #                     "headers": {...} (optional)}
    config_cipher: str = Field(max_length=4096)
    # JSON-encoded list of event kinds this provider should receive:
    #   ["task.grabbed", "download.completed", "download.failed", ...]
    events: str = Field(
        default='["task.grabbed","download.completed","download.failed"]', max_length=1024
    )
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)
    last_sent_at: datetime | None = Field(default=None)
    last_sent_ok: bool | None = Field(default=None)
    last_sent_message: str | None = Field(default=None, max_length=512)
