from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from trove.config import get_settings
from trove.db import get_session as _db_session
from trove.models.user import User
from trove.services import auth_service


def db_session() -> Generator[Session, None, None]:
    yield from _db_session()


def _session_token_from_request(request: Request) -> str | None:
    cookie_name = get_settings().session_cookie_name
    return request.cookies.get(cookie_name)


def current_user(
    request: Request,
    session: Session = Depends(db_session),
) -> User:
    token = _session_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")
    user_id = auth_service.read_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_session")
    user = auth_service.get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found")
    return user
