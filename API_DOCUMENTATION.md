# API_DOCUMENTATION.md

Full reference for InsightForge AI's REST API. All endpoints are prefixed with `/api`.
Interactive, always-up-to-date docs are also available at `/api/docs` (Swagger UI) and
`/api/redoc` when the app is running.

All error responses follow the shape `{"detail": "human-readable message"}`. Internal error
details (stack traces, provider responses, raw exceptions) are never included - see
`app.py`'s global exception handler and `provider_router.py`'s `AllProvidersFailedError`.

---

## POST /api/research

Start a new research session. Returns immediately with a `pending` session; the agent runs
in a background task.

**Request body:**
```json
{
  "research_question": "Compare the best AI coding assistants for developers in 2026",
  "mode": "standard",
  "max_sources": null,
  "max_tasks": null
}
```
- `research_question` - string, 5-2000 characters, required.
- `mode` - one of `quick` | `standard` | `deep` | `custom`. Default `standard`.
- `max_sources`, `max_tasks` - only used when `mode` is `custom` (1-30 and 1-15
  respectively). Ignored otherwise (mode presets apply).

**Response `201 Created`:**
```json
{
  "id": "b3f1...",
  "research_question": "...",
  "mode": "standard",
  "status": "pending",
  "current_stage": "pending",
  "progress_percent": 0,
  "error_message": null,
  "created_at": "2026-08-16T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "duration_seconds": null,
  "progress_log": [{"message": "Research session created", "stage": "pending", "timestamp": "..."}]
}
```

**Errors:**
- `422 Unprocessable Entity` - validation failure (question too short/long, invalid mode).
- `503 Service Unavailable` - no AI provider is configured on the server at all.

---

## GET /api/research

List research sessions, most recent first.

**Query params:** `limit` (default 50, max 200), `offset` (default 0).

**Response `200 OK`:** array of the same session object shape as above (without
tasks/sources/report - use the detail endpoint for those).

---

## GET /api/research/{session_id}

Full detail for one session, including tasks, sources, and the report if completed.

**Response `200 OK`:** session object plus:
```json
{
  "...": "...",
  "tasks": [{"id": "...", "order_index": 0, "title": "...", "description": "...", "priority": "medium", "expected_output": "...", "status": "completed", "result_summary": "..."}],
  "sources": [{"id": "...", "title": "...", "url": "...", "domain": "...", "relevance_score": 0.8, "authority_score": 0.9, "recency_score": 0.6, "evidence_score": 0.7, "bias_risk": "low", "overall_quality": 0.78, "trust_label": "verified", "summary": "..."}],
  "report": {"id": "...", "title": "...", "executive_summary": "...", "key_findings": ["..."], "conflicts": [...], "limitations": ["..."], "conclusion": "...", "sources_json": [...]}
}
```

**Errors:** `404 Not Found` if the session doesn't exist.

---

## DELETE /api/research/{session_id}

Permanently deletes a session and all related tasks/sources/report/usage rows (cascade).

**Response:** `204 No Content` on success. `404 Not Found` if the session doesn't exist.

---

## GET /api/research/{session_id}/stream

Server-Sent Events stream of live progress updates. Content-Type: `text/event-stream`. Each
event's `data:` field is a JSON object:
```json
{"status": "running", "stage": "searching", "progress_percent": 32, "error_message": null, "log": [{"message": "...", "stage": "searching", "timestamp": "..."}]}
```
The stream closes automatically once `status` is `completed` or `failed`, or after a 15-minute
safety cap. The frontend (`progress.js`) falls back to polling `GET /api/research/{id}` every
2.5s if `EventSource` isn't supported or the stream errors.

---

## POST /api/research/{session_id}/export

Export a completed session's report.

**Request body:**
```json
{ "format": "markdown" }
```
`format` is one of `markdown` | `html` | `pdf` | `txt` | `json`.

**Response `200 OK`:** the rendered file as the response body, with `Content-Type` matching
the format and a `Content-Disposition: attachment` header for download.

**Errors:**
- `404 Not Found` - session doesn't exist.
- `409 Conflict` - session exists but has no completed report yet.
- `422 Unprocessable Entity` - invalid `format` value.

---

## GET /api/providers

Configuration status for every known AI provider. **Never makes a live API call** - only
checks whether an API key is present.

**Response `200 OK`:**
```json
[
  {"name": "openai", "configured": true, "model": "gpt-4o-mini", "role": ["planning"]},
  {"name": "anthropic", "configured": true, "model": "claude-sonnet-4-5-20250929", "role": ["analysis", "synthesis"]},
  {"name": "gemini", "configured": false, "model": "gemini-2.0-flash", "role": ["crosscheck"]}
]
```

---

## GET /api/health

Liveness/readiness probe used by Docker/Render/Railway health checks.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "database": "connected",
  "providers": {"openai": true, "anthropic": true, "gemini": false},
  "configured_provider_count": 2
}
```
`status` is `"degraded"` (still HTTP 200) if the database check fails, so the process isn't
killed for a transient DB hiccup while still surfacing the problem.

---

## GET /api/config/status

Non-secret application configuration, used by the Settings/About pages.

**Response `200 OK`:**
```json
{
  "app_env": "production",
  "search_backend": "duckduckgo",
  "limits": {
    "max_agent_iterations": 10,
    "max_tool_calls": 20,
    "max_sources": 10,
    "max_research_tasks": 8,
    "request_timeout_seconds": 30,
    "max_provider_retries": 2,
    "provider_fallback_limit": 3
  },
  "fallback_chain": ["openai", "anthropic", "gemini"],
  "configured_providers": ["openai", "anthropic"]
}
```

---

## GET /api/settings/routing

Current provider routing configuration (env defaults merged with any saved overrides).

**Response `200 OK`:**
```json
{
  "primary": "openai", "fallback": "anthropic", "secondary_fallback": "gemini",
  "planning": "openai", "analysis": "anthropic", "crosscheck": "gemini", "synthesis": "anthropic",
  "configured_providers": ["openai", "anthropic"]
}
```

## POST /api/settings/routing

Update routing preferences. **Never accepts or stores API keys** - only provider name
choices from `{openai, anthropic, gemini, auto}`.

**Request body:** any subset of `primary`, `fallback`, `secondary_fallback`, `planning`,
`analysis`, `crosscheck`, `synthesis`, each set to a provider name or `"auto"`.
```json
{ "synthesis": "gemini" }
```

**Response `200 OK`:**
```json
{ "status": "updated", "routing": {"synthesis": "gemini"} }
```

**Errors:** `400 Bad Request` for an unsupported key or invalid provider value.

---

## GET /api/research/{session_id}/usage

Per-call AI provider usage log for one session (which provider/model handled each stage,
whether it was a fallback, duration, success/error type). Powers dashboard/debugging views.

**Response `200 OK`:** array of
```json
{"stage": "planning", "provider": "openai", "model": "gpt-4o-mini", "success": true, "was_fallback": false, "duration_ms": 842, "error_type": null, "created_at": "..."}
```

**Errors:** `404 Not Found` if the session doesn't exist.
