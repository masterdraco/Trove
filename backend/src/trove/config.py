from __future__ import annotations

import contextlib
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRET_FILE_NAME = "session.secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TROVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    config_dir: Path = Field(default=Path("./config"))
    data_dir: Path = Field(default=Path("./data"))

    database_url: str | None = None

    session_secret: str | None = Field(
        default=None,
        description=(
            "HMAC secret for signed session cookies and credential encryption. "
            "If unset, a random 32-byte secret is generated on first run and "
            "persisted to <config_dir>/session.secret."
        ),
    )
    session_cookie_name: str = "trove_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days

    ai_enabled: bool = True
    ai_model: str = "ollama/gemma4:latest"
    ai_endpoint: str = "http://localhost:11434"
    ai_cache_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # In dev the SvelteKit dev-server runs on :5173. In production the UI
    # is served from the same origin as the API, so CORS is not needed.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    log_level: str = "INFO"
    log_json: bool = False

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def ensure_secret(self) -> None:
        if self.session_secret:
            return
        secret_path = self.config_dir / SECRET_FILE_NAME
        if secret_path.exists():
            self.session_secret = secret_path.read_text(encoding="utf-8").strip()
            return
        new_secret = secrets.token_urlsafe(48)
        secret_path.write_text(new_secret, encoding="utf-8")
        with contextlib.suppress(OSError):
            secret_path.chmod(0o600)
        self.session_secret = new_secret

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.config_dir / "trove.db"
        return f"sqlite:///{db_path}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    settings.ensure_secret()
    return settings
