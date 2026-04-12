from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog
import yaml
from sqlmodel import Session, select

from trove.ai import client as ai_client
from trove.clients.base import ClientType, Protocol
from trove.indexers.base import Category
from trove.models.client import Client

log = structlog.get_logger()

SYSTEM_PROMPT = """You are Trove's assistant. The user will describe what they want. \
Classify the intent and extract parameters. Reply with ONE JSON object, no prose, no markdown \
fences. Valid intents and their fields:

IMPORTANT about protocol: Trove has two download protocols — torrent (Deluge,
Transmission) and usenet (SABnzbd, NZBGet). By default, tasks search BOTH
and let the user's configured clients pick whichever protocol the best hit
belongs to. Only set the optional ``protocol`` field if the user EXPLICITLY
says "via torrent", "as nzb", "only usenet", "skip usenet", or similar.
Without an explicit preference, omit it — the user wants the best match
regardless of source.

1. add_series — user wants to automatically download every new episode of a specific TV show.
   fields: title (string, required), quality (string, optional: "2160p"|"1080p"|"720p"|"any"),
           year (int, optional),
           protocol (string, optional: "torrent"|"usenet" — ONLY if user explicitly says)

2. add_movie — user wants to download ONE specific movie once it's available.
   fields: title (string, required), year (int, optional), quality (string, optional),
           protocol (string, optional: "torrent"|"usenet" — ONLY if user explicitly says)

3. add_filter_task — user wants a STANDING RULE that auto-grabs ALL items matching a filter.
   Use this when the user says "all", "always", "everything", a year range, or a broad
   category rule. NOT for a specific title.
   fields:
     kind ("movie"|"series"|"game"|"software"|"audiobook"|"comic"|"music"|"any", required),
     year_min (int, optional, inclusive, useful for movies),
     year_max (int, optional, inclusive, useful for movies),
     quality (string, optional: "2160p"|"1080p"|"720p"|"any", only for video),
     max_size_gb (int, optional),
     require_tokens (list of strings, optional, MUST appear in title e.g. ["linux", "iso"]),
     reject_tokens (list of strings, optional, e.g. ["nuked", "rerip"]),
     protocol (string, optional: "torrent"|"usenet" — ONLY if user explicitly says)

4. search_now — user wants to see search results RIGHT NOW, not create a task.
   fields: query (string, required)

5. add_to_watchlist — user wants to track a title but not auto-download yet.
   fields: kind ("series"|"movie"), title (string), year (int, optional)

6. bulk_tmdb — user wants to bulk-add movies/TV from TMDB to the watchlist based on
   metadata criteria (rating, release date, popularity). This queries TMDB directly
   rather than reading from RSS feeds. Each match is added to the watchlist and
   auto-promoted to a download task.
   fields:
     kind ("movie"|"tv", required),
     rating_min (float, optional, e.g. 6.0 for "rating over 6"),
     date_from (string, optional, "today" or YYYY-MM-DD — earliest release date),
     date_to (string, optional, YYYY-MM-DD — latest release date),
     year_min (int, optional),
     year_max (int, optional),
     quality (string, optional: "2160p"|"1080p"|"720p"|"best"),
     limit (int, optional, default 50, max 100)

7. chat — user is asking a general question, small talk, or something unsupported.
   fields: message (string, your plain-text reply)

Examples:
User: add the big bang theory to my downloads
{"intent": "add_series", "params": {"title": "The Big Bang Theory", "quality": "1080p"}}

User: i want dune part two in 4k
{"intent": "add_movie", "params": {"title": "Dune: Part Two", "quality": "2160p"}}

User: always grab all movies newer than 2022 in 1080p
{"intent": "add_filter_task", "params": {"kind": "movie", "year_min": 2022, "quality": "1080p"}}

User: download every 4k movie from the last 3 years
{"intent": "add_filter_task", "params": {"kind": "movie", "year_min": 2023, "quality": "2160p"}}

User: grab any movie from 2020-2023 under 5gb
{"intent": "add_filter_task", "params": {"kind": "movie", "year_min": 2020, "year_max": 2023, "max_size_gb": 5}}

User: download all new linux iso releases
{"intent": "add_filter_task", "params": {"kind": "software", "require_tokens": ["linux", "iso"]}}

User: grab every new switch game
{"intent": "add_filter_task", "params": {"kind": "game", "require_tokens": ["switch"]}}

User: always get new audiobooks
{"intent": "add_filter_task", "params": {"kind": "audiobook"}}

User: grab severance via usenet only
{"intent": "add_series", "params": {"title": "Severance", "protocol": "usenet"}}

User: download oppenheimer as a torrent
{"intent": "add_movie", "params": {"title": "Oppenheimer", "protocol": "torrent"}}

User: get the best version of blade runner 2049
{"intent": "add_movie", "params": {"title": "Blade Runner 2049"}}

User: search for the bear season 3
{"intent": "search_now", "params": {"query": "the bear s03"}}

User: remember severance, i might grab it later
{"intent": "add_to_watchlist", "params": {"kind": "series", "title": "Severance"}}

User: why did last night's run fail
{"intent": "chat", "params": {"message": "Check the task history page — each run shows a detailed trace."}}

User: hent alle film fra idag og frem der har en rating på over 6 i bedst mulige kvalitet
{"intent": "bulk_tmdb", "params": {"kind": "movie", "rating_min": 6.0, "date_from": "today", "quality": "best"}}

User: grab all highly rated movies from 2024 in 1080p
{"intent": "bulk_tmdb", "params": {"kind": "movie", "year_min": 2024, "rating_min": 7.0, "quality": "1080p"}}

User: add all upcoming movies with rating over 7 to my watchlist
{"intent": "bulk_tmdb", "params": {"kind": "movie", "rating_min": 7.0, "date_from": "today"}}

User: download top 20 popular tv shows from this year
{"intent": "bulk_tmdb", "params": {"kind": "tv", "year_min": 2026, "limit": 20}}

Reply with JSON ONLY, starting with { and ending with }."""


@dataclass(slots=True)
class ProposedAction:
    intent: str
    params: dict[str, Any]
    description: str
    preview: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = True
    message: str | None = None
    warnings: list[str] = field(default_factory=list)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "task"


def _parse_protocol(raw: Any) -> Protocol | None:
    """Coerce an LLM-supplied protocol hint into a Protocol enum, or None."""
    if not isinstance(raw, str):
        return None
    lowered = raw.lower().strip()
    if lowered in ("torrent", "torrents", "bittorrent"):
        return Protocol.TORRENT
    if lowered in ("usenet", "nzb"):
        return Protocol.USENET
    return None


def _enabled_indexer_protocols(session: Session) -> set[Protocol]:
    """Return the set of protocols at least one enabled indexer handles."""
    from trove.models.indexer import IndexerRow

    rows = session.exec(
        select(IndexerRow).where(IndexerRow.enabled == True)  # noqa: E712
    ).all()
    out: set[Protocol] = set()
    for r in rows:
        try:
            out.add(Protocol(r.protocol))
        except ValueError:
            continue
    return out


async def _probe_indexers(
    session: Session,
    query: str,
    *,
    category: Category,
    protocol: Protocol | None = None,
    tmdb_id: int | None = None,
    imdb_id: str | None = None,
) -> tuple[int, str | None]:
    """Fire a cheap search across enabled indexers to see if the thing
    the user wants is actually findable. Returns (hit_count, sample_title).

    Used by add_series / add_movie at propose time so the AI can tell
    the user "I found 18 hits matching 'Scream 7'" or "0 hits — the
    movie may not be out yet" *before* the task is even created.
    """
    from trove.services import search_service

    try:
        response = await search_service.run_search(
            session,
            query,
            categories=[category],
            protocol=protocol,
            limit=5,
            timeout_per_indexer=10.0,
            tmdb_id=str(tmdb_id) if tmdb_id else None,
            imdb_id=str(imdb_id) if imdb_id else None,
        )
    except Exception:
        # Probe failures are non-fatal — the task can still be created.
        return 0, None
    count = len(response.hits)
    sample = response.hits[0].title if response.hits else None
    return count, sample


def _pick_default_clients(
    session: Session,
    preferred_protocol: Protocol | None = None,
) -> list[Client]:
    """Return one enabled client per protocol the user has configured.

    If ``preferred_protocol`` is given, that protocol's client is returned
    first; the other protocol (if available) follows. This lets callers
    build multi-output tasks that route torrent hits to the torrent
    client and usenet hits to the usenet client automatically.

    Returns an empty list if the user has no enabled clients at all.
    """
    stmt = select(Client).where(Client.enabled == True)  # noqa: E712
    rows = list(session.exec(stmt).all())
    if not rows:
        return []

    torrent_clients: list[Client] = []
    usenet_clients: list[Client] = []
    for row in rows:
        try:
            proto = ClientType(row.type).protocol
        except ValueError:
            continue
        if proto is Protocol.TORRENT:
            torrent_clients.append(row)
        elif proto is Protocol.USENET:
            usenet_clients.append(row)

    picked: list[Client] = []
    # First: the preferred protocol if any and we have a client
    if preferred_protocol is Protocol.TORRENT and torrent_clients:
        picked.append(torrent_clients[0])
    elif preferred_protocol is Protocol.USENET and usenet_clients:
        picked.append(usenet_clients[0])
    # Then fill in any protocol not already represented, starting with
    # torrent for the default-preferred ordering.
    if not any(ClientType(c.type).protocol is Protocol.TORRENT for c in picked) and torrent_clients:
        picked.append(torrent_clients[0])
    if not any(ClientType(c.type).protocol is Protocol.USENET for c in picked) and usenet_clients:
        picked.append(usenet_clients[0])
    return picked


def _build_series_task_yaml(
    title: str,
    quality: str | None,
    output_clients: list[str],
    *,
    tmdb_id: int | None = None,
    imdb_id: str | None = None,
    protocol: Protocol | None = None,
) -> str:
    reject = ["cam", "telesync", "hdcam", "workprint"]
    filters: dict[str, Any] = {
        "min_seeders": 2,
        "reject": reject,
        # Strict show-name match — keeps "The Boys" from grabbing every
        # Fringe / Criminal Minds episode whose title happens to contain
        # "The Boy(s)", and from grabbing the spinoff "The Boys Presents
        # Diabolical". Indexers that honor tmdbid filter at the source;
        # this is the fallback for the rest.
        "require_title": title,
        # Episode-level only — drop season packs and multi-episode
        # bundles like "The.Boys.Season.4" or "The.Boys.S01.Complete".
        "require_episode": True,
    }
    if quality and quality != "any":
        # Soft preference — ranking boost, not a hard filter. If the
        # desired quality isn't available, the engine still grabs the
        # best thing it can find.
        filters["prefer_quality"] = quality
    input_spec: dict[str, Any] = {
        "kind": "search",
        "query": title,
        "categories": ["tv"],
    }
    if tmdb_id:
        input_spec["tmdb_id"] = int(tmdb_id)
    if imdb_id:
        input_spec["imdb_id"] = str(imdb_id)
    if protocol is not None:
        input_spec["protocol"] = protocol.value
    config: dict[str, Any] = {
        "inputs": [input_spec],
        "filters": filters,
        "outputs": list(output_clients),
    }
    return yaml.safe_dump(config, sort_keys=False)


def _build_movie_task_yaml(
    title: str,
    year: int | None,
    quality: str | None,
    output_clients: list[str],
    *,
    tmdb_id: int | None = None,
    imdb_id: str | None = None,
    protocol: Protocol | None = None,
) -> str:
    query = f"{title} {year}" if year else title
    filters: dict[str, Any] = {
        "min_seeders": 5,
        "reject": ["cam", "telesync", "hdcam", "workprint", "hdts"],
        "require_title": title,
    }
    if quality and quality != "any":
        filters["prefer_quality"] = quality
    input_spec: dict[str, Any] = {
        "kind": "search",
        "query": query,
        "categories": ["movies"],
    }
    if tmdb_id:
        input_spec["tmdb_id"] = int(tmdb_id)
    if imdb_id:
        input_spec["imdb_id"] = str(imdb_id)
    if protocol is not None:
        input_spec["protocol"] = protocol.value
    config: dict[str, Any] = {
        "inputs": [input_spec],
        "filters": filters,
        "outputs": list(output_clients),
    }
    return yaml.safe_dump(config, sort_keys=False)


def _build_filter_task_yaml(
    kind: str,
    year_min: int | None,
    year_max: int | None,
    quality: str | None,
    max_size_gb: int | None,
    output_clients: list[str],
    protocols: list[str],
    require_tokens: list[str] | None = None,
    reject_tokens: list[str] | None = None,
) -> str:
    filters: dict[str, Any] = {"min_seeders": 2}

    # Default reject lists tailored to content type
    if kind in ("movie", "series"):
        default_reject = ["cam", "telesync", "hdcam", "workprint", "hdts"]
    elif kind == "game":
        default_reject = ["nuked", "dlc-only", "update-only"]
    elif kind in ("software", "audiobook", "comic"):
        default_reject: list[str] = []
    else:
        default_reject = []

    combined_reject = list(default_reject)
    if reject_tokens:
        for token in reject_tokens:
            if token not in combined_reject:
                combined_reject.append(token)
    if combined_reject:
        filters["reject"] = combined_reject

    if kind in ("movie", "series"):
        filters["kind"] = kind

    if year_min is not None:
        filters["year_min"] = year_min
    if year_max is not None:
        filters["year_max"] = year_max

    # quality + require_tokens merge into require list
    require_list: list[str] = []
    if quality and quality != "any":
        require_list.append(quality)
    if require_tokens:
        require_list.extend(require_tokens)
    if require_list:
        filters["require"] = require_list

    if max_size_gb is not None:
        filters["max_size_mb"] = max_size_gb * 1024

    # Build one rss_items input per protocol so both torrent and usenet
    # feeds are considered. If only one protocol is given, we emit a
    # single input. An empty protocols list means "all feeds regardless
    # of protocol" — we emit a single input without the protocol filter.
    inputs: list[dict[str, Any]] = []
    if not protocols:
        inputs.append({"kind": "rss_items", "limit": 1000})
    else:
        for proto in protocols:
            inputs.append({"kind": "rss_items", "protocol": proto, "limit": 1000})

    config: dict[str, Any] = {
        "inputs": inputs,
        "filters": filters,
        "outputs": list(output_clients),
    }
    return yaml.safe_dump(config, sort_keys=False)


async def classify_intent(prompt: str) -> dict[str, Any]:
    """Ask the LLM to classify the user's request and extract parameters."""
    raw = await ai_client.complete(
        prompt,
        system=SYSTEM_PROMPT,
        temperature=0.1,
        cache=False,
    )
    data = _extract_json(raw)
    if data is None:
        return {
            "intent": "chat",
            "params": {"message": raw.strip() or "Sorry, I did not understand."},
        }
    intent = data.get("intent")
    if not isinstance(intent, str):
        return {"intent": "chat", "params": {"message": "Sorry, I did not understand."}}
    params = data.get("params")
    if not isinstance(params, dict):
        params = {}
    return {"intent": intent, "params": params}


async def propose(session: Session, user_prompt: str) -> ProposedAction:
    classified = await classify_intent(user_prompt)
    intent = classified["intent"]
    params: dict[str, Any] = classified.get("params") or {}

    if intent == "chat":
        return ProposedAction(
            intent="chat",
            params=params,
            description="",
            requires_confirmation=False,
            message=str(params.get("message", "")),
        )

    if intent == "search_now":
        query = str(params.get("query") or "").strip()
        if not query:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message="I could not figure out what to search for.",
            )
        return ProposedAction(
            intent="search_now",
            params={"query": query},
            description=f"Run a search for **{query}** across all your indexers.",
            preview={"query": query},
            requires_confirmation=False,
        )

    if intent == "add_to_watchlist":
        kind = params.get("kind") if params.get("kind") in ("series", "movie") else "series"
        title = str(params.get("title") or "").strip()
        if not title:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message="I need a title to add to the watchlist.",
            )
        year = params.get("year") if isinstance(params.get("year"), int) else None
        return ProposedAction(
            intent="add_to_watchlist",
            params={"kind": kind, "title": title, "year": year},
            description=f"Add **{title}** to your watchlist as a {kind}.",
            preview={"kind": kind, "title": title, "year": year},
        )

    if intent == "add_filter_task":
        valid_kinds = (
            "movie",
            "series",
            "game",
            "software",
            "audiobook",
            "comic",
            "music",
            "any",
        )
        kind = params.get("kind") if params.get("kind") in valid_kinds else "movie"
        year_min = params.get("year_min") if isinstance(params.get("year_min"), int) else None
        year_max = params.get("year_max") if isinstance(params.get("year_max"), int) else None
        quality = params.get("quality")
        if isinstance(quality, str):
            quality = quality.lower().strip() or None
        max_size_gb = (
            params.get("max_size_gb") if isinstance(params.get("max_size_gb"), int) else None
        )
        require_tokens_raw = params.get("require_tokens")
        require_tokens = (
            [str(t).lower() for t in require_tokens_raw if t]
            if isinstance(require_tokens_raw, list)
            else None
        )
        reject_tokens_raw = params.get("reject_tokens")
        reject_tokens = (
            [str(t).lower() for t in reject_tokens_raw if t]
            if isinstance(reject_tokens_raw, list)
            else None
        )
        preferred_proto = _parse_protocol(params.get("protocol"))

        # Feeds are required — this intent reads from the local RSS cache
        from sqlmodel import select as sql_select

        from trove.models.feed import FeedRow

        feeds = session.exec(sql_select(FeedRow).where(FeedRow.enabled == True)).all()  # noqa: E712
        if not feeds:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message=(
                    "Filter tasks read from your local RSS cache, but you have no RSS feeds "
                    "configured yet. Add at least one feed on the Feeds page first — that's "
                    "the source of releases this task will filter."
                ),
            )

        clients = _pick_default_clients(session, preferred_protocol=preferred_proto)
        warnings: list[str] = []
        if not clients:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message="Add a download client before creating a filter task.",
            )
        if preferred_proto is Protocol.TORRENT and not any(
            ClientType(c.type).protocol is Protocol.TORRENT for c in clients
        ):
            warnings.append(
                "You asked for torrent only but no torrent client is configured — "
                "using the usenet client instead."
            )
        if preferred_proto is Protocol.USENET and not any(
            ClientType(c.type).protocol is Protocol.USENET for c in clients
        ):
            warnings.append(
                "You asked for usenet only but no usenet client is configured — "
                "using the torrent client instead."
            )

        # Filter clients list if user explicitly asked for a single protocol
        if preferred_proto is not None:
            clients = [
                c for c in clients if ClientType(c.type).protocol is preferred_proto
            ] or clients

        # Which protocols to query in the rss_items input?
        active_protocols = sorted({ClientType(c.type).protocol.value for c in clients})

        # Build a readable task name
        parts = ["auto", kind if kind != "any" else "all"]
        if year_min and year_max:
            parts.append(f"{year_min}-{year_max}")
        elif year_min:
            parts.append(f"{year_min}plus")
        elif year_max:
            parts.append(f"upto{year_max}")
        if quality and quality != "any":
            parts.append(quality)
        if require_tokens:
            parts.extend(require_tokens[:2])  # cap to keep the name reasonable
        task_name = _slugify("-".join(parts))

        config_yaml = _build_filter_task_yaml(
            kind=kind,
            year_min=year_min,
            year_max=year_max,
            quality=quality,
            max_size_gb=max_size_gb,
            output_clients=[c.name for c in clients],
            protocols=active_protocols,
            require_tokens=require_tokens,
            reject_tokens=reject_tokens,
        )
        schedule = "15 * * * *"  # every hour at :15

        # Compose a human description
        kind_label = {
            "movie": "movies",
            "series": "TV episodes",
            "game": "games",
            "software": "software releases",
            "audiobook": "audiobooks",
            "comic": "comics",
            "music": "music releases",
            "any": "releases",
        }.get(kind, "releases")

        year_desc = ""
        if year_min and year_max:
            year_desc = f" from **{year_min}-{year_max}**"
        elif year_min:
            year_desc = f" from **{year_min} and newer**"
        elif year_max:
            year_desc = f" from **{year_max} or older**"
        quality_desc = f" in **{quality}**" if quality and quality != "any" else ""
        size_desc = f" under **{max_size_gb} GB**" if max_size_gb else ""
        keyword_desc = ""
        if require_tokens:
            keyword_desc = f" containing {', '.join(f'*{t}*' for t in require_tokens)}"

        client_names = ", ".join(f"**{c.name}**" for c in clients)
        protocol_label = f" ({'+'.join(active_protocols)})" if len(active_protocols) > 1 else ""
        description = (
            f"Create a standing task **{task_name}** that checks your RSS feeds every hour "
            f"for all {kind_label}{year_desc}{quality_desc}{size_desc}{keyword_desc} and sends "
            f"matches to {client_names}{protocol_label}. Already-seen releases are skipped."
        )

        if len(feeds) == 1:
            warnings.append(
                f"Only 1 RSS feed configured ({feeds[0].name}). Add more feeds for better coverage."
            )

        return ProposedAction(
            intent=intent,
            params={
                "task_name": task_name,
                "config_yaml": config_yaml,
                "schedule_cron": schedule,
                "kind": kind,
                "year_min": year_min,
                "year_max": year_max,
                "quality": quality,
                "max_size_gb": max_size_gb,
            },
            description=description,
            preview={
                "task_name": task_name,
                "schedule_cron": schedule,
                "config_yaml": config_yaml,
                "clients": [c.name for c in clients],
                "protocols": active_protocols,
            },
            warnings=warnings,
        )

    if intent in ("add_series", "add_movie"):
        title = str(params.get("title") or "").strip()
        if not title:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message="I need a title to do that.",
            )
        quality = params.get("quality")
        if isinstance(quality, str):
            quality = quality.lower().strip() or None
        year = params.get("year") if isinstance(params.get("year"), int) else None
        preferred_proto = _parse_protocol(params.get("protocol"))

        clients = _pick_default_clients(session, preferred_protocol=preferred_proto)
        warnings: list[str] = []
        if not clients:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message=(
                    f"I can set up auto-download for '{title}', but you haven't added any "
                    "download clients yet. Go to the Clients page first."
                ),
            )

        indexer_protocols = _enabled_indexer_protocols(session)
        if not indexer_protocols:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message=(
                    f"I can set up auto-download for '{title}', but you haven't added any "
                    "indexers yet. A task with no indexers can't search anywhere. "
                    "Add a Newznab/Torznab/UNIT3D indexer on the Indexers page first."
                ),
            )

        # Refuse up front if the user's protocol hint can't be served —
        # neither the client side nor the indexer side has a match.
        if preferred_proto is Protocol.TORRENT and not any(
            ClientType(c.type).protocol is Protocol.TORRENT for c in clients
        ):
            warnings.append(
                "You asked for torrent only but no torrent client is configured — "
                "using usenet instead."
            )
            preferred_proto = None
        elif preferred_proto is Protocol.USENET and not any(
            ClientType(c.type).protocol is Protocol.USENET for c in clients
        ):
            warnings.append(
                "You asked for usenet only but no usenet client is configured — "
                "using torrent instead."
            )
            preferred_proto = None
        elif preferred_proto is not None:
            clients = [
                c for c in clients if ClientType(c.type).protocol is preferred_proto
            ] or clients

        # Indexer protocol sanity check — the user might have the right
        # *client* but no indexer that speaks the same protocol, in which
        # case the task would never find anything useful.
        if preferred_proto is Protocol.TORRENT and Protocol.TORRENT not in indexer_protocols:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message=(
                    f"You asked for '{title}' via torrent, but all your enabled indexers are "
                    "usenet (NZB). A torrent task needs a torrent-capable indexer — add one "
                    "on the Indexers page (UNIT3D, Torznab, or Cardigann) and try again."
                ),
            )
        if preferred_proto is Protocol.USENET and Protocol.USENET not in indexer_protocols:
            return ProposedAction(
                intent="chat",
                params={},
                description="",
                requires_confirmation=False,
                message=(
                    f"You asked for '{title}' via usenet, but all your enabled indexers are "
                    "torrent. A usenet task needs a Newznab-speaking indexer — add one on "
                    "the Indexers page and try again."
                ),
            )

        output_names = [c.name for c in clients]
        active_protocols = sorted({ClientType(c.type).protocol.value for c in clients})
        protocol_label = f" ({'+'.join(active_protocols)})" if len(active_protocols) > 1 else ""
        client_names = ", ".join(f"**{c.name}**" for c in clients)

        if intent == "add_series":
            task_name = _slugify(title)
            config_yaml = _build_series_task_yaml(
                title, quality, output_names, protocol=preferred_proto
            )
            schedule = "0 * * * *"  # hourly
            desc_quality = f" in **{quality}**" if quality and quality != "any" else ""
            description = (
                f"Create a task **{task_name}** that searches hourly for new **{title}** "
                f"episodes{desc_quality} across all your indexers and sends matches to "
                f"{client_names}{protocol_label}. Already-seen releases are skipped."
            )
            probe_category = Category.TV
            probe_query = title
        else:
            task_name = _slugify(f"{title}-{year}" if year else title)
            config_yaml = _build_movie_task_yaml(
                title, year, quality, output_names, protocol=preferred_proto
            )
            schedule = "0 */2 * * *"  # every 2 hours
            desc_quality = f" in **{quality}**" if quality and quality != "any" else ""
            year_text = f" ({year})" if year else ""
            description = (
                f"Create a task **{task_name}** that searches every 2 hours for "
                f"**{title}**{year_text}{desc_quality} across all your indexers and sends "
                f"the best match to {client_names}{protocol_label}. The task stops after "
                f"the movie is downloaded."
            )
            probe_category = Category.MOVIES
            probe_query = f"{title} {year}" if year else title

        # Probe the indexers now so the user sees "I found N hits" before
        # committing. Cheap — limit=5, 10s timeout per indexer.
        probe_count, probe_sample = await _probe_indexers(
            session,
            probe_query,
            category=probe_category,
            protocol=preferred_proto,
        )
        if probe_count > 0:
            sample_note = (
                f" Best guess from a quick probe: *{probe_sample}*." if probe_sample else ""
            )
            description += (
                f"\n\n**Quick probe**: found **{probe_count} hit{'s' if probe_count != 1 else ''}** "
                f"matching your query across your enabled indexers.{sample_note}"
            )
        else:
            description += (
                "\n\n**Quick probe**: **0 hits** right now — none of your enabled indexers "
                "returned anything matching this query. The release may not be out yet, or "
                "your indexers may not carry it. You can still create the task; it'll start "
                "grabbing the moment something lands."
            )

        return ProposedAction(
            intent=intent,
            params={
                "title": title,
                "quality": quality,
                "year": year,
                "task_name": task_name,
                "config_yaml": config_yaml,
                "schedule_cron": schedule,
            },
            description=description,
            preview={
                "task_name": task_name,
                "schedule_cron": schedule,
                "config_yaml": config_yaml,
                "clients": output_names,
                "protocols": active_protocols,
            },
            warnings=warnings,
        )

    if intent == "bulk_tmdb":
        return await _propose_bulk_tmdb(session, params)

    return ProposedAction(
        intent="chat",
        params={},
        description="",
        requires_confirmation=False,
        message=f"Sorry, I don't know how to handle intent '{intent}' yet.",
    )


async def _propose_bulk_tmdb(session: Session, params: dict[str, Any]) -> ProposedAction:
    """Query TMDB discover and return a preview of movies/TV to bulk-add."""
    from datetime import date

    from trove.services import tmdb

    if not tmdb.is_configured():
        return ProposedAction(
            intent="chat",
            params={},
            description="",
            requires_confirmation=False,
            message=(
                "Bulk-add from TMDB needs a TMDB API token. Add one in **Settings → TMDB** first."
            ),
        )

    kind = params.get("kind") if params.get("kind") in ("movie", "tv") else "movie"
    rating_min = params.get("rating_min")
    if isinstance(rating_min, int):
        rating_min = float(rating_min)
    if not isinstance(rating_min, float):
        rating_min = None

    date_from_raw = params.get("date_from")
    date_from: str | None = None
    if isinstance(date_from_raw, str):
        if date_from_raw.lower() == "today":
            date_from = date.today().isoformat()
        elif len(date_from_raw) == 10:
            date_from = date_from_raw

    date_to_raw = params.get("date_to")
    date_to: str | None = None
    if isinstance(date_to_raw, str) and len(date_to_raw) == 10:
        date_to = date_to_raw

    year_min = params.get("year_min") if isinstance(params.get("year_min"), int) else None
    year_max = params.get("year_max") if isinstance(params.get("year_max"), int) else None
    if year_min and not date_from:
        date_from = f"{year_min}-01-01"
    if year_max and not date_to:
        date_to = f"{year_max}-12-31"

    quality = params.get("quality")
    if isinstance(quality, str):
        quality = quality.lower().strip() or None
    if quality == "best":
        quality = "2160p"

    limit = params.get("limit") if isinstance(params.get("limit"), int) else 50
    limit = max(1, min(100, limit))

    # Check watchlist is set up (needs clients)
    clients = _pick_default_clients(session)
    if not clients:
        return ProposedAction(
            intent="chat",
            params={},
            description="",
            requires_confirmation=False,
            message="Add a download client before bulk-adding movies.",
        )

    # Query TMDB discover
    try:
        items = await _tmdb_discover(
            kind=kind,
            rating_min=rating_min,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )
    except tmdb.TmdbError as e:
        return ProposedAction(
            intent="chat",
            params={},
            description="",
            requires_confirmation=False,
            message=f"TMDB query failed: {e}",
        )

    # Filter out items already on the watchlist
    from trove.models.watchlist import WatchlistItemRow

    existing_ids = {
        w.tmdb_id for w in session.exec(select(WatchlistItemRow)).all() if w.tmdb_id is not None
    }
    new_items = [i for i in items if i["tmdb_id"] not in existing_ids]

    if not new_items:
        return ProposedAction(
            intent="chat",
            params={},
            description="",
            requires_confirmation=False,
            message=(
                f"Found {len(items)} matching {kind}s on TMDB, but all of them are "
                "already on your watchlist."
            ),
        )

    # Build description
    criteria: list[str] = []
    if rating_min is not None:
        criteria.append(f"rating ≥ {rating_min}")
    if date_from:
        criteria.append(f"released from {date_from}")
    if date_to:
        criteria.append(f"until {date_to}")
    if quality:
        criteria.append(f"quality {quality}")
    criteria_text = ", ".join(criteria) if criteria else "no filters"

    kind_label = "movies" if kind == "movie" else "TV shows"
    sample = ", ".join(i["title"] for i in new_items[:5])
    if len(new_items) > 5:
        sample += f", and {len(new_items) - 5} more"

    return ProposedAction(
        intent="bulk_tmdb",
        params={
            "kind": kind,
            "quality": quality,
            "items": new_items,
        },
        description=(
            f"Add **{len(new_items)}** {kind_label} from TMDB ({criteria_text}) "
            f"to your watchlist and create download tasks for each.\n\n"
            f"**Preview:** {sample}"
        ),
        preview={
            "kind": kind,
            "count": len(new_items),
            "quality": quality,
            "sample_titles": [i["title"] for i in new_items[:10]],
        },
    )


async def _tmdb_discover(
    kind: str,
    rating_min: float | None,
    date_from: str | None,
    date_to: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Query TMDB /discover with filters. Returns a list of item dicts."""
    from datetime import date, timedelta

    from trove.services import tmdb

    endpoint = "/discover/movie" if kind == "movie" else "/discover/tv"
    params: dict[str, Any] = {
        "sort_by": "popularity.desc",
        "include_adult": "false",
    }

    # If filtering by rating, we need movies that have actually been rated.
    # Brand-new releases have no votes yet, so a date_from of "today" would
    # return nothing. Expand the range backwards by 180 days so recent
    # well-rated releases come through too.
    effective_date_from = date_from
    if rating_min is not None and date_from:
        try:
            parsed = date.fromisoformat(date_from)
            if parsed >= date.today() - timedelta(days=30):
                effective_date_from = (parsed - timedelta(days=180)).isoformat()
        except ValueError:
            pass

    if kind == "movie":
        if effective_date_from:
            params["primary_release_date.gte"] = effective_date_from
        if date_to:
            params["primary_release_date.lte"] = date_to
    else:
        if effective_date_from:
            params["first_air_date.gte"] = effective_date_from
        if date_to:
            params["first_air_date.lte"] = date_to
    if rating_min is not None:
        params["vote_average.gte"] = rating_min
        params["vote_count.gte"] = 20  # prevent tiny-sample-size 10/10s

    results: list[dict[str, Any]] = []
    pages_needed = max(1, (limit + 19) // 20)
    for page in range(1, pages_needed + 1):
        data = await tmdb._request(endpoint, {**params, "page": page})
        for r in data.get("results") or []:
            tid = int(r.get("id") or 0)
            if tid == 0:
                continue
            title = r.get("title") if kind == "movie" else r.get("name")
            if not title:
                continue
            release_date = r.get("release_date") if kind == "movie" else r.get("first_air_date")
            import contextlib as _ctx

            year: int | None = None
            if release_date and len(release_date) >= 4:
                with _ctx.suppress(ValueError):
                    year = int(release_date[:4])
            poster = r.get("poster_path")
            backdrop = r.get("backdrop_path")
            results.append(
                {
                    "tmdb_id": tid,
                    "title": title,
                    "year": year,
                    "overview": (r.get("overview") or "")[:500] or None,
                    "rating": r.get("vote_average"),
                    "release_date": release_date,
                    "poster_path": f"https://image.tmdb.org/t/p/w342{poster}" if poster else None,
                    "backdrop_path": f"https://image.tmdb.org/t/p/w1280{backdrop}"
                    if backdrop
                    else None,
                }
            )
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
        if page >= int(data.get("total_pages", 1)):
            break
    return results[:limit]
