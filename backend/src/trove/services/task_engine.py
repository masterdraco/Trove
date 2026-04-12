from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
import yaml
from sqlmodel import Session, select

from trove.clients.base import (
    AddOptions,
    ClientError,
    ClientType,
    DownloadClient,
    Protocol,
    Release,
    TorrentClient,
    UsenetClient,
)
from trove.indexers.base import Category
from trove.models.client import Client
from trove.models.feed import FeedRow, RssItemRow
from trove.models.indexer import IndexerRow
from trove.models.task import SeenReleaseRow, TaskRow, TaskRunRow
from trove.parsing.title import (
    extract_episode,
    extract_year,
    looks_like_series,
    normalized_movie_name,
    normalized_show_prefix,
)
from trove.services import (
    client_registry,
    notification_service,
    quality_profile,
    search_service,
)
from trove.utils.crypto import decrypt_json

log = structlog.get_logger()


def _format_size(size: int | None) -> str:
    if not size or size <= 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}{unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f}PB"  # type: ignore[str-format]


def parse_task_config(config_yaml: str) -> dict[str, Any]:
    if not config_yaml.strip():
        return {"inputs": [], "filters": {}, "outputs": []}
    data = yaml.safe_load(config_yaml)
    if not isinstance(data, dict):
        raise ValueError("task config must be a YAML mapping")
    return data


# Legacy hardcoded fallbacks — kept in sync with the built-in default
# profile in services/quality_profile.py. Used when score_hit is called
# without a profile (e.g. from tests or old call sites).
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
_SOURCE_TIERS: dict[str, int] = {
    "remux": 6,
    "bluray": 5,
    "blu-ray": 5,
    "bdrip": 4,
    "web-dl": 4,
    "webdl": 4,
    "webrip": 3,
    "hdtv": 2,
    "dvdrip": 1,
    "hdts": -5,
    "telesync": -5,
    "cam": -10,
}
_CODEC_BONUS: dict[str, int] = {
    "x265": 2,
    "h265": 2,
    "h.265": 2,
    "hevc": 2,
    "x264": 1,
    "h264": 1,
}


def _match_tier(title_lower: str, table: dict[str, int]) -> int:
    best = 0
    for key, value in table.items():
        if key in title_lower and (value > best or best == 0):
            best = value
    return best


def score_hit(
    hit: search_service.SearchHit,
    *,
    prefer_quality: str | None = None,
    max_size_mb: int | None = None,
    profile: dict[str, Any] | None = None,
) -> float:
    """Rank a search hit. Higher is better. Used to sort candidates so
    the task engine picks the best one that also passes the hard filters.

    When ``profile`` is given, its quality/source/codec tables and
    prefer_quality override the hardcoded defaults. Otherwise the
    historical hardcoded weights are used, so existing tests and old
    tasks keep ranking the same way.
    """
    title = hit.title.lower()
    score = 0.0

    if profile:
        quality_tiers = {k: int(v) for k, v in (profile.get("quality_tiers") or {}).items()}
        source_tiers = {k: int(v) for k, v in (profile.get("source_tiers") or {}).items()}
        codec_bonus = {k: int(v) for k, v in (profile.get("codec_bonus") or {}).items()}
        effective_prefer = profile.get("prefer_quality") or prefer_quality
    else:
        quality_tiers = _QUALITY_TIERS
        source_tiers = _SOURCE_TIERS
        codec_bonus = _CODEC_BONUS
        effective_prefer = prefer_quality

    # Quality tier (2160 > 1080 > 720 …)
    score += _match_tier(title, quality_tiers) * 100

    # Preferred quality gets a soft bonus so it wins when available, but
    # does NOT disqualify lower qualities if nothing else matches.
    if effective_prefer and str(effective_prefer).lower() in title:
        score += 500

    # Source — BluRay/Remux > WEB-DL > HDTV > DVD > CAM/TS
    score += _match_tier(title, source_tiers) * 30

    # Codec — x265/HEVC preferred
    best_codec = 0
    for codec, bonus in codec_bonus.items():
        if codec in title:
            best_codec = max(best_codec, bonus)
    score += best_codec * 10

    # Size — slight bonus for bigger (proxy for quality) but only up to
    # max_size_mb. Hard filter handles the over-size case.
    if hit.size and max_size_mb and max_size_mb > 0:
        size_mb = hit.size / (1024 * 1024)
        ratio = min(size_mb / max_size_mb, 1.0)
        score += ratio * 20

    # Health — seeders for torrents, published recency isn't worth much
    if hit.protocol is Protocol.TORRENT and hit.seeders:
        score += math.log1p(hit.seeders) * 5

    return score


def compute_quality_tier(
    hit: search_service.SearchHit,
    profile: dict[str, Any] | None = None,
) -> int:
    """Return the integer quality tier for a release title.

    Uses the profile's quality_tiers table when available, otherwise
    the hardcoded defaults. The tier value is what gets stored in
    ``seen_release.quality_tier`` and compared against the task's
    ``upgrade_until_tier`` cutoff.
    """
    title = hit.title.lower()
    table = (
        {k: int(v) for k, v in (profile.get("quality_tiers") or {}).items()}
        if profile
        else _QUALITY_TIERS
    )
    return _match_tier(title, table)


def _seen_key(release: search_service.SearchHit) -> str:
    """Dedup key — same episode/movie across different qualities maps to
    the same key so a task never grabs "S01E01 1080p" and "S01E01 2160p"
    as two separate downloads.
    """
    ep = extract_episode(release.title)
    if ep is not None:
        show = normalized_show_prefix(release.title)
        return f"e:{show}:s{ep[0]:02d}e{ep[1]:02d}"
    year = extract_year(release.title)
    if year is not None:
        name = normalized_movie_name(release.title)
        return f"m:{name}:{year}"
    if release.infohash:
        return f"h:{release.infohash.lower()}"
    return f"t:{release.title.lower()}"


def _read_rss_items(
    session: Any,
    feed_names: list[str] | None = None,
    protocol: Protocol | None = None,
    limit: int = 500,
) -> list[search_service.SearchHit]:
    """Load all cached RSS items as SearchHits. Used by rss_items task inputs."""
    from sqlmodel import select  # local import to keep the module cycle-free

    stmt = select(RssItemRow, FeedRow).where(RssItemRow.feed_id == FeedRow.id)
    if protocol is not None:
        stmt = stmt.where(FeedRow.protocol_hint == protocol.value)
    if feed_names:
        stmt = stmt.where(FeedRow.name.in_(feed_names))  # type: ignore[attr-defined]
    stmt = stmt.order_by(RssItemRow.fetched_at.desc()).limit(limit)  # type: ignore[attr-defined]

    hits: list[search_service.SearchHit] = []
    for item, feed in session.exec(stmt).all():
        try:
            hit_protocol = Protocol(feed.protocol_hint)
        except ValueError:
            hit_protocol = Protocol.TORRENT
        hits.append(
            search_service.SearchHit(
                title=item.title,
                protocol=hit_protocol,
                size=item.size,
                seeders=item.seeders,
                leechers=item.leechers,
                download_url=item.download_url,
                infohash=item.infohash,
                category=item.category,
                source=f"rss:{feed.name}",
                score=0.0,
                published_at=item.published_at.isoformat() if item.published_at else None,
            )
        )
    return hits


def _pass_filter(hit: search_service.SearchHit, filters: dict[str, Any]) -> tuple[bool, str]:
    # Seeder filter only applies to torrents — NZB releases have no seeders
    # and would be dropped unconditionally if treated as zero.
    min_seeders = filters.get("min_seeders")
    if (
        isinstance(min_seeders, int)
        and hit.protocol is Protocol.TORRENT
        and (hit.seeders or 0) < min_seeders
    ):
        return False, f"seeders<{min_seeders}"

    max_size_mb = filters.get("max_size_mb")
    if (
        isinstance(max_size_mb, int)
        and hit.size is not None
        and hit.size > max_size_mb * 1024 * 1024
    ):
        return False, f"size>{max_size_mb}mb"

    min_size_mb = filters.get("min_size_mb")
    if (
        isinstance(min_size_mb, int)
        and hit.size is not None
        and hit.size < min_size_mb * 1024 * 1024
    ):
        return False, f"size<{min_size_mb}mb"

    # Year range — parsed from the release title
    year_min = filters.get("year_min")
    year_max = filters.get("year_max")
    if isinstance(year_min, int) or isinstance(year_max, int):
        year = extract_year(hit.title)
        if year is None:
            return False, "no year in title"
        if isinstance(year_min, int) and year < year_min:
            return False, f"year<{year_min}"
        if isinstance(year_max, int) and year > year_max:
            return False, f"year>{year_max}"

    # Kind filter — movie vs series
    kind = filters.get("kind")
    if kind == "movie" and looks_like_series(hit.title):
        return False, "kind:not-movie"
    if kind == "series" and not looks_like_series(hit.title):
        return False, "kind:not-series"
    # For kind=game|software|audiobook|comic we trust the feed's category_hint
    # and/or the caller's keyword filters rather than trying to parse titles.

    # Category filter — only apply if hit has a category and filter specifies one
    wanted_categories = filters.get("categories")
    if isinstance(wanted_categories, list) and wanted_categories:
        cat = (hit.category or "").lower()
        if cat and cat not in [str(c).lower() for c in wanted_categories]:
            return False, f"category:{cat}"

    title_lower = hit.title.lower()
    reject = filters.get("reject") or []
    if isinstance(reject, list):
        for token in reject:
            if isinstance(token, str) and token.lower() in title_lower:
                return False, f"reject:{token}"

    require = filters.get("require") or []
    if isinstance(require, list):
        for token in require:
            if isinstance(token, str) and token.lower() not in title_lower:
                return False, f"missing:{token}"

    # Strict title match. Picks the right normalizer based on whether
    # the hit looks like an episode (truncate at SxxExx) or a movie
    # (truncate at the trailing year). Both strip embedded years and
    # collapse to lowercase alnum so:
    #   - "The.Boys.2019.S01E01"          -> "theboys"
    #   - "Dune.Part.Two.2024.2160p..."   -> "duneparttwo"
    #   - "The.Boys.Presents.Diabolical." -> "theboyspresentsdiabolical"
    # Exact match required — keeps "The Boys" from grabbing the spinoff
    # and "Dune Part Two" from grabbing a "Trailer" cut, while still
    # accepting all release groups for the actual film/show.
    require_title = filters.get("require_title")
    if isinstance(require_title, str) and require_title.strip():
        import re as _re

        wanted = _re.sub(r"[^a-z0-9]+", "", require_title.lower())
        if extract_episode(hit.title) is not None:
            actual = normalized_show_prefix(hit.title)
        else:
            actual = normalized_movie_name(hit.title)
        if wanted and actual != wanted:
            return False, f"title!={require_title}"

    # Episode-only mode for series tasks: drop season packs and
    # multi-episode bundles that don't carry an explicit SxxExx marker.
    if filters.get("require_episode") and extract_episode(hit.title) is None:
        return False, "no episode marker"

    return True, "ok"


@dataclass(slots=True)
class _SendOutcome:
    ok: bool
    message: str
    client_id: int | None = None
    identifier: str | None = None


async def _prefetch_torrent(
    session: Session,
    hit: search_service.SearchHit,
    logger: io.StringIO,
) -> bytes | None:
    """Pre-fetch a .torrent file server-side using the indexer's credentials.

    Download clients (Transmission, Deluge) fetch URLs with their own
    HTTP client and don't carry indexer cookies/tokens. Private trackers
    that require cookie auth for downloads (e.g. RarTracker/Superbits)
    will return 401 to the client. We solve this by fetching the
    .torrent here, where we have access to the indexer's stored
    credentials, and passing raw content to the client instead of a URL.

    Returns the .torrent bytes on success, or ``None`` if the fetch
    isn't needed or fails (callers fall back to URL mode).
    """
    url = hit.download_url
    if not url or not url.startswith(("http://", "https://")):
        return None
    source = hit.source
    if not source or source.startswith("rss:"):
        return None

    # Look up the indexer to get auth credentials.
    indexer = session.exec(select(IndexerRow).where(IndexerRow.name == source)).first()
    headers: dict[str, str] = {}
    if indexer is not None:
        try:
            creds = decrypt_json(indexer.credentials_cipher)
        except Exception:
            creds = {}
        cookie = creds.get("session_cookie")
        if isinstance(cookie, str) and cookie:
            headers["Cookie"] = cookie
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
            resp = await c.get(url, headers=headers)
        if resp.status_code >= 400:
            logger.write(f"  prefetch: HTTP {resp.status_code} for {source} (will try URL mode)\n")
            return None
        data = resp.content
        # Quick sanity check — .torrent files are bencoded and start with 'd'.
        if data and (data[0:1] == b"d" or data[0:2] == b"\x1f\x8b"):
            logger.write(f"  prefetch: got {len(data)} bytes from {source}\n")
            return data
        logger.write("  prefetch: response not a torrent file, skip\n")
        return None
    except Exception as e:
        logger.write(f"  prefetch: {e} (will try URL mode)\n")
        return None


async def _send_to_clients(
    session: Session,
    hit: search_service.SearchHit,
    output_names: list[str],
    logger: io.StringIO,
) -> _SendOutcome:
    if not hit.download_url:
        return _SendOutcome(ok=False, message="no download url")

    # Pre-fetch .torrent content server-side so download clients don't
    # need the indexer's auth cookies. Falls back to URL mode on failure.
    prefetched: bytes | None = None
    if hit.protocol is Protocol.TORRENT and not (hit.download_url.startswith("magnet:")):
        prefetched = await _prefetch_torrent(session, hit, logger)

    for name in output_names:
        client_row = session.exec(select(Client).where(Client.name == name)).first()
        if client_row is None:
            logger.write(f"  output {name}: not found\n")
            continue
        if not client_row.enabled:
            logger.write(f"  output {name}: disabled\n")
            continue
        protocol = ClientType(client_row.type).protocol
        if protocol is not hit.protocol:
            logger.write(f"  output {name}: protocol mismatch\n")
            continue
        try:
            driver = client_registry.build_driver(client_row)
        except ClientError as e:
            logger.write(f"  output {name}: build failed: {e}\n")
            continue
        try:
            release = Release(
                title=hit.title,
                protocol=hit.protocol,
                download_url=hit.download_url if prefetched is None else None,
                content=prefetched,
                size=hit.size,
                infohash=hit.infohash,
            )
            options = AddOptions(
                category=client_row.default_category,
                save_path=client_row.default_save_path,
            )
            if protocol is Protocol.TORRENT:
                assert isinstance(driver, TorrentClient)
                result = await driver.add_torrent(release, options)
            else:
                assert isinstance(driver, UsenetClient)
                result = await driver.add_nzb(release, options)
            logger.write(f"  output {name}: {result.ok} ({result.message or ''})\n")
            if result.ok:
                return _SendOutcome(
                    ok=True,
                    message=name,
                    client_id=client_row.id,
                    identifier=result.identifier,
                )
        except ClientError as e:
            logger.write(f"  output {name}: {e}\n")
        finally:
            await driver.close()
    return _SendOutcome(ok=False, message="no output accepted")


async def _remove_from_client(
    session: Session,
    seen: SeenReleaseRow,
    logger: io.StringIO,
) -> bool:
    """Remove a previously-grabbed release from its download client.

    Returns ``True`` if the removal succeeded (or the item was already
    gone). Used by the upgrade path to evict lower-quality grabs.
    """
    if not seen.client_id or not seen.grabbed_identifier:
        logger.write(f"  upgrade: cannot remove '{seen.title}' — no client/identifier\n")
        return False
    client_row = session.get(Client, seen.client_id)
    if client_row is None:
        logger.write(f"  upgrade: client id={seen.client_id} not found\n")
        return False
    try:
        driver: DownloadClient = client_registry.build_driver(client_row)
    except ClientError as e:
        logger.write(f"  upgrade: build driver failed: {e}\n")
        return False
    try:
        ok = await driver.remove_download(seen.grabbed_identifier, delete_data=True)
        logger.write(f"  upgrade: remove '{seen.title}' from {client_row.name}: {ok}\n")
        return ok
    except ClientError as e:
        logger.write(f"  upgrade: remove failed: {e}\n")
        return False
    finally:
        await driver.close()


async def run_task(
    session: Session,
    task: TaskRow,
    *,
    dry_run: bool = False,
) -> TaskRunRow:
    run = TaskRunRow(
        task_id=task.id or 0,
        started_at=datetime.now(UTC),
        status="running",
        dry_run=dry_run,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    logger = io.StringIO()
    considered = 0
    accepted = 0
    grabbed_keys: set[str] = set()
    try:
        config = parse_task_config(task.config_yaml)
        inputs = config.get("inputs") or []
        filters = config.get("filters") or {}
        outputs = config.get("outputs") or []
        if not isinstance(outputs, list):
            outputs = []

        for input_spec in inputs:
            if not isinstance(input_spec, dict):
                continue
            kind = input_spec.get("kind")

            hits: list[search_service.SearchHit] = []

            if kind == "search":
                query = str(input_spec.get("query", ""))
                if not query:
                    continue
                categories_raw = input_spec.get("categories") or []
                category_values: list[Category] = []
                for c in categories_raw:
                    try:
                        category_values.append(Category(c))
                    except ValueError:
                        continue
                tmdb_id_raw = input_spec.get("tmdb_id")
                tmdb_id = str(tmdb_id_raw) if tmdb_id_raw not in (None, "") else None
                imdb_id_raw = input_spec.get("imdb_id")
                imdb_id = str(imdb_id_raw) if imdb_id_raw not in (None, "") else None
                proto_raw = input_spec.get("protocol")
                search_protocol: Protocol | None = None
                if isinstance(proto_raw, str):
                    try:
                        search_protocol = Protocol(proto_raw)
                    except ValueError:
                        search_protocol = None
                # Per-season backfill: a single tvsearch caps at ~100 hits,
                # which usually only covers the most recent season + a few
                # stragglers. When the user has explicitly enabled backfill
                # (or it's a watchlist series with a tmdb_id and no
                # season set), iterate season=1..N. To avoid burning 20+
                # indexer hits per cron after the initial backfill is
                # done, we shrink the scan to the latest 2 seasons once
                # this task already has any "sent" releases on file —
                # the periodic check then only looks for new episodes of
                # the current and upcoming season.
                seasons_cfg = input_spec.get("seasons")
                seasons_to_query: list[int | None] = [None]

                def _highest_seen_season() -> int:
                    rows = session.exec(
                        select(SeenReleaseRow)
                        .where(SeenReleaseRow.task_id == task.id)
                        .where(SeenReleaseRow.outcome == "sent")
                    ).all()
                    best = 0
                    import re

                    for r in rows:
                        m = re.match(r"e:[^:]+:s(\d+)e\d+", r.key)
                        if m:
                            best = max(best, int(m.group(1)))
                    return best

                if seasons_cfg == "auto" or (
                    seasons_cfg is None and tmdb_id and Category.TV in category_values
                ):
                    # high == 0 → never backfilled, do full sweep (1..20).
                    # high > 0  → already have content, just check current
                    #             season and the next one (in case it
                    #             just aired).
                    high = _highest_seen_season()
                    seasons_to_query = list(range(1, 21)) if high == 0 else [high, high + 1]
                elif isinstance(seasons_cfg, list):
                    seasons_to_query = [int(s) for s in seasons_cfg if isinstance(s, (int, str))]
                elif isinstance(seasons_cfg, int):
                    seasons_to_query = [seasons_cfg]

                extras = ""
                if tmdb_id:
                    extras += f" tmdb={tmdb_id}"
                if imdb_id:
                    extras += f" imdb={imdb_id}"
                if search_protocol is not None:
                    extras += f" protocol={search_protocol.value}"
                if seasons_to_query != [None]:
                    extras += f" backfill={seasons_to_query[0]}..{seasons_to_query[-1]}"
                logger.write(f"search: {query} (cats={category_values}{extras})\n")

                hits = []
                seen_urls: set[str] = set()
                empty_streak = 0
                for season in seasons_to_query:
                    response = await search_service.run_search(
                        session,
                        query,
                        categories=category_values,
                        tmdb_id=tmdb_id,
                        imdb_id=imdb_id,
                        season=season,
                        protocol=search_protocol,
                    )
                    new = [
                        h
                        for h in response.hits
                        if h.download_url and h.download_url not in seen_urls
                    ]
                    for h in new:
                        if h.download_url:
                            seen_urls.add(h.download_url)
                    if season is None:
                        logger.write(
                            f"  got {len(response.hits)} hits "
                            f"in {response.elapsed_ms}ms from {response.indexers_used} indexers\n"
                        )
                    else:
                        logger.write(
                            f"  s{season:02d}: {len(response.hits)} hits ({len(new)} new) "
                            f"in {response.elapsed_ms}ms\n"
                        )
                    hits.extend(new)
                    if season is not None and len(new) == 0:
                        empty_streak += 1
                        if empty_streak >= 2:
                            logger.write("  stop backfill: 2 empty seasons in a row\n")
                            break
                    else:
                        empty_streak = 0
            elif kind == "rss_items":
                proto_str = input_spec.get("protocol")
                protocol_filter: Protocol | None = None
                if isinstance(proto_str, str):
                    try:
                        protocol_filter = Protocol(proto_str)
                    except ValueError:
                        protocol_filter = None
                feed_names_raw = input_spec.get("feeds")
                feed_names = (
                    [str(f) for f in feed_names_raw] if isinstance(feed_names_raw, list) else None
                )
                limit = int(input_spec.get("limit", 500))
                logger.write(
                    f"rss_items: protocol={protocol_filter} feeds={feed_names} limit={limit}\n"
                )
                hits = _read_rss_items(
                    session,
                    feed_names=feed_names,
                    protocol=protocol_filter,
                    limit=limit,
                )
                logger.write(f"  loaded {len(hits)} cached RSS items\n")
            else:
                logger.write(f"skip unsupported input kind: {kind}\n")
                continue

            # Rank hits so the first one that passes filters is the best
            # available, not just the first one the indexer returned.
            # Resolve quality profile if the task references one; otherwise
            # the hardcoded defaults keep the old behaviour. Profile
            # reject_tokens are merged into the filter dict so the hard
            # filter honours them alongside any task-specific rejects.
            profile_name = filters.get("quality_profile")
            active_profile: dict[str, Any] | None = None
            if isinstance(profile_name, str) and profile_name.strip():
                active_profile = quality_profile.get_profile(session, profile_name.strip())
                logger.write(f"  quality profile: {profile_name}\n")
                profile_rejects = active_profile.get("reject_tokens") or []
                if isinstance(profile_rejects, list) and profile_rejects:
                    existing = filters.get("reject") or []
                    if not isinstance(existing, list):
                        existing = []
                    merged = list(existing)
                    for tok in profile_rejects:
                        if tok not in merged:
                            merged.append(tok)
                    filters["reject"] = merged

            prefer_quality = filters.get("prefer_quality")
            max_size_mb_cfg = (
                filters.get("max_size_mb") if isinstance(filters.get("max_size_mb"), int) else None
            )
            prefer_quality_str = (
                str(prefer_quality).strip()
                if isinstance(prefer_quality, str) and prefer_quality
                else None
            )
            hits.sort(
                key=lambda h: score_hit(
                    h,
                    prefer_quality=prefer_quality_str,
                    max_size_mb=max_size_mb_cfg,
                    profile=active_profile,
                ),
                reverse=True,
            )

            # Upgrade configuration — per-task opt-in via filters.
            upgrades_enabled = bool(filters.get("enable_upgrades"))
            upgrade_until_tier = int(filters.get("upgrade_until_tier") or 0)
            max_upgrades = int(filters.get("max_upgrades_per_run") or 3)
            upgrades_this_run = 0
            if upgrades_enabled:
                logger.write(
                    f"  upgrades: enabled (until_tier={upgrade_until_tier}, "
                    f"max={max_upgrades}/run)\n"
                )

            for hit in hits:
                considered += 1
                ok, reason = _pass_filter(hit, filters)
                if not ok:
                    logger.write(f"  drop '{hit.title}': {reason}\n")
                    continue
                key = _seen_key(hit)
                if key in grabbed_keys:
                    logger.write(f"  skip '{hit.title}': dup within run\n")
                    continue

                hit_score = score_hit(
                    hit,
                    prefer_quality=prefer_quality_str,
                    max_size_mb=max_size_mb_cfg,
                    profile=active_profile,
                )
                hit_tier = compute_quality_tier(hit, active_profile)

                existing = session.exec(
                    select(SeenReleaseRow)
                    .where(SeenReleaseRow.task_id == task.id)
                    .where(SeenReleaseRow.key == key)
                    .where(SeenReleaseRow.outcome == "sent")
                ).first()

                if existing is not None:
                    # Already grabbed — check if we should upgrade.
                    if not upgrades_enabled:
                        logger.write(f"  skip '{hit.title}': already grabbed\n")
                        continue
                    if upgrades_this_run >= max_upgrades:
                        logger.write(
                            f"  skip '{hit.title}': upgrade throttle "
                            f"({upgrades_this_run}/{max_upgrades})\n"
                        )
                        continue
                    existing_tier = existing.quality_tier or 0
                    existing_score = existing.quality_score or 0.0
                    if existing_tier >= upgrade_until_tier and upgrade_until_tier > 0:
                        logger.write(
                            f"  skip '{hit.title}': already at target tier "
                            f"({existing_tier}>={upgrade_until_tier})\n"
                        )
                        continue
                    if hit_score <= existing_score:
                        logger.write(
                            f"  skip '{hit.title}': not better "
                            f"(score {hit_score:.0f} <= {existing_score:.0f})\n"
                        )
                        continue

                    # This hit is genuinely better — attempt upgrade.
                    logger.write(
                        f"  UPGRADE '{existing.title}' (tier={existing_tier}, "
                        f"score={existing_score:.0f}) -> '{hit.title}' "
                        f"(tier={hit_tier}, score={hit_score:.0f})\n"
                    )
                    if dry_run:
                        logger.write(f"  [dry-run] would upgrade '{hit.title}'\n")
                        grabbed_keys.add(key)
                        accepted += 1
                        upgrades_this_run += 1
                        continue

                    # Remove old release from client.
                    removed = await _remove_from_client(session, existing, logger)
                    if not removed:
                        logger.write("  upgrade: skipping — could not remove old release\n")
                        continue

                    # Send new release.
                    outcome = await _send_to_clients(session, hit, outputs, logger)
                    # Mark old release as upgraded.
                    existing.outcome = "upgraded"
                    session.add(existing)
                    seen = SeenReleaseRow(
                        task_id=task.id or 0,
                        key=key,
                        title=hit.title,
                        outcome="sent" if outcome.ok else "failed",
                        reason=outcome.message[:512],
                        client_id=outcome.client_id,
                        grabbed_identifier=outcome.identifier,
                        download_status="queued" if outcome.ok and outcome.identifier else None,
                        quality_score=hit_score,
                        quality_tier=hit_tier,
                        upgraded_from_id=existing.id,
                    )
                    session.add(seen)
                    if outcome.ok:
                        grabbed_keys.add(key)
                        accepted += 1
                        upgrades_this_run += 1
                        await notification_service.dispatch(
                            session,
                            notification_service.Event(
                                kind="task.upgraded",
                                title=f"Upgraded: {hit.title[:120]}",
                                description=(
                                    f"Replaced **{existing.title[:80]}** "
                                    f"(tier {existing_tier}) with "
                                    f"**{hit.title[:80]}** (tier {hit_tier}) "
                                    f"via task **{task.name}**."
                                ),
                                fields={
                                    "Task": task.name,
                                    "Old": existing.title[:100],
                                    "New": hit.title[:100],
                                    "Client": outcome.message,
                                    "Quality": f"tier {existing_tier} -> {hit_tier}",
                                    "Score": f"{existing_score:.0f} -> {hit_score:.0f}",
                                },
                            ),
                        )
                    continue

                # Fresh grab — no existing release for this key.
                if dry_run:
                    logger.write(f"  [dry-run] would send '{hit.title}'\n")
                    grabbed_keys.add(key)
                    accepted += 1
                    continue
                outcome = await _send_to_clients(session, hit, outputs, logger)
                seen = SeenReleaseRow(
                    task_id=task.id or 0,
                    key=key,
                    title=hit.title,
                    outcome="sent" if outcome.ok else "failed",
                    reason=outcome.message[:512],
                    client_id=outcome.client_id,
                    grabbed_identifier=outcome.identifier,
                    download_status="queued" if outcome.ok and outcome.identifier else None,
                    quality_score=hit_score,
                    quality_tier=hit_tier,
                )
                session.add(seen)
                if outcome.ok:
                    grabbed_keys.add(key)
                    accepted += 1
                    await notification_service.dispatch(
                        session,
                        notification_service.Event(
                            kind="task.grabbed",
                            title=f"Grabbed: {hit.title[:120]}",
                            description=f"Sent to **{outcome.message}** by task **{task.name}**.",
                            fields={
                                "Task": task.name,
                                "Client": outcome.message,
                                "Size": _format_size(hit.size) if hit.size else "?",
                            },
                        ),
                    )
                else:
                    await notification_service.dispatch(
                        session,
                        notification_service.Event(
                            kind="task.send_failed",
                            title=f"Send failed: {hit.title[:120]}",
                            description=(
                                f"Task **{task.name}** found a match but no client "
                                f"accepted it: {outcome.message}"
                            ),
                            fields={"Task": task.name, "Reason": outcome.message},
                        ),
                    )
        # Distinguish between "ran cleanly and grabbed something", "ran
        # cleanly but nothing matched", and "ran cleanly and found zero
        # hits at all". Previously everything was "success" which made
        # the UI lie about whether a download actually happened.
        if accepted > 0:
            run.status = "success"
        elif considered > 0:
            run.status = "no_match"
        else:
            run.status = "no_hits"
    except Exception as e:  # pragma: no cover
        logger.write(f"ERROR: {e}\n")
        run.status = "error"
        log.exception("task.run.failed", task=task.name)
    finally:
        run.finished_at = datetime.now(UTC)
        run.considered = considered
        run.accepted = accepted
        run.log = logger.getvalue()
        session.add(run)
        task.last_run_at = run.finished_at
        task.last_run_status = run.status
        task.last_run_accepted = accepted
        task.last_run_considered = considered
        session.add(task)
        session.commit()
        session.refresh(run)

    return run
