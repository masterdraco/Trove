from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from trove.config import get_settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    secret = get_settings().session_secret
    if not secret:
        raise RuntimeError("session_secret is not initialised")
    return Fernet(_derive_fernet_key(secret))


def encrypt_json(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet().encrypt(blob).decode("ascii")


def decrypt_json(token: str) -> dict[str, Any]:
    try:
        blob = _fernet().decrypt(token.encode("ascii"))
    except InvalidToken as e:
        raise ValueError("failed to decrypt credentials") from e
    return json.loads(blob.decode("utf-8"))
