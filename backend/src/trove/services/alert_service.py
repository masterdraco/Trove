"""Saved browse-alert runner.

For each enabled SavedAlertRow we periodically re-run the browse
fan-out for its category, filter by the alert's keywords, diff the
current titles against the last-seen set, and dispatch one
``alert.new_match`` notification per newly-appearing release.

Scheduler drives this from ``scheduler.py`` on a 5-minute tick —
alerts with a longer ``check_interval_minutes`` are simply skipped
until their next due time.

Failures per alert are isolated: one broken indexer or one busted
alert row never blocks the rest of the sweep.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import structlog
from sqlmodel import Session, select

from trove.clients.base import Protocol
from trove.db import get_engine
from trove.indexers.base import Category
from trove.models.saved_alert import SavedAlertRow
from trove.services import notification_service, search_service

log = structlog.get_logger()


def _split_keywords(raw: str) -> list[str]:
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    low = title.lower()
    return any(k in low for k in keywords)


def _load_seen(row: SavedAlertRow) -> set[str]:
    try:
        data = json.loads(row.last_seen_titles or "[]")
        if isinstance(data, list):
            return {str(t) for t in data}
    except ValueError:
        pass
    return set()


def _save_seen(row: SavedAlertRow, titles: set[str]) -> None:
    # Cap at 200 — enough for diffing across a day even on busy trackers.
    capped = list(titles)[:200]
    row.last_seen_titles = json.dumps(capped)


async def check_alert(session: Session, alert: SavedAlertRow) -> int:
    """Run one alert; return the number of new matches dispatched."""
    try:
        category = Category(alert.category)
    except ValueError:
        log.warning("alert.unknown_category", alert_id=alert.id, category=alert.category)
        return 0

    protocol: Protocol | None = None
    if alert.protocol:
        try:
            protocol = Protocol(alert.protocol)
        except ValueError:
            protocol = None

    try:
        result = await search_service.run_browse(
            session,
            category=category,
            protocol=protocol,
            limit=100,
        )
    except Exception as e:  # pragma: no cover
        log.warning("alert.browse_failed", alert_id=alert.id, error=str(e))
        return 0

    keywords = _split_keywords(alert.keywords)
    matching = [h for h in result.hits if _matches_keywords(h.title, keywords)]
    current_titles = {h.title for h in matching}

    seen = _load_seen(alert)
    new_titles = current_titles - seen

    dispatched = 0
    for hit in matching:
        if hit.title not in new_titles:
            continue
        fields = {
            "Alert": alert.name,
            "Category": alert.category,
            "Source": hit.source or "?",
        }
        if hit.size:
            fields["Size"] = f"{hit.size / (1024**3):.1f} GB"
        if hit.group:
            fields["Group"] = hit.group
        event = notification_service.Event(
            kind="alert.new_match",
            title=f"New match: {hit.title[:120]}",
            description=f'Alert "{alert.name}" matched a new release.',
            fields=fields,
            link=hit.download_url,
        )
        try:
            await notification_service.dispatch(session, event)
            dispatched += 1
        except Exception as e:  # pragma: no cover
            log.warning("alert.dispatch_failed", alert_id=alert.id, error=str(e))

    _save_seen(alert, current_titles)
    alert.last_check_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(alert)
    try:
        session.commit()
    except Exception as e:  # pragma: no cover
        log.warning("alert.commit_failed", alert_id=alert.id, error=str(e))
        session.rollback()

    return dispatched


async def sweep_due_alerts() -> dict[str, int]:
    """Run every enabled alert whose check interval has elapsed.

    Called by the scheduler on a fixed tick (5 min). Alerts with
    longer intervals are skipped on ticks where ``last_check_at +
    interval > now``.
    """
    stats = {"checked": 0, "new_matches": 0, "errors": 0}
    engine = get_engine()
    now = datetime.now(UTC).replace(tzinfo=None)

    with Session(engine) as session:
        rows = session.exec(
            select(SavedAlertRow).where(SavedAlertRow.enabled == True)  # noqa: E712
        ).all()
        for row in rows:
            due = row.last_check_at is None or (
                row.last_check_at + timedelta(minutes=row.check_interval_minutes) <= now
            )
            if not due:
                continue
            stats["checked"] += 1
            try:
                stats["new_matches"] += await check_alert(session, row)
            except Exception as e:
                log.warning("alert.sweep.unexpected", alert_id=row.id, error=str(e))
                stats["errors"] += 1
    return stats
