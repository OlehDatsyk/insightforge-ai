"""
app.py
======
FastAPI application entry point.

Responsibilities kept deliberately narrow (section 32 - clean separation of
concerns): wiring middleware, mounting the API router, serving the Jinja2
frontend pages, and translating uncaught exceptions into safe responses.
All business logic lives in the agent/provider/tool/service modules this
file imports.

Run locally:
    uvicorn app:app --reload --port 8000

Run in production (Render/Railway inject $PORT):
    uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from api import router as api_router
from config import get_settings
from database import init_db, session_scope
from logging_config import configure_logging
from models import AppSetting
from provider_router import get_router
from rate_limiter import RateLimitMiddleware

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("insightforge.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(
        "InsightForge AI starting | env=%s | configured_providers=%s",
        settings.app_env,
        settings.configured_providers or "none",
    )
    # Load any previously-saved provider routing overrides (section 25).
    try:
        with session_scope() as db:
            rows = db.query(AppSetting).filter(AppSetting.key.like("routing.%")).all()
            overrides = {row.key.removeprefix("routing."): row.value for row in rows}
        if overrides:
            get_router().load_routing_overrides(overrides)
            logger.info("loaded %d saved routing override(s)", len(overrides))
    except Exception:  # noqa: BLE001
        logger.exception("failed to load routing overrides at startup")
    yield


app = FastAPI(
    title="InsightForge AI",
    description="An agentic, multi-model AI research platform.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose declared body exceeds MAX_REQUEST_BODY_BYTES (section 28)."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_body_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large."})
        return await call_next(request)


app.add_middleware(BodySizeLimitMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(api_router)


# ----------------------------------------------------------------------------
# Global exception handling - never leak internals to the client (section 30)
# ----------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled exception on %s %s", request.method, request.url.path)
    # In production, never leak exception details to the client (section 30/28).
    # Locally/in development, surfacing the exception type + message directly in
    # the response makes the app self-debuggable without needing to find and
    # copy text from a separate server console window.
    if settings.app_env == "production":
        detail = "An unexpected server error occurred."
    else:
        detail = f"An unexpected server error occurred: {type(exc).__name__}: {exc}"
    return JSONResponse(status_code=500, content={"detail": detail})


# ----------------------------------------------------------------------------
# Frontend pages (server-rendered shells; all data loads via /api/* from JS)
# ----------------------------------------------------------------------------
@app.get("/")
def landing_page(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/research/new")
def new_research_page(request: Request):
    return templates.TemplateResponse(request, "new_research.html")


@app.get("/research/{session_id}/progress")
def research_progress_page(request: Request, session_id: str):
    return templates.TemplateResponse(request, "progress.html", {"session_id": session_id})


@app.get("/research/{session_id}")
def research_results_page(request: Request, session_id: str):
    return templates.TemplateResponse(request, "results.html", {"session_id": session_id})


@app.get("/history")
def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html")


@app.get("/reports")
def reports_page(request: Request):
    return templates.TemplateResponse(request, "reports.html")


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html")


@app.get("/about")
def about_page(request: Request):
    return templates.TemplateResponse(request, "about.html")
