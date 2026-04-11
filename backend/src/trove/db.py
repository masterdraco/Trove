from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from trove.config import get_settings


@event.listens_for(Engine, "connect")
def _enable_sqlite_wal(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Default busy_timeout is 0, so any concurrent writer (e.g. the
        # scheduler running a task while the API tries to delete one)
        # gets an immediate "database is locked" error. Wait up to 5s.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
    except Exception:
        pass


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolved_database_url
        connect_args: dict[str, object] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, echo=False, connect_args=connect_args)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
