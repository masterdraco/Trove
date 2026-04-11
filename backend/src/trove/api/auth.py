from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from trove.api.deps import current_user, db_session
from trove.config import get_settings
from trove.models.user import User
from trove.services import auth_service

router = APIRouter()


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str


class SetupStatus(BaseModel):
    needs_setup: bool


def _set_session_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    token = auth_service.issue_session_token(user_id)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=False,  # reverse proxies handle TLS termination
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/status", response_model=SetupStatus)
async def status_endpoint(session: Session = Depends(db_session)) -> SetupStatus:
    return SetupStatus(needs_setup=not auth_service.user_exists(session))


@router.post("/setup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def setup_endpoint(
    payload: SetupRequest,
    response: Response,
    session: Session = Depends(db_session),
) -> UserOut:
    if auth_service.user_exists(session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="setup_already_completed",
        )
    user = auth_service.create_user(session, payload.username, payload.password)
    assert user.id is not None
    _set_session_cookie(response, user.id)
    return UserOut(id=user.id, username=user.username)


@router.post("/login", response_model=UserOut)
async def login_endpoint(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(db_session),
) -> UserOut:
    user = auth_service.get_user_by_username(session, payload.username)
    if user is None or not auth_service.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        )
    auth_service.touch_last_login(session, user)
    assert user.id is not None
    _set_session_cookie(response, user.id)
    return UserOut(id=user.id, username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(response: Response) -> Response:
    _clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me_endpoint(user: User = Depends(current_user)) -> UserOut:
    assert user.id is not None
    return UserOut(id=user.id, username=user.username)
