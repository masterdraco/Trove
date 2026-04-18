"""Periodic download state polling.

Walks recent ``seen_release`` rows that have an identifier assigned
(i.e. we actually handed the release to a client) and haven't
reached a terminal state yet, calls ``client.get_state()`` on each,
and writes the result back to the row. State transitions
(``queued -> downloading -> completed`` / ``failed``) are dispatched
to the notification system — but that plumbing is added in a later
commit; for now we only persist the latest state.

Ran by APScheduler every 60 seconds via ``start_poller`` in the
main scheduler. Cheap: the default 48h lookback + terminal-state
short-circuit means a long-running install never polls more than a
handful of rows per tick.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlmodel import Session, select

from trove.clients.base import DownloadState, DownloadStatus
from trove.db import get_engine
from trove.models.client import Client
from trove.models.task import SeenReleaseRow
from trove.services import client_registry, notification_service, watchlist_completion

log = structlog.get_logger()

# States we stop polling from — they're final.
TERMINAL_STATES = {
    DownloadStatus.COMPLETED.value,
    DownloadStatus.FAILED.value,
    DownloadStatus.NOT_FOUND.value,
}

# Only poll rows grabbed within this window. Older rows are assumed
# done-for-good even if we never saw the transition.
POLL_WINDOW = timedelta(hours=48)


def _format_size(size: int | None) -> str:
    if not size or size <= 0:
        return "?"
    size_f = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_f < 1024:
            return f"{size_f:.1f}{unit}" if unit != "B" else f"{int(size_f)}B"
        size_f /= 1024
    return f"{size_f:.1f}PB"


async def _dispatch_transition(
    session: Session,
    row: SeenReleaseRow,
    prior: str | None,
    state: DownloadState,
) -> None:
    """Fire a notification event for a meaningful state change.

    Only dispatch on the "interesting" transitions — queued→downloading,
    →completed, →failed, →removed. We don't spam on verifying or
    pause transitions; those would be too chatty.
    """
    new_status = state.status.value
    # Intermediate noise — skip.
    if new_status in ("queued", "paused", "verifying", "unknown"):
        return
    if new_status == prior:
        return
    size_label = _format_size(state.size_bytes)
    fields = {
        "Task id": str(row.task_id),
        "Title": (state.display_title or row.title)[:120],
        "Size": size_label,
    }
    if new_status == "downloading":
        event = notification_service.Event(
            kind="download.started",
            title=f"Downloading: {row.title[:120]}",
            description=f"{state.display_title or row.title}",
            fields=fields,
        )
    elif new_status == "completed":
        event = notification_service.Event(
            kind="download.completed",
            title=f"Completed: {row.title[:120]}",
            description=f"{state.display_title or row.title}",
            fields=fields,
        )
    elif new_status == "failed":
        err_fields = dict(fields)
        if state.error_message:
            err_fields["Error"] = state.error_message[:200]
        event = notification_service.Event(
            kind="download.failed",
            title=f"Failed: {row.title[:120]}",
            description=f"{state.display_title or row.title}",
            fields=err_fields,
        )
    elif new_status == "not_found":
        event = notification_service.Event(
            kind="download.removed",
            title=f"Removed from client: {row.title[:120]}",
            description="Trove will re-grab this release on the next task run.",
            fields=fields,
        )
    else:
        return
    await notification_service.dispatch(session, event)

    # Terminal success → update any linked watchlist item. We do this
    # after dispatch so notification failures never block state updates.
    if new_status == "completed":
        try:
            watchlist_completion.handle_download_completed(session, row.task_id)
        except Exception as e:  # pragma: no cover - defensive
            log.warning("watchlist_completion.failed", error=str(e), task_id=row.task_id)


async def poll_once() -> dict[str, int]:
    """One sweep across all pollable rows. Returns a summary dict."""
    stats = {
        "polled": 0,
        "updated": 0,
        "transitioned": 0,
        "not_found": 0,
        "errors": 0,
    }
    engine = get_engine()
    with Session(engine) as session:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - POLL_WINDOW
        rows = session.exec(
            select(SeenReleaseRow)
            .where(SeenReleaseRow.outcome == "sent")
            .where(SeenReleaseRow.grabbed_identifier.is_not(None))  # type: ignore[attr-defined]
            .where(SeenReleaseRow.seen_at >= cutoff)
        ).all()

        # Cache driver instances by client_id so we don't rebuild one
        # driver per row (each build opens an httpx client).
        drivers: dict[int, object] = {}
        try:
            for row in rows:
                # Skip rows already in a terminal state.
                if row.download_status in TERMINAL_STATES:
                    continue
                if row.client_id is None or row.grabbed_identifier is None:
                    continue

                driver = drivers.get(row.client_id)
                if driver is None:
                    client_row = session.get(Client, row.client_id)
                    if client_row is None or not client_row.enabled:
                        continue
                    try:
                        driver = client_registry.build_driver(client_row)
                    except Exception as e:  # pragma: no cover - defensive
                        log.warning(
                            "download_poller.build_driver.failed",
                            client=client_row.name if client_row else row.client_id,
                            error=str(e),
                        )
                        stats["errors"] += 1
                        continue
                    drivers[row.client_id] = driver

                stats["polled"] += 1
                try:
                    state: DownloadState = await driver.get_state(  # type: ignore[attr-defined]
                        row.grabbed_identifier
                    )
                except Exception as e:  # pragma: no cover
                    log.warning(
                        "download_poller.get_state.failed",
                        identifier=row.grabbed_identifier,
                        error=str(e),
                    )
                    stats["errors"] += 1
                    continue

                prior = row.download_status
                row.download_status = state.status.value
                row.download_progress = state.progress
                row.download_size_bytes = state.size_bytes
                row.download_downloaded_bytes = state.downloaded_bytes
                row.download_eta_seconds = state.eta_seconds
                row.download_error_message = state.error_message
                row.download_state_at = datetime.now(UTC).replace(tzinfo=None)

                if state.status is DownloadStatus.NOT_FOUND:
                    # The download disappeared from the client —
                    # typically because the user removed it manually.
                    # Flip the row to outcome=removed so the task can
                    # re-grab on the next run if it still wants to.
                    row.outcome = "removed"
                    stats["not_found"] += 1

                if prior != row.download_status:
                    stats["transitioned"] += 1
                    await _dispatch_transition(session, row, prior, state)
                stats["updated"] += 1
                session.add(row)

            session.commit()
        finally:
            # Close every driver we opened so we don't leak httpx clients.
            for drv in drivers.values():
                try:
                    close_fn = getattr(drv, "close", None)
                    if close_fn is not None:
                        res = close_fn()
                        # close() can be sync or async depending on the
                        # driver — await if coroutine.
                        import inspect

                        if inspect.isawaitable(res):
                            await res
                except Exception:  # pragma: no cover
                    pass
    return stats
