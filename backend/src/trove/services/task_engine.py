from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import structlog
import yaml
from sqlmodel import Session, select

from trove.clients.base import (
    AddOptions,
    ClientError,
    ClientType,
    Protocol,
    Release,
    TorrentClient,
    UsenetClient,
)
from trove.indexers.base import Category
from trove.models.client import Client
from trove.models.feed import FeedRow, RssItemRow
from trove.models.task import SeenReleaseRow, TaskRow, TaskRunRow
from trove.parsing.title import extract_year, looks_like_series
from trove.services import client_registry, search_service

log = structlog.get_logger()


def parse_task_config(config_yaml: str) -> dict[str, Any]:
    if not config_yaml.strip():
        return {"inputs": [], "filters": {}, "outputs": []}
    data = yaml.safe_load(config_yaml)
    if not isinstance(data, dict):
        raise ValueError("task config must be a YAML mapping")
    return data


def _seen_key(release: search_service.SearchHit) -> str:
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
    min_seeders = filters.get("min_seeders")
    if isinstance(min_seeders, int) and (hit.seeders or 0) < min_seeders:
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

    return True, "ok"


async def _send_to_clients(
    session: Session,
    hit: search_service.SearchHit,
    output_names: list[str],
    logger: io.StringIO,
) -> tuple[bool, str]:
    if not hit.download_url:
        return False, "no download url"
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
                download_url=hit.download_url,
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
                return True, name
        except ClientError as e:
            logger.write(f"  output {name}: {e}\n")
        finally:
            await driver.close()
    return False, "no output accepted"


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
                logger.write(f"search: {query} (cats={category_values})\n")
                response = await search_service.run_search(
                    session, query, categories=category_values
                )
                logger.write(
                    f"  got {len(response.hits)} hits in {response.elapsed_ms}ms "
                    f"from {response.indexers_used} indexers\n"
                )
                hits = response.hits
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

            for hit in hits:
                considered += 1
                ok, reason = _pass_filter(hit, filters)
                if not ok:
                    logger.write(f"  drop '{hit.title}': {reason}\n")
                    continue
                key = _seen_key(hit)
                existing = session.exec(
                    select(SeenReleaseRow)
                    .where(SeenReleaseRow.task_id == task.id)
                    .where(SeenReleaseRow.key == key)
                ).first()
                if existing is not None:
                    logger.write(f"  skip '{hit.title}': already seen\n")
                    continue
                if dry_run:
                    logger.write(f"  [dry-run] would send '{hit.title}'\n")
                    accepted += 1
                    continue
                sent, info = await _send_to_clients(session, hit, outputs, logger)
                seen = SeenReleaseRow(
                    task_id=task.id or 0,
                    key=key,
                    title=hit.title,
                    outcome="sent" if sent else "failed",
                    reason=info[:512],
                )
                session.add(seen)
                if sent:
                    accepted += 1
        run.status = "success"
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
