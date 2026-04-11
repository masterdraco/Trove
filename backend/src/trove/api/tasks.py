from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.task import SeenReleaseRow, TaskRow, TaskRunRow
from trove.models.user import User
from trove.services import scheduler, task_engine

router = APIRouter()


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    schedule_cron: str | None = None
    config_yaml: str = ""


class TaskUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    schedule_cron: str | None = None
    config_yaml: str | None = None


class TaskOut(BaseModel):
    id: int
    name: str
    enabled: bool
    schedule_cron: str | None
    config_yaml: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_accepted: int | None
    last_run_considered: int | None


class TaskRunOut(BaseModel):
    id: int
    task_id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    considered: int
    accepted: int
    dry_run: bool
    log: str


def _to_out(row: TaskRow) -> TaskOut:
    assert row.id is not None
    return TaskOut(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        schedule_cron=row.schedule_cron,
        config_yaml=row.config_yaml,
        last_run_at=row.last_run_at,
        last_run_status=row.last_run_status,
        last_run_accepted=row.last_run_accepted,
        last_run_considered=row.last_run_considered,
    )


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[TaskOut]:
    rows = session.exec(select(TaskRow).order_by(TaskRow.name)).all()
    return [_to_out(r) for r in rows]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> TaskOut:
    existing = session.exec(select(TaskRow).where(TaskRow.name == payload.name)).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="name_taken")
    row = TaskRow(
        name=payload.name,
        enabled=payload.enabled,
        schedule_cron=payload.schedule_cron,
        config_yaml=payload.config_yaml,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    scheduler.schedule_task(row)
    # Fire once immediately so the first run happens without waiting for
    # the cron interval. The one-shot runs 3s later to let the response
    # return first.
    if payload.enabled and row.id is not None:
        scheduler.schedule_run_now(row.id)
    return _to_out(row)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> TaskOut:
    row = session.get(TaskRow, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if payload.name is not None:
        row.name = payload.name
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.schedule_cron is not None:
        row.schedule_cron = payload.schedule_cron or None
    if payload.config_yaml is not None:
        row.config_yaml = payload.config_yaml
    row.updated_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    session.refresh(row)
    scheduler.schedule_task(row)
    return _to_out(row)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> None:
    row = session.get(TaskRow, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    scheduler.unschedule_task(task_id)
    # Cascade manually — task_run / seen_release have FKs to task with no
    # ON DELETE CASCADE, and SQLite has FK enforcement enabled. Use bulk
    # execute() instead of session.delete(child) so the child DELETEs hit
    # the DB *immediately*, before the parent's DELETE is queued. The
    # session-based variant let SQLAlchemy reorder the unit-of-work flush
    # and the parent DELETE went out first → FK violation.
    session.execute(sql_delete(SeenReleaseRow).where(SeenReleaseRow.task_id == task_id))
    session.execute(sql_delete(TaskRunRow).where(TaskRunRow.task_id == task_id))
    session.delete(row)
    session.commit()


@router.post("/{task_id}/run", response_model=TaskRunOut)
async def run_task_endpoint(
    task_id: int,
    dry_run: bool = False,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> TaskRunOut:
    row = session.get(TaskRow, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    run = await task_engine.run_task(session, row, dry_run=dry_run)
    return TaskRunOut(
        id=run.id or 0,
        task_id=run.task_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        considered=run.considered,
        accepted=run.accepted,
        dry_run=run.dry_run,
        log=run.log,
    )


@router.get("/{task_id}/runs", response_model=list[TaskRunOut])
async def list_runs(
    task_id: int,
    limit: int = 25,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[TaskRunOut]:
    rows = session.exec(
        select(TaskRunRow)
        .where(TaskRunRow.task_id == task_id)
        .order_by(TaskRunRow.started_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    return [
        TaskRunOut(
            id=r.id or 0,
            task_id=r.task_id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            status=r.status,
            considered=r.considered,
            accepted=r.accepted,
            dry_run=r.dry_run,
            log=r.log,
        )
        for r in rows
    ]
