"""Calendar API — month-grid view of upcoming + recent watchlist events.

For each watchlist item, fetches air dates from TMDB (series:
next_episode_to_air + last_episode_to_air; movies: release_date from
the cached row) and cross-references against seen_release to determine
grab state.
"""

from __future__ import annotations

import contextlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.api.deps import current_user, db_session
from trove.models.task import SeenReleaseRow
from trove.models.user import User
from trove.models.watchlist import WatchlistItemRow
from trove.services import tmdb

router = APIRouter()


class CalendarEvent(BaseModel):
    date: str
    title: str
    kind: str  # movie | tv
    tmdb_id: int | None = None
    season: int | None = None
    episode: int | None = None
    episode_title: str | None = None
    poster_url: str | None = None
    grab_state: str = "pending"  # pending | grabbed | missed


class CalendarResponse(BaseModel):
    month: str  # YYYY-MM
    events: list[CalendarEvent] = Field(default_factory=list)


@router.get("", response_model=CalendarResponse)
async def get_calendar(
    month: str | None = None,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> CalendarResponse:
    now = datetime.utcnow()
    target_month = month if month and len(month) == 7 else now.strftime("%Y-%m")

    try:
        target_year = int(target_month[:4])
        target_mon = int(target_month[5:7])
    except (ValueError, IndexError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid month format: {month} (expected YYYY-MM)",
        ) from e

    items = session.exec(select(WatchlistItemRow)).all()
    if not items:
        return CalendarResponse(month=target_month, events=[])

    # Collect all seen_release keys so we can check grab state cheaply.
    seen_keys: set[str] = set()
    sent_rows = session.exec(select(SeenReleaseRow).where(SeenReleaseRow.outcome == "sent")).all()
    for r in sent_rows:
        seen_keys.add(r.key)

    events: list[CalendarEvent] = []

    for item in items:
        if item.kind == "movie":
            _collect_movie_events(item, target_year, target_mon, seen_keys, events)
        elif item.kind == "series" and item.tmdb_id and item.tmdb_type == "tv":
            await _collect_series_events(item, target_year, target_mon, seen_keys, events)

    events.sort(key=lambda e: e.date)
    return CalendarResponse(month=target_month, events=events)


def _in_month(date_str: str | None, year: int, month: int) -> bool:
    if not date_str or len(date_str) < 7:
        return False
    try:
        return int(date_str[:4]) == year and int(date_str[5:7]) == month
    except (ValueError, IndexError):
        return False


def _grab_state(key: str, seen_keys: set[str], date_str: str) -> str:
    if key in seen_keys:
        return "grabbed"
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        if d < datetime.utcnow():
            return "missed"
    except ValueError:
        pass
    return "pending"


def _collect_movie_events(
    item: WatchlistItemRow,
    year: int,
    month: int,
    seen_keys: set[str],
    events: list[CalendarEvent],
) -> None:
    rd = item.release_date
    if not _in_month(rd, year, month):
        return
    from trove.parsing.title import normalized_movie_name

    key = f"m:{normalized_movie_name(item.title)}:{item.year or ''}"
    events.append(
        CalendarEvent(
            date=str(rd),
            title=item.title,
            kind="movie",
            tmdb_id=item.tmdb_id,
            poster_url=item.poster_path,
            grab_state=_grab_state(key, seen_keys, str(rd)),
        )
    )


async def _collect_series_events(
    item: WatchlistItemRow,
    year: int,
    month: int,
    seen_keys: set[str],
    events: list[CalendarEvent],
) -> None:
    """Fetch next/last episode from TMDB and add if they fall in the month."""
    try:
        data = await tmdb._request(f"/tv/{item.tmdb_id}")
    except tmdb.TmdbError:
        return

    import re

    show_norm = re.sub(r"[^a-z0-9]+", "", item.title.lower())

    for ep_key in ("next_episode_to_air", "last_episode_to_air"):
        ep = data.get(ep_key)
        if not isinstance(ep, dict):
            continue
        air_date = ep.get("air_date")
        if not _in_month(air_date, year, month):
            continue
        s = int(ep.get("season_number") or 0)
        e = int(ep.get("episode_number") or 0)
        dedup_key = f"e:{show_norm}:s{s:02d}e{e:02d}"
        events.append(
            CalendarEvent(
                date=str(air_date),
                title=item.title,
                kind="tv",
                tmdb_id=item.tmdb_id,
                season=s,
                episode=e,
                episode_title=ep.get("name"),
                poster_url=item.poster_path,
                grab_state=_grab_state(dedup_key, seen_keys, str(air_date)),
            )
        )

    # Also check the current season's episodes — TMDB returns all
    # with air dates if the season is airing. Cap at season+1.
    seasons_data = data.get("seasons") or []
    current_season: int | None = None
    with contextlib.suppress(Exception):
        nea = data.get("next_episode_to_air") or data.get("last_episode_to_air")
        if isinstance(nea, dict):
            current_season = int(nea.get("season_number") or 0)
    if current_season is None and seasons_data:
        current_season = max(
            (int(s.get("season_number") or 0) for s in seasons_data if isinstance(s, dict)),
            default=None,
        )
    if current_season is None:
        return

    for sn in (current_season, current_season + 1):
        try:
            season_data = await tmdb._request(f"/tv/{item.tmdb_id}/season/{sn}")
        except tmdb.TmdbError:
            continue
        for ep in season_data.get("episodes") or []:
            air_date = ep.get("air_date")
            if not _in_month(air_date, year, month):
                continue
            s = int(ep.get("season_number") or sn)
            e = int(ep.get("episode_number") or 0)
            dedup_key = f"e:{show_norm}:s{s:02d}e{e:02d}"
            # Avoid duplicates from the next/last episode we added above.
            if any(
                ev.tmdb_id == item.tmdb_id and ev.season == s and ev.episode == e for ev in events
            ):
                continue
            events.append(
                CalendarEvent(
                    date=str(air_date),
                    title=item.title,
                    kind="tv",
                    tmdb_id=item.tmdb_id,
                    season=s,
                    episode=e,
                    episode_title=ep.get("name"),
                    poster_url=item.poster_path,
                    grab_state=_grab_state(dedup_key, seen_keys, str(air_date)),
                )
            )
