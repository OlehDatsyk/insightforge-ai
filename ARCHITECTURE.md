# ARCHITECTURE.md

Technical architecture documentation for InsightForge AI.

## 1. High-level layers

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (templates/ + static/)                                 │
│  Jinja2-rendered page shells + vanilla JS calling /api/*          │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ HTTP / SSE
┌───────────────────────────────▼───────────────────────────────────┐
│  API layer (api.py)                                                │
│  Request validation, HTTP semantics, translates internal            │
│  exceptions into safe responses                                     │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────┐
│  Agent layer (research_agent.py, planner.py, source_analyzer.py,    │
│                report_generator.py)                                 │
│  Orchestrates the multi-step research pipeline & business logic     │
└───────┬───────────────────────┬────────────────────────┬──────────┘
        │                       │                        │
┌───────▼────────┐   ┌──────────▼──────────┐   ┌──────────▼─────────┐
│ Provider layer  │   │ Tool layer           │   │ Database layer      │
│ (ai_provider.py,│   │ (tools.py,           │   │ (database.py,       │
│  *_provider.py, │   │  search_tool.py)      │   │  models.py)         │
│  provider_router)│  │                       │   │                     │
└─────────────────┘   └───────────────────────┘   └─────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────────┐
│  Configuration layer (config.py) - the only module reading os.environ │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Frontend

Server-rendered Jinja2 page shells (`templates/*.html`) extend a shared `base.html` that
provides the nav bar, theme toggle, and toast system. Every page is otherwise a static shell
- all data loads client-side via `fetch()` calls to `/api/*`, implemented in
`static/js/api.js` (a small typed wrapper with consistent error handling) and page-specific
scripts (`dashboard.js`, `new_research.js`, `progress.js`, `results.js`, `history.js`,
`settings.js`). This keeps the backend a pure JSON API and the frontend framework-free -
no build step, no bundler, works by just opening the page.

Dark/light theme is implemented with CSS custom properties switched via a `data-theme`
attribute on `<html>`, persisted in a cookie rather than `localStorage` (deliberately avoided
per this project's frontend guidelines). The cookie is read client-side on each page load to
restore the user's preference before first paint.

## 3. FastAPI (`app.py`)

Owns only cross-cutting concerns: CORS, rate limiting (`rate_limiter.py`), request body size
limits, structured logging setup (`logging_config.py`), the Jinja2 template environment,
static file mounting, global exception handling (never leaks internals - see section 10
below), and the page routes. All `/api/*` business endpoints live in `api.py`'s `APIRouter`,
included once. Startup (via a `lifespan` context manager) creates database tables if missing
and loads any previously-saved provider routing overrides from the database.

## 4. Agent (`research_agent.py`)

`ResearchAgent` is the state machine that walks one `ResearchSession` through:

```
pending -> planning -> searching -> analyzing -> crosschecking -> synthesizing -> completed
                                                                            ↘ failed (any stage)
```

Each stage:
1. Opens a short-lived DB session (`database.session_scope()`) to read/write state - the
   agent never holds a DB connection open across a slow AI/network call.
2. Calls into `planner.py` / `source_analyzer.py` / `report_generator.py` as needed.
3. Appends a safe, high-level message to `ResearchSession.progress_log` (never internal
   model reasoning - see section 11 of the original spec / section 9 below).
4. Updates `progress_percent` so the frontend progress bar and stage list can render
   accurately, whether polling or streaming via SSE.

Safety: `_check_iteration_budget()` increments a counter on every major loop step and raises
if `MAX_AGENT_ITERATIONS` is exceeded; `ToolRegistry` independently enforces `MAX_TOOL_CALLS`.
Either limit being hit stops the agent gracefully rather than looping forever - the session is
marked `failed` with a safe message, and whatever was collected up to that point remains in
the database and queryable.

## 5. Planner (`planner.py`)

Converts the raw research question into a `schemas.ResearchPlan` via a structured-output call
to the "planning" provider. If the model's JSON doesn't validate against the Pydantic schema,
`_repair_plan()` attempts a best-effort recovery (renaming loosely-matching keys); if the
model returns no usable tasks at all, `_fallback_plan()` provides a deterministic generic plan
so the pipeline can still proceed rather than hard-failing.

## 6. Tools (`tools.py`, `search_tool.py`)

`ToolRegistry` is a simple name -> handler map with a hard call-count ceiling
(`MAX_TOOL_CALLS`). Every tool call - successful or not - is logged in `call_log`.
`search_tool.py` implements real web search (DuckDuckGo via the `ddgs` package by default, or
Tavily if `SEARCH_BACKEND=tavily` and a key is set) plus `fetch_webpage`/`extract_text`
helpers that check `robots.txt`, enforce a per-domain minimum request interval, and cap page
size. `calculate` uses an AST-based evaluator (never `eval()`) restricted to arithmetic
operators only.

## 7. AI Provider Layer

`ai_provider.py` defines the `AIProvider` ABC and the shared exception hierarchy
(`ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderAuthError`,
`ProviderUnavailableError`, `StructuredOutputParseError`) that every vendor module maps its
SDK's own exceptions onto. This normalization is what lets `provider_router.py` reason about
retriability generically instead of vendor-by-vendor.

- **`openai_provider.py`** - uses `AsyncOpenAI`, native JSON mode
  (`response_format={"type": "json_object"}`) for structured calls.
- **`anthropic_provider.py`** - uses `AsyncAnthropic`; Claude has no dedicated JSON mode, so
  structured calls rely on strict prompting + the base class's tolerant JSON extraction.
- **`gemini_provider.py`** - uses the `google-genai` SDK's synchronous client dispatched
  through `asyncio.to_thread`, with `response_mime_type="application/json"` for structured
  calls.

## 8. Provider Router (`provider_router.py`)

Two responsibilities layered on top of the provider ABC:

1. **Fallback** - `_run()` tries providers in `_ordered_chain_for_stage()` order (the
   stage's preferred provider first, then the global primary/fallback/secondary chain,
   deduplicated, filtered to only configured providers), retrying each up to
   `MAX_PROVIDER_RETRIES` times with bounded exponential backoff for retriable errors, and
   moving on immediately for non-retriable ones (e.g. bad key). If every provider in the
   (length-capped by `PROVIDER_FALLBACK_LIMIT`) chain fails, it raises
   `AllProvidersFailedError` with one safe, generic message.
2. **Routing** - `STAGE_ENV_MAP` maps pipeline stages to their configured "preferred
   provider" env var. Runtime overrides (set from the Settings page, persisted to the
   `AppSetting` table) take precedence over the env-configured default without ever
   touching API keys.

## 9. Database (`database.py`, `models.py`)

SQLAlchemy 2.0 declarative models, SQLite by default (`sqlite:///./data/insightforge.db`),
swappable to PostgreSQL by changing `DATABASE_URL` alone - no code changes required (SQLite's
`check_same_thread` connect arg is applied conditionally). Tables: `research_sessions`,
`research_tasks`, `sources`, `reports`, `provider_usage`, `app_settings`. `session_scope()`
provides a short-lived, auto-committing context manager used throughout the agent so DB
connections are never held open across slow network calls.

## 10. Search (`search_tool.py`)

See section 6. Deduplicates by exact URL and caps results per domain (max 2) to keep source
diversity, per the "avoid duplicate sources" requirement.

## 11. Report Generator (`report_generator.py`)

`synthesize_report()` calls the "synthesis" provider for the analytical prose (executive
summary, key findings, detailed analysis, comparison, limitations, conclusion) but **sources
and detected conflicts are never re-generated by the AI at this stage** - they're passed in
directly from the database, so the report can never cite a source the agent didn't actually
collect. `EXPORTERS` maps format name -> renderer function: `to_markdown`, `to_html` (via the
`markdown` library), `to_txt`, `to_json`, and `to_pdf` (via `reportlab`, chosen over
`weasyprint` specifically because it's pure-Python with no system-level C library
dependencies - critical for reliable deployment on Render/Railway without a custom Docker
build step).

## 12. Fallback System (cross-reference)

Documented in depth in section 8 above and in `README.md`'s "AI Provider Architecture"
section. The important architectural point: fallback is generic infrastructure in
`provider_router.py`, not duplicated per-vendor logic - every call site (`planner.py`,
`research_agent.py`'s analysis stage, `source_analyzer.py`'s conflict detection,
`report_generator.py`'s synthesis) goes through the same `run_text` / `run_structured`
methods and gets fallback behavior for free.

## 13. Deployment

- **Local:** `uvicorn app:app --reload` (see `Start App.bat` / `Start App (Mac).command`
  for a zero-typing bootstrap).
- **Docker:** `Dockerfile` builds a slim Python 3.11 image, installs
  `requirements.txt`, and runs `uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}`. Includes
  a `HEALTHCHECK` that calls `/api/health` (no AI provider calls).
- **Render:** `render.yaml` blueprint - Python runtime (no Docker required), health check
  path `/api/health`, secret env vars marked `sync: false` so Render prompts for them.
- **Railway:** `railway.json` - Nixpacks builder, same start command, health check, and
  restart policy.

Both cloud targets bind to `0.0.0.0` and read `$PORT` from the environment rather than
assuming a fixed local port, per the deployment requirements.
