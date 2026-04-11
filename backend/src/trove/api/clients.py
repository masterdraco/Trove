from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.clients import (
    AddOptions,
    ClientError,
    ClientType,
    Protocol,
    Release,
    TorrentClient,
    UsenetClient,
)
from trove.models.client import Client
from trove.models.user import User
from trove.services import client_registry

router = APIRouter()


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: ClientType
    url: str = Field(min_length=1, max_length=512)
    credentials: dict[str, Any] = Field(default_factory=dict)
    default_category: str | None = None
    default_save_path: str | None = None
    enabled: bool = True


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    url: str | None = Field(default=None, min_length=1, max_length=512)
    credentials: dict[str, Any] | None = None
    default_category: str | None = None
    default_save_path: str | None = None
    enabled: bool | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    type: ClientType
    url: str
    protocol: Protocol
    default_category: str | None
    default_save_path: str | None
    enabled: bool
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None


class ClientTestResult(BaseModel):
    ok: bool
    version: str | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    categories: list[str] = Field(default_factory=list)


class ClientTestRequest(BaseModel):
    type: ClientType
    url: str
    credentials: dict[str, Any] = Field(default_factory=dict)


class SendRequest(BaseModel):
    title: str
    download_url: str
    category: str | None = None
    save_path: str | None = None
    paused: bool = False
    priority: int | None = None


def _to_out(client: Client) -> ClientOut:
    assert client.id is not None
    return ClientOut(
        id=client.id,
        name=client.name,
        type=ClientType(client.type),
        url=client.url,
        protocol=ClientType(client.type).protocol,
        default_category=client.default_category,
        default_save_path=client.default_save_path,
        enabled=client.enabled,
        last_test_at=client.last_test_at,
        last_test_ok=client.last_test_ok,
        last_test_message=client.last_test_message,
    )


@router.get("", response_model=list[ClientOut])
async def list_clients(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[ClientOut]:
    rows = session.exec(select(Client).order_by(Client.name)).all()
    return [_to_out(c) for c in rows]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> ClientOut:
    existing = session.exec(select(Client).where(Client.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")

    client = Client(
        name=payload.name,
        type=payload.type.value,
        url=payload.url,
        credentials_cipher=client_registry.encrypt_credentials(payload.credentials),
        default_category=payload.default_category,
        default_save_path=payload.default_save_path,
        enabled=payload.enabled,
    )
    session.add(client)
    session.commit()
    session.refresh(client)
    return _to_out(client)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: int,
    payload: ClientUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> ClientOut:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    if payload.name is not None and payload.name != client.name:
        clash = session.exec(select(Client).where(Client.name == payload.name)).first()
        if clash is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")
        client.name = payload.name
    if payload.url is not None:
        client.url = payload.url
    if payload.credentials is not None:
        client.credentials_cipher = client_registry.encrypt_credentials(payload.credentials)
    if payload.default_category is not None:
        client.default_category = payload.default_category or None
    if payload.default_save_path is not None:
        client.default_save_path = payload.default_save_path or None
    if payload.enabled is not None:
        client.enabled = payload.enabled

    session.add(client)
    session.commit()
    session.refresh(client)
    return _to_out(client)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    session.delete(client)
    session.commit()


async def _run_test(driver) -> ClientTestResult:  # type: ignore[no-untyped-def]
    try:
        health = await driver.test_connection()
        categories: list[str] = []
        if health.ok:
            try:
                categories = await driver.list_categories()
            except ClientError:
                categories = []
        return ClientTestResult(
            ok=health.ok,
            version=health.version,
            message=health.message,
            details=health.details,
            categories=categories,
        )
    finally:
        await driver.close()


@router.post("/test", response_model=ClientTestResult)
async def test_transient(
    payload: ClientTestRequest,
    _user: User = Depends(current_user),
) -> ClientTestResult:
    try:
        driver = client_registry.build_transient(payload.type, payload.url, payload.credentials)
    except ClientError as e:
        return ClientTestResult(ok=False, message=str(e))
    return await _run_test(driver)


@router.post("/{client_id}/test", response_model=ClientTestResult)
async def test_existing(
    client_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> ClientTestResult:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    try:
        driver = client_registry.build_driver(client)
    except ClientError as e:
        return ClientTestResult(ok=False, message=str(e))
    result = await _run_test(driver)

    client.last_test_at = datetime.now(UTC)
    client.last_test_ok = result.ok
    client.last_test_message = (result.message or "")[:512] or None
    session.add(client)
    session.commit()

    return result


@router.post("/{client_id}/send", status_code=status.HTTP_200_OK)
async def send_to_client(
    client_id: int,
    payload: SendRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    protocol = ClientType(client.type).protocol
    release = Release(
        title=payload.title,
        protocol=protocol,
        download_url=payload.download_url,
    )
    options = AddOptions(
        category=payload.category or client.default_category,
        save_path=payload.save_path or client.default_save_path,
        paused=payload.paused,
        priority=payload.priority,
    )

    try:
        driver = client_registry.build_driver(client)
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        if protocol is Protocol.TORRENT:
            assert isinstance(driver, TorrentClient)
            result = await driver.add_torrent(release, options)
        else:
            assert isinstance(driver, UsenetClient)
            result = await driver.add_nzb(release, options)
    except ClientError as e:
        await driver.close()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    finally:
        await driver.close()

    return {
        "ok": result.ok,
        "identifier": result.identifier,
        "message": result.message,
    }


@router.post("/{client_id}/send-file", status_code=status.HTTP_200_OK)
async def send_file_to_client(
    client_id: int,
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(...)],
    category: Annotated[str | None, Form()] = None,
    save_path: Annotated[str | None, Form()] = None,
    paused: Annotated[bool, Form()] = False,
    priority: Annotated[int | None, Form()] = None,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> dict[str, Any]:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    content = await file.read()
    protocol = ClientType(client.type).protocol
    release = Release(title=title, protocol=protocol, content=content)
    options = AddOptions(
        category=category or client.default_category,
        save_path=save_path or client.default_save_path,
        paused=paused,
        priority=priority,
    )

    try:
        driver = client_registry.build_driver(client)
    except ClientError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    try:
        if protocol is Protocol.TORRENT:
            assert isinstance(driver, TorrentClient)
            result = await driver.add_torrent(release, options)
        else:
            assert isinstance(driver, UsenetClient)
            result = await driver.add_nzb(release, options)
    except ClientError as e:
        await driver.close()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    finally:
        await driver.close()

    return {
        "ok": result.ok,
        "identifier": result.identifier,
        "message": result.message,
    }
