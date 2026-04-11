"""Live log viewer: history endpoint + WebSocket stream."""

from __future__ import annotations

from typing import Any

import anyio
import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlmodel import Session
from starlette.websockets import WebSocketState

from trove.api.deps import current_user, db_session
from trove.config import get_settings
from trove.log_buffer import log_buffer
from trove.models.user import User
from trove.services import auth_service

log = structlog.get_logger()

router = APIRouter()


@router.get("/history")
async def logs_history(
    limit: int = 500,
    _user: User = Depends(current_user),
) -> dict[str, list[dict[str, Any]]]:
    """Return up to `limit` most recent entries from the ring buffer."""
    entries = log_buffer.history()
    if limit > 0:
        entries = entries[-limit:]
    return {"entries": entries}


@router.websocket("/ws")
async def logs_ws(websocket: WebSocket, session: Session = Depends(db_session)) -> None:
    """Stream log entries over a WebSocket.

    Auth: reads the session cookie from the handshake and validates it
    the same way ``current_user`` does. Rejects with 1008 if invalid.
    """
    cookie_name = get_settings().session_cookie_name
    token = websocket.cookies.get(cookie_name)
    user_id = auth_service.read_session_token(token) if token else None
    user = auth_service.get_user_by_id(session, user_id) if user_id else None
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    send, receive = log_buffer.subscribe()
    try:
        for entry in log_buffer.history():
            await websocket.send_json(entry)
        async with receive:
            async for entry in receive:
                if websocket.client_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_json(entry)
    except WebSocketDisconnect:
        pass
    except anyio.get_cancelled_exc_class():
        raise
    except Exception as e:  # pragma: no cover
        log.warning("logs.ws.error", error=str(e))
    finally:
        log_buffer.unsubscribe(send)
