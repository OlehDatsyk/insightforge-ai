"""
api.py
======
All REST API endpoints (section 23), grouped under a single ``APIRouter``
mounted at ``/api`` by ``app.py``. Endpoints stay thin - they validate input,
talk to the database and the provider router, and translate internal
exceptions into safe, user-friendly HTTP errors. Business logic lives in
``research_agent.py`` / ``planner.py`` / ``report_generator.py`` etc.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from config import Settings, get_settings
from database import get_db
from models import AppSetting, ProviderUsage, ResearchSession, ResearchTask, Source
from provider_router import get_router
from report_generator import EXPORTERS
from research_agent import run_research_session
from schemas import (
    ExportFormat,
    ProviderStatus,
    ReportOut,
    ResearchRequest,
    ResearchSessionDetail,
    ResearchSessionOut,
    SourceOut,
    TaskOut,
)

logger = logging.getLogger("insightforge.api")
router = APIRouter(prefix="/api", tags=["insightforge"])

MODE_PRESETS = {
    "quick": {"max_sources": 4, "max_tasks": 3},
    "standard": {"max_sources": 8, "max_tasks": 5},
    "deep": {"max_sources": 15, "max_tasks": 8},
}


def _content_type(fmt: str) -> str:
    return {
        "markdown": "text/markdown",
        "html": "text/html",
        "txt": "text/plain",
        "json": "application/json",
        "pdf": "application/pdf",
    }[fmt]


# ----------------------------------------------------------------------------
# Research sessions
# ----------------------------------------------------------------------------
@router.post("/research", response_model=ResearchSessionOut, status_code=201)
def create_research(payload: ResearchRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.configured_providers:
        raise HTTPException(
            status_code=503,
            detail="No AI provider is configured on this server. Add at least one API key to get started.",
        )

    if payload.mode == "custom":
        max_sources = min(payload.max_sources or 6, settings.max_sources)
        max_tasks = min(payload.max_tasks or 5, settings.max_research_tasks)
    else:
        preset = MODE_PRESETS[payload.mode]
        max_sources = min(preset["max_sources"], settings.max_sources)
        max_tasks = min(preset["max_tasks"], settings.max_research_tasks)

    session = ResearchSession(
        research_question=payload.research_question,
        mode=payload.mode,
        status="pending",
        current_stage="pending",
        max_sources=max_sources,
        max_tasks=max_tasks,
        progress_log=[],
    )
    session.add_progress("Research session created", stage="pending")
    db.add(session)
    db.commit()
    db.refresh(session)

    background_tasks.add_task(run_research_session, session.id)

    return session


@router.get("/research", response_model=list[ResearchSessionOut])
def list_research(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 200))
    sessions = (
        db.query(ResearchSession)
        .order_by(ResearchSession.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return sessions


@router.get("/research/{session_id}", response_model=ResearchSessionDetail)
def get_research(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ResearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found.")
    return session


@router.delete("/research/{session_id}", status_code=204)
def delete_research(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ResearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found.")
    db.delete(session)
    db.commit()
    return Response(status_code=204)


@router.get("/research/{session_id}/stream")
async def stream_research_progress(session_id: str, db: Session = Depends(get_db)):
    """Server-Sent Events endpoint for live progress updates (section 18)."""
    session = db.get(ResearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found.")

    async def event_generator():
        from database import session_scope

        last_len = 0
        max_wait_seconds = 900  # hard cap so a stalled connection can't hang forever
        waited = 0.0
        while waited < max_wait_seconds:
            with session_scope() as s:
                current = s.get(ResearchSession, session_id)
                if current is None:
                    break
                payload = {
                    "status": current.status,
                    "stage": current.current_stage,
                    "progress_percent": current.progress_percent,
                    "error_message": current.error_message,
                    "log": current.progress_log[last_len:],
                }
                last_len = len(current.progress_log)
                terminal = current.status in ("completed", "failed")
            yield f"data: {json.dumps(payload)}\n\n"
            if terminal:
                break
            await asyncio.sleep(1.2)
            waited += 1.2

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------
@router.post("/research/{session_id}/export")
def export_report(session_id: str, payload: ExportFormat, db: Session = Depends(get_db)):
    session = db.get(ResearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found.")
    if not session.report:
        raise HTTPException(status_code=409, detail="This research session does not have a completed report yet.")

    from schemas import ConflictItem, FinalReport, SourceCandidate

    report_model = FinalReport(
        title=session.report.title,
        executive_summary=session.report.executive_summary,
        research_question=session.research_question,
        methodology=session.report.methodology,
        key_findings=session.report.key_findings,
        detailed_analysis=session.report.detailed_analysis,
        comparison=session.report.comparison,
        conflicting_information=[ConflictItem.model_validate(c) for c in session.report.conflicts],
        limitations=session.report.limitations,
        conclusion=session.report.conclusion,
        sources=[SourceCandidate.model_validate(s) for s in session.report.sources_json],
    )

    exporter = EXPORTERS[payload.format]
    content = exporter(report_model)
    body = content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8")
    filename = f"insightforge-report-{session_id[:8]}.{('md' if payload.format == 'markdown' else payload.format)}"
    return Response(
        content=body,
        media_type=_content_type(payload.format),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------------
# Providers / health / config
# ----------------------------------------------------------------------------
@router.get("/providers", response_model=list[ProviderStatus])
def get_providers():
    return get_router().provider_status()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness/readiness check. Never makes an outbound AI API call - it only
    checks whether each provider has a configured API key (section 24)."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False

    settings = get_settings()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "providers": {p["name"]: p["configured"] for p in get_router().provider_status()},
        "configured_provider_count": len(settings.configured_providers),
    }


@router.get("/config/status")
def config_status(settings: Settings = Depends(get_settings)):
    return {
        "app_env": settings.app_env,
        "search_backend": settings.search_backend,
        "limits": {
            "max_agent_iterations": settings.max_agent_iterations,
            "max_tool_calls": settings.max_tool_calls,
            "max_sources": settings.max_sources,
            "max_research_tasks": settings.max_research_tasks,
            "request_timeout_seconds": settings.request_timeout_seconds,
            "max_provider_retries": settings.max_provider_retries,
            "provider_fallback_limit": settings.provider_fallback_limit,
        },
        "fallback_chain": settings.fallback_chain,
        "configured_providers": settings.configured_providers,
    }


# ----------------------------------------------------------------------------
# Settings / provider routing (section 25) - routing preferences only, NEVER API keys
# ----------------------------------------------------------------------------
ALLOWED_ROUTING_KEYS = {"primary", "fallback", "secondary_fallback", "planning", "analysis", "crosscheck", "synthesis"}


@router.get("/settings/routing")
def get_routing_settings():
    router_ = get_router()
    settings = get_settings()
    overrides = router_.get_routing_overrides()
    return {
        "primary": overrides.get("primary", settings.primary_ai_provider),
        "fallback": overrides.get("fallback", settings.fallback_ai_provider),
        "secondary_fallback": overrides.get("secondary_fallback", settings.secondary_fallback_ai_provider),
        "planning": overrides.get("planning", settings.planning_provider),
        "analysis": overrides.get("analysis", settings.analysis_provider),
        "crosscheck": overrides.get("crosscheck", settings.crosscheck_provider),
        "synthesis": overrides.get("synthesis", settings.synthesis_provider),
        "configured_providers": settings.configured_providers,
    }


@router.post("/settings/routing")
def update_routing_settings(payload: dict[str, str], db: Session = Depends(get_db)):
    invalid_keys = set(payload.keys()) - ALLOWED_ROUTING_KEYS
    if invalid_keys:
        raise HTTPException(status_code=400, detail=f"Unsupported setting(s): {', '.join(invalid_keys)}")

    valid_providers = {"openai", "anthropic", "gemini", "auto"}
    for key, value in payload.items():
        if value not in valid_providers:
            raise HTTPException(status_code=400, detail=f"Invalid provider '{value}' for '{key}'.")

    router_ = get_router()
    merged = router_.get_routing_overrides()
    merged.update(payload)
    router_.load_routing_overrides(merged)

    for key, value in merged.items():
        setting_key = f"routing.{key}"
        row = db.get(AppSetting, setting_key)
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=setting_key, value=value))
    db.commit()

    return {"status": "updated", "routing": router_.get_routing_overrides()}


# ----------------------------------------------------------------------------
# Provider usage (used by the dashboard)
# ----------------------------------------------------------------------------
@router.get("/research/{session_id}/usage")
def get_provider_usage(session_id: str, db: Session = Depends(get_db)):
    session = db.get(ResearchSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found.")
    rows = db.query(ProviderUsage).filter(ProviderUsage.session_id == session_id).all()
    return [
        {
            "stage": r.stage,
            "provider": r.provider,
            "model": r.model,
            "success": r.success,
            "was_fallback": r.was_fallback,
            "duration_ms": r.duration_ms,
            "error_type": r.error_type,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
