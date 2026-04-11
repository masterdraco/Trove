from __future__ import annotations

from typing import Any

from trove.clients import (
    ClientError,
    ClientType,
    DownloadClient,
    Protocol,
    TorrentClient,
    UsenetClient,
)
from trove.clients.deluge import DelugeClient
from trove.clients.nzbget import NzbgetClient
from trove.clients.sabnzbd import SabnzbdClient
from trove.clients.transmission import TransmissionClient
from trove.models.client import Client
from trove.utils.crypto import decrypt_json, encrypt_json


def encrypt_credentials(creds: dict[str, Any]) -> str:
    return encrypt_json(creds)


def decrypt_credentials(cipher: str) -> dict[str, Any]:
    return decrypt_json(cipher)


def _build(client_type: ClientType, url: str, creds: dict[str, Any]) -> DownloadClient:
    if client_type is ClientType.TRANSMISSION:
        return TransmissionClient(
            url,
            username=creds.get("username") or None,
            password=creds.get("password") or None,
        )
    if client_type is ClientType.DELUGE:
        password = creds.get("password")
        if not password:
            raise ClientError("deluge: password is required")
        return DelugeClient(url, password=password)
    if client_type is ClientType.SABNZBD:
        api_key = creds.get("api_key")
        if not api_key:
            raise ClientError("sabnzbd: api_key is required")
        return SabnzbdClient(url, api_key=api_key)
    if client_type is ClientType.NZBGET:
        username = creds.get("username") or ""
        password = creds.get("password") or ""
        return NzbgetClient(url, username=username, password=password)
    raise ClientError(f"unknown client type: {client_type}")


def build_driver(client: Client) -> DownloadClient:
    try:
        client_type = ClientType(client.type)
    except ValueError as e:
        raise ClientError(f"unknown client type: {client.type}") from e
    creds = decrypt_json(client.credentials_cipher)
    return _build(client_type, client.url, creds)


def build_transient(client_type: ClientType, url: str, creds: dict[str, Any]) -> DownloadClient:
    """Build a driver for a client that isn't persisted yet (for pre-save test)."""
    return _build(client_type, url, creds)


def protocol_for(client: Client) -> Protocol:
    return ClientType(client.type).protocol


def ensure_torrent(driver: DownloadClient) -> TorrentClient:
    if not isinstance(driver, TorrentClient):
        raise ClientError(f"{driver.client_type} is not a torrent client")
    return driver


def ensure_usenet(driver: DownloadClient) -> UsenetClient:
    if not isinstance(driver, UsenetClient):
        raise ClientError(f"{driver.client_type} is not a usenet client")
    return driver
