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

6. chat — user is asking a general question, small talk, or something unsupported.
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
) -> str:
    require: list[str] = []
    if quality and quality != "any":
        require.append(quality)
    reject = ["cam", "telesync", "hdcam", "workprint"]
    config: dict[str, Any] = {
        "inputs": [
            {
                "kind": "search",
                "query": title,
                "categories": ["tv"],
            }
        ],
        "filters": {
            "min_seeders": 2,
            "reject": reject,
        },
        "outputs": list(output_clients),
    }
    if require:
        config["filters"]["require"] = require
    return yaml.safe_dump(config, sort_keys=False)


def _build_movie_task_yaml(
    title: str,
    year: int | None,
    quality: str | None,
    output_clients: list[str],
) -> str:
    query = f"{title} {year}" if year else title
    require: list[str] = []
    if quality and quality != "any":
        require.append(quality)
    config: dict[str, Any] = {
        "inputs": [
            {
                "kind": "search",
                "query": query,
                "categories": ["movies"],
            }
        ],
        "filters": {
            "min_seeders": 5,
            "reject": ["cam", "telesync", "hdcam", "workprint", "hdts"],
        },
        "outputs": list(output_clients),
    }
    if require:
        config["filters"]["require"] = require
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

        # Filter clients list if user explicitly asked for a single protocol
        if preferred_proto is Protocol.TORRENT and not any(
            ClientType(c.type).protocol is Protocol.TORRENT for c in clients
        ):
            warnings.append(
                "You asked for torrent only but no torrent client is configured — "
                "using usenet instead."
            )
        elif preferred_proto is Protocol.USENET and not any(
            ClientType(c.type).protocol is Protocol.USENET for c in clients
        ):
            warnings.append(
                "You asked for usenet only but no usenet client is configured — "
                "using torrent instead."
            )
        elif preferred_proto is not None:
            clients = [
                c for c in clients if ClientType(c.type).protocol is preferred_proto
            ] or clients

        output_names = [c.name for c in clients]
        active_protocols = sorted({ClientType(c.type).protocol.value for c in clients})
        protocol_label = f" ({'+'.join(active_protocols)})" if len(active_protocols) > 1 else ""
        client_names = ", ".join(f"**{c.name}**" for c in clients)

        if intent == "add_series":
            task_name = _slugify(title)
            config_yaml = _build_series_task_yaml(title, quality, output_names)
            schedule = "0 * * * *"  # hourly
            desc_quality = f" in **{quality}**" if quality and quality != "any" else ""
            description = (
                f"Create a task **{task_name}** that searches hourly for new **{title}** "
                f"episodes{desc_quality} across all your indexers and sends matches to "
                f"{client_names}{protocol_label}. Already-seen releases are skipped."
            )
        else:
            task_name = _slugify(f"{title}-{year}" if year else title)
            config_yaml = _build_movie_task_yaml(title, year, quality, output_names)
            schedule = "0 */2 * * *"  # every 2 hours
            desc_quality = f" in **{quality}**" if quality and quality != "any" else ""
            year_text = f" ({year})" if year else ""
            description = (
                f"Create a task **{task_name}** that searches every 2 hours for "
                f"**{title}**{year_text}{desc_quality} across all your indexers and sends "
                f"the best match to {client_names}{protocol_label}. The task stops after "
                f"the movie is downloaded."
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

    return ProposedAction(
        intent="chat",
        params={},
        description="",
        requires_confirmation=False,
        message=f"Sorry, I don't know how to handle intent '{intent}' yet.",
    )
