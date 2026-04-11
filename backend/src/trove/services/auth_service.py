from __future__ import annotations

from datetime import UTC, datetime

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext
from sqlmodel import Session, select

from trove.config import get_settings
from trove.models.user import User

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


def user_exists(session: Session) -> bool:
    stmt = select(User).limit(1)
    return session.exec(stmt).first() is not None


def get_user_by_username(session: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return session.exec(stmt).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def create_user(session: Session, username: str, password: str) -> User:
    user = User(username=username, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def touch_last_login(session: Session, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    session.add(user)
    session.commit()


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().session_secret)


def issue_session_token(user_id: int) -> str:
    return _signer().sign(str(user_id).encode("utf-8")).decode("utf-8")


def read_session_token(token: str) -> int | None:
    settings = get_settings()
    try:
        raw = _signer().unsign(token, max_age=settings.session_max_age_seconds)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    try:
        return int(raw.decode("utf-8"))
    except ValueError:
        return None
