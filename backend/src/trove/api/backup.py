"""Backup / restore endpoints.

A Trove backup is a single zip file containing everything needed to
recreate the install on a different host:

- ``trove.db``       — SQLite database (WAL-checkpointed before export)
- ``session.secret`` — Fernet key derivative; required to decrypt the
  client / indexer / feed credentials stored in the database
- ``manifest.json``  — version + timestamp + alembic revision + file
  checksums, used during restore to validate and sanity-check

Restore is destructive — it stops the scheduler, overwrites the two
files, re-inits the DB engine, and restarts the scheduler. The caller
is responsible for confirming the intent.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from trove import __version__
from trove.api.deps import current_user, current_user_id_offline
from trove.config import get_settings
from trove.db import get_engine
from trove.models.user import User
from trove.services import scheduler as scheduler_service

router = APIRouter()

BACKUP_FILENAME_PREFIX = "trove-backup"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _checkpoint_db(db_path: Path) -> None:
    """Force-merge the WAL into the main DB so the backup captures a
    consistent point-in-time snapshot without copying -wal / -shm files.
    """
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()


def _read_alembic_version(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        if cur.fetchone() is None:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


@router.get("")
async def download_backup(
    _user: User = Depends(current_user),
) -> StreamingResponse:
    settings = get_settings()
    db_path = settings.config_dir / "trove.db"
    secret_path = settings.config_dir / "session.secret"

    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="database file missing",
        )

    # Flush any pending writes before we snapshot
    _checkpoint_db(db_path)

    alembic_rev = _read_alembic_version(db_path)

    manifest = {
        "format_version": 1,
        "trove_version": __version__,
        "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z",
        "alembic_revision": alembic_rev,
        "files": {
            "trove.db": {"sha256": _sha256(db_path), "size": db_path.stat().st_size},
        },
    }
    if secret_path.exists():
        manifest["files"]["session.secret"] = {
            "sha256": _sha256(secret_path),
            "size": secret_path.stat().st_size,
        }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, arcname="trove.db")
        if secret_path.exists():
            zf.write(secret_path, arcname="session.secret")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    buf.seek(0)

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"{BACKUP_FILENAME_PREFIX}-{timestamp}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@router.post("/restore")
async def restore_backup(
    file: UploadFile,
    _user_id: int = Depends(current_user_id_offline),
) -> dict[str, str | int | None]:
    settings = get_settings()
    db_path = settings.config_dir / "trove.db"
    secret_path = settings.config_dir / "session.secret"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty upload")

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"not a zip file: {e}"
        ) from e

    names = set(zf.namelist())
    if "manifest.json" not in names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing manifest.json")
    if "trove.db" not in names:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing trove.db")

    try:
        manifest = json.loads(zf.read("manifest.json"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid manifest: {e}"
        ) from e

    if manifest.get("format_version") != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported backup format version {manifest.get('format_version')}",
        )

    # Extract into a temp area first so a mid-extract failure doesn't
    # corrupt the live DB.
    tmp_dir = settings.config_dir / ".restore-staging"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        (tmp_dir / "trove.db").write_bytes(zf.read("trove.db"))
        if "session.secret" in names:
            (tmp_dir / "session.secret").write_bytes(zf.read("session.secret"))

        # Validate checksums against manifest
        files_manifest = manifest.get("files") or {}
        for fname, meta in files_manifest.items():
            staged = tmp_dir / fname
            if not staged.exists():
                continue
            expected = meta.get("sha256")
            if expected and _sha256(staged) != expected:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"checksum mismatch for {fname}",
                )

        # Stop the scheduler so nothing writes to the DB while we swap
        scheduler_service.stop_scheduler()

        # Dispose the SQLAlchemy engine so it releases file handles
        get_engine().dispose()

        # Back up the current files in case the new ones are bad
        safety_dir = settings.config_dir / ".pre-restore"
        safety_dir.mkdir(exist_ok=True)
        if db_path.exists():
            db_path.replace(safety_dir / f"trove.db.{int(datetime.now(UTC).timestamp())}")
        if secret_path.exists():
            secret_path.replace(safety_dir / f"session.secret.{int(datetime.now(UTC).timestamp())}")

        # Swap staged files into place
        (tmp_dir / "trove.db").replace(db_path)
        staged_secret = tmp_dir / "session.secret"
        if staged_secret.exists():
            staged_secret.replace(secret_path)
            with contextlib.suppress(OSError):
                secret_path.chmod(0o600)

        # Fresh engine picks up the new DB file
        import trove.db as db_module

        db_module._engine = None

        # Restart the scheduler so feeds and tasks get re-loaded
        scheduler_service.start_scheduler()
    finally:
        # Best-effort cleanup of the staging dir
        for leftover in tmp_dir.glob("*"):
            with contextlib.suppress(OSError):
                leftover.unlink()
        with contextlib.suppress(OSError):
            tmp_dir.rmdir()

    return {
        "ok": True,
        "restored_version": manifest.get("trove_version"),
        "restored_alembic": manifest.get("alembic_revision"),
        "backup_created_at": manifest.get("created_at"),
    }
