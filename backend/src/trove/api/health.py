from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from trove import __version__
from trove.db import get_engine

router = APIRouter()


@router.get("/health")
async def health(response: Response) -> dict[str, str]:
    """Liveness + DB integrity check.

    Returns 200 only if the SQLite engine can actually execute a query.
    Previously this endpoint just returned a static 200 even when the
    DB file was malformed, which made every request 500 elsewhere
    while monitoring still saw "everything fine".
    """
    db_status = "ok"
    db_error: str | None = None
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1")).scalar_one()
    except Exception as e:
        db_status = "error"
        db_error = type(e).__name__ + ": " + str(e)[:200]
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    payload: dict[str, str] = {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": __version__,
        "db": db_status,
    }
    if db_error:
        payload["db_error"] = db_error
    return payload
