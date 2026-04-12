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
from typing import TYPE_CHECKING

import structlog
from sqlmodel import Session, select

from trove.clients.base import DownloadStatus
from trove.db import get_engine
from trove.models.client import Client
from trove.models.task import SeenReleaseRow
from trove.services import client_registry

if TYPE_CHECKING:
    from trove.clients.base import DownloadState

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
