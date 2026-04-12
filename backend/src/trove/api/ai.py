from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from trove.ai import agent as ai_agent
from trove.ai import client as ai_client
from trove.api.deps import current_user, db_session
from trove.models.task import TaskRow
from trove.models.user import User
from trove.models.watchlist import WatchlistItemRow
from trove.services import scheduler

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    system: str | None = None
    temperature: float = 0.3


class ChatResponse(BaseModel):
    response: str


class AiStatus(BaseModel):
    enabled: bool
    endpoint: str
    model: str


class OllamaModel(BaseModel):
    name: str
    size: int | None = None
    parameter_size: str | None = None
    family: str | None = None


@router.get("/status", response_model=AiStatus)
async def status_endpoint(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> AiStatus:
    cfg = ai_client.get_effective_config(session)
    return AiStatus(enabled=cfg.enabled, endpoint=cfg.endpoint, model=cfg.model)


@router.get("/models", response_model=list[OllamaModel])
async def list_models(
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> list[OllamaModel]:
    cfg = ai_client.get_effective_config(session)
    url = cfg.endpoint.rstrip("/") + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"failed to fetch models from {cfg.endpoint}: {e}",
        ) from e

    models: list[OllamaModel] = []
    for m in data.get("models") or []:
        name = m.get("name") or m.get("model") or ""
        if not name:
            continue
        details = m.get("details") or {}
        models.append(
            OllamaModel(
                name=name,
                size=m.get("size"),
                parameter_size=details.get("parameter_size"),
                family=details.get("family"),
            )
        )
    return models


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    _user: User = Depends(current_user),
) -> ChatResponse:
    try:
        response = await ai_client.complete(
            payload.prompt,
            system=payload.system,
            temperature=payload.temperature,
            cache=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ai request failed: {e}",
        ) from e
    return ChatResponse(response=response)


class AgentProposeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class AgentProposal(BaseModel):
    intent: str
    description: str
    preview: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = True
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AgentExecuteRequest(BaseModel):
    intent: str
    params: dict[str, Any]


class AgentExecuteResponse(BaseModel):
    ok: bool
    kind: str
    resource_id: int | None = None
    message: str


@router.post("/agent/propose", response_model=AgentProposal)
async def agent_propose(
    payload: AgentProposeRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> AgentProposal:
    try:
        proposal = await ai_agent.propose(session, payload.prompt)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ai request failed: {e}",
        ) from e
    return AgentProposal(
        intent=proposal.intent,
        description=proposal.description,
        preview=proposal.preview,
        params=proposal.params,
        requires_confirmation=proposal.requires_confirmation,
        message=proposal.message,
        warnings=proposal.warnings,
    )


@router.post("/agent/execute", response_model=AgentExecuteResponse)
async def agent_execute(
    payload: AgentExecuteRequest,
    session: Session = Depends(db_session),
    _user: User = Depends(current_user),
) -> AgentExecuteResponse:
    intent = payload.intent
    params = payload.params

    if intent in ("add_series", "add_movie", "add_filter_task"):
        task_name = params.get("task_name")
        config_yaml = params.get("config_yaml")
        schedule_cron = params.get("schedule_cron")
        if not task_name or not config_yaml:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="missing task_name or config_yaml",
            )
        # Deduplicate: if a task with this name already exists, update it.
        existing = session.exec(select(TaskRow).where(TaskRow.name == task_name)).first()
        if existing is not None:
            existing.config_yaml = config_yaml
            existing.schedule_cron = schedule_cron
            existing.enabled = True
            session.add(existing)
            session.commit()
            session.refresh(existing)
            scheduler.schedule_task(existing)
            # Re-run the task immediately so filter changes take effect
            # without waiting for the next cron fire.
            assert existing.id is not None
            scheduler.schedule_run_now(existing.id)
            return AgentExecuteResponse(
                ok=True,
                kind="task",
                resource_id=existing.id,
                message=f"Updated existing task '{task_name}' — running now",
            )
        row = TaskRow(
            name=task_name,
            enabled=True,
            schedule_cron=schedule_cron,
            config_yaml=config_yaml,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        scheduler.schedule_task(row)
        # Fire the task once immediately so the user sees results without
        # waiting for the first cron interval (up to 2 hours for movies).
        assert row.id is not None
        scheduler.schedule_run_now(row.id)
        return AgentExecuteResponse(
            ok=True,
            kind="task",
            resource_id=row.id,
            message=f"Created task '{task_name}' — running now",
        )

    if intent == "add_to_watchlist":
        kind = params.get("kind", "series")
        title = params.get("title")
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="missing title",
            )
        year = params.get("year") if isinstance(params.get("year"), int) else None
        row = WatchlistItemRow(kind=kind, title=title, year=year)
        session.add(row)
        session.commit()
        session.refresh(row)
        return AgentExecuteResponse(
            ok=True,
            kind="watchlist",
            resource_id=row.id,
            message=f"Added '{title}' to watchlist",
        )

    if intent == "search_now":
        return AgentExecuteResponse(
            ok=True,
            kind="search",
            resource_id=None,
            message="Open the Search page with this query",
        )

    if intent == "bulk_tmdb":
        from trove.ai import agent as ai_agent

        kind = params.get("kind", "movie")
        quality = params.get("quality")
        items = params.get("items") or []
        if not isinstance(items, list) or not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="missing items",
            )
        clients = ai_agent._pick_default_clients(session)
        if not clients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="no_clients_configured",
            )
        output_names = [c.name for c in clients]

        added = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            tmdb_id = it.get("tmdb_id")
            title = it.get("title")
            if not tmdb_id or not title:
                continue
            # Skip if already on watchlist
            exists = session.exec(
                select(WatchlistItemRow).where(WatchlistItemRow.tmdb_id == tmdb_id)
            ).first()
            if exists is not None:
                continue
            wl = WatchlistItemRow(
                kind="movie" if kind == "movie" else "series",
                title=title,
                year=it.get("year"),
                target_quality=quality,
                tmdb_id=tmdb_id,
                tmdb_type=kind,
                poster_path=it.get("poster_path"),
                backdrop_path=it.get("backdrop_path"),
                overview=it.get("overview"),
                release_date=it.get("release_date"),
                rating=it.get("rating"),
                discovery_status="pending",
            )
            session.add(wl)
            session.commit()
            session.refresh(wl)

            # Auto-promote: create the download task
            if wl.kind == "series":
                task_name = ai_agent._slugify(wl.title)
                config_yaml = ai_agent._build_series_task_yaml(
                    wl.title,
                    wl.target_quality,
                    output_names,
                    tmdb_id=wl.tmdb_id,
                )
                schedule_cron = "0 * * * *"
            else:
                slug_parts = [wl.title]
                if wl.year:
                    slug_parts.append(str(wl.year))
                task_name = ai_agent._slugify("-".join(slug_parts))
                config_yaml = ai_agent._build_movie_task_yaml(
                    wl.title,
                    wl.year,
                    wl.target_quality,
                    output_names,
                    tmdb_id=wl.tmdb_id,
                )
                schedule_cron = "0 */2 * * *"

            existing_task = session.exec(select(TaskRow).where(TaskRow.name == task_name)).first()
            if existing_task is not None:
                task = existing_task
                task.config_yaml = config_yaml
                task.schedule_cron = schedule_cron
                task.enabled = True
            else:
                task = TaskRow(
                    name=task_name,
                    enabled=True,
                    schedule_cron=schedule_cron,
                    config_yaml=config_yaml,
                )
                session.add(task)
            session.commit()
            session.refresh(task)
            wl.discovery_task_id = task.id
            wl.discovery_status = "promoted"
            session.add(wl)
            session.commit()
            scheduler.schedule_task(task)
            added += 1

        return AgentExecuteResponse(
            ok=True,
            kind="bulk_tmdb",
            resource_id=None,
            message=f"Added {added} {kind}s to watchlist and created download tasks",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"cannot execute intent '{intent}'",
    )


@router.post("/test", response_model=ChatResponse)
async def test_endpoint(_user: User = Depends(current_user)) -> ChatResponse:
    try:
        response = await ai_client.complete(
            "Reply with exactly the word: pong",
            system="You are a health check. Reply with a single word.",
            temperature=0.0,
            cache=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ai unreachable: {e}",
        ) from e
    return ChatResponse(response=response)
