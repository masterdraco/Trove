"""Auto-complete watchlist items when a download finishes.

Called by :mod:`download_poller` the moment it observes a
queued→completed transition. We look up the WatchlistItemRow linked
to the task (via ``discovery_task_id``) and update its state:

  discovery_status → "downloaded"   always, once the first successful
                                    download is observed.
  status           → "done"         only for movies that hit the target
                                    quality tier. Series stay active so
                                    new episodes keep getting grabbed.
  task.enabled     → False          same condition as above — the task
                                    has nothing more to do once quality
                                    target is met for a movie.

Series are intentionally left alone beyond the discovery_status flip,
since a single completed episode doesn't mean the whole show is done.
The user marks series as ``status="done"`` by hand when they've had
enough.
"""

from __future__ import annotations

import structlog
from sqlmodel import Session, select

from trove.models.task import SeenReleaseRow, TaskRow
from trove.models.watchlist import WatchlistItemRow

log = structlog.get_logger()

# Mirrors task_engine._QUALITY_TIERS. If you add new tags there,
# mirror them here or refactor into a shared module.
_QUALITY_TIERS: dict[str, int] = {
    "2160p": 4,
    "4k": 4,
    "uhd": 4,
    "1080p": 3,
    "720p": 2,
    "576p": 1,
    "480p": 1,
    "sd": 1,
}


def _parse_quality_tier(text: str | None) -> int | None:
    if not text:
        return None
    lower = text.lower()
    for tag, tier in _QUALITY_TIERS.items():
        if tag in lower:
            return tier
    return None


def handle_download_completed(session: Session, task_id: int) -> None:
    """Update watchlist + task state for a completed download.

    Silent no-op when the task isn't linked to a watchlist item or
    when no completed SeenReleaseRow can be found for it. Commits on
    success; rolls back on DB error so we don't poison the caller's
    session.
    """
    item = session.exec(
        select(WatchlistItemRow).where(WatchlistItemRow.discovery_task_id == task_id)
    ).first()
    if item is None:
        return

    completed = session.exec(
        select(SeenReleaseRow)
        .where(
            SeenReleaseRow.task_id == task_id,
            SeenReleaseRow.download_status == "completed",
        )
        .order_by(SeenReleaseRow.id.desc())  # type: ignore[attr-defined]
    ).first()
    if completed is None:
        return

    target_tier = _parse_quality_tier(item.target_quality)
    current_tier = completed.quality_tier
    meets_target = target_tier is None or (current_tier is not None and current_tier >= target_tier)

    changed = False
    if item.discovery_status != "downloaded":
        item.discovery_status = "downloaded"
        session.add(item)
        changed = True

    if meets_target and item.kind == "movie":
        if item.status != "done":
            item.status = "done"
            session.add(item)
            changed = True
        task = session.get(TaskRow, task_id)
        if task is not None and task.enabled:
            task.enabled = False
            session.add(task)
            changed = True

    if not changed:
        return

    try:
        session.commit()
        log.info(
            "watchlist.auto_completed",
            watchlist_id=item.id,
            task_id=task_id,
            kind=item.kind,
            meets_target=meets_target,
            current_tier=current_tier,
            target_tier=target_tier,
        )
    except Exception as e:  # pragma: no cover - defensive
        log.warning("watchlist.auto_complete.commit_failed", error=str(e))
        session.rollback()
