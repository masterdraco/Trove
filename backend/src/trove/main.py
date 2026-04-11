from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trove import __version__
from trove.api import ai as ai_router
from trove.api import app_settings as app_settings_router
from trove.api import auth as auth_router
from trove.api import clients as clients_router
from trove.api import docs as docs_router
from trove.api import feeds as feeds_router
from trove.api import health as health_router
from trove.api import indexers as indexers_router
from trove.api import search as search_router
from trove.api import tasks as tasks_router
from trove.api import torznab as torznab_router
from trove.api import watchlist as watchlist_router
from trove.config import get_settings
from trove.db import init_db
from trove.logging_setup import configure_logging
from trove.services import scheduler as scheduler_service

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    log.info("trove.starting", version=__version__, config_dir=str(settings.config_dir))
    init_db()
    try:
        scheduler_service.start_scheduler()
    except Exception as e:  # pragma: no cover
        log.warning("scheduler.start_failed", error=str(e))
    yield
    scheduler_service.stop_scheduler()
    log.info("trove.stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Trove",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/swagger",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router.router, prefix="/api")
    app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
    app.include_router(clients_router.router, prefix="/api/clients", tags=["clients"])
    app.include_router(indexers_router.router, prefix="/api/indexers", tags=["indexers"])
    app.include_router(search_router.router, prefix="/api/search", tags=["search"])
    app.include_router(tasks_router.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(ai_router.router, prefix="/api/ai", tags=["ai"])
    app.include_router(watchlist_router.router, prefix="/api/watchlist", tags=["watchlist"])
    app.include_router(feeds_router.router, prefix="/api/feeds", tags=["feeds"])
    app.include_router(docs_router.router, prefix="/api/docs", tags=["docs"])
    app.include_router(
        app_settings_router.router, prefix="/api/settings", tags=["settings"]
    )
    app.include_router(torznab_router.router, prefix="/torznab", tags=["torznab"])

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        # Mount static assets (hashed JS/CSS) under /_app so they keep their cache headers.
        app_dir = static_dir / "_app"
        if app_dir.exists():
            app.mount("/_app", StaticFiles(directory=str(app_dir)), name="spa_assets")

        index_html = static_dir / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        async def spa_fallback(request: Request, full_path: str) -> FileResponse | JSONResponse:
            # API and torznab paths are handled by their routers — never return the SPA shell.
            if full_path.startswith(("api/", "torznab/")):
                return JSONResponse({"detail": "not_found"}, status_code=404)
            # Serve any real file that exists (favicons, robots.txt, etc.).
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            # Otherwise fall back to the SPA shell so the client-side router can handle it.
            return FileResponse(index_html)
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "Trove",
                    "version": __version__,
                    "message": "Web UI not built yet. Run 'pnpm build' in web/.",
                }
            )

    return app


app = create_app()
