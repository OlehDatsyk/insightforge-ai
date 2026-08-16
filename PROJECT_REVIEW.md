# PROJECT_REVIEW.md

An honest technical self-review of InsightForge AI, performed after the implementation was
complete. Per the project brief, this document records findings rather than silently patching
around them - each item below is a real finding from reading the shipped code, not a
hypothetical.

## What was actually verified (not just written)

- **36 automated tests pass** (`pytest`): provider configuration detection, the fallback
  system (including a simulated "all providers fail" path with a friendly-message assertion),
  structured-JSON extraction edge cases, research plan validation/repair/fallback, the tool
  registry's call-limit enforcement, and a full offline end-to-end run of the agent pipeline
  (planning -> searching -> analyzing -> cross-checking -> synthesizing -> report) with every
  export format (Markdown/HTML/PDF/TXT/JSON) rendered from the resulting report.
- **The app was actually booted** with `uvicorn` and every page (`/`, `/dashboard`,
  `/research/new`, `/history`, `/reports`, `/settings`, `/about`) and API endpoint
  (`/api/health`, `/api/providers`, `/api/config/status`) was requested live and returned
  correct status codes/content.
- **All three provider SDKs were introspected against the actually-installed package
  versions** (not assumed from memory) - `google-genai` 0.5.0's `GenerateContentConfig` /
  `GenerateContentResponse` / `GenerateContentResponseUsageMetadata` field names, and the
  `anthropic` / `openai` SDKs' async client classes and exception hierarchies - to confirm
  the provider modules call real, existing APIs correctly.
- **What could not be verified in this development sandbox:** outbound network access here is
  restricted to an allowlist that excludes the AI vendor APIs and search engines (confirmed
  by testing direct HTTP calls to `api.openai.com`, `duckduckgo.com`, and even
  `example.com`, all of which returned `403` from the sandbox's egress proxy). This means the
  actual live search results and live AI provider responses could not be exercised end-to-end
  from within this session. This is a property of the development sandbox, not of the code -
  the same requests work normally from a personal machine, or from Render/Railway. **Run the
  smoke test in `INSTRUCTION.md` step 16 with real API keys before considering this fully
  verified in your own environment.**

## Findings

### 1. Custom research mode caps tasks below what the user requested - Medium
**File:** `planner.py` (`MODE_TASK_COUNTS`, `create_research_plan`)
**Why it matters:** `MODE_TASK_COUNTS["custom"] = 6` is combined with `min(6, max_tasks)`,
so a user who explicitly selects Custom mode and asks for, say, 12 tasks will only ever get
up to 6 - silently, with no error or indication why. The Custom mode's entire purpose is
"user chooses depth," so this is a functional inconsistency, not just a cosmetic one.
**Recommended improvement:** For `mode == "custom"`, set `target_tasks = max_tasks` directly
instead of running it through `MODE_TASK_COUNTS`. The existing `min(..., max_tasks)` pattern
should stay for the preset modes only.

### 2. Conflict-to-source linkage relies on exact title string matching - Medium
**File:** `research_agent.py` (`_mark_sources_with_conflicts`)
**Why it matters:** After the cross-checking stage identifies conflicting sources by title
(via the LLM's JSON output), `_mark_sources_with_conflicts` tries to flip those sources'
`trust_label` to `"conflicting"` by matching `Source.title` against the titles the model
returned. LLMs frequently paraphrase, truncate, or lightly reformat titles rather than
echoing them byte-for-byte, so this match can silently fail - the conflict still appears in
the report's "Conflicting Information" section, but the affected source cards on the results
page may not get flagged.
**Recommended improvement:** Include stable `source_id` values in the cross-check prompt/
schema (`ConflictItem`) instead of relying on titles, and match on ID.

### 3. No recovery for a research session interrupted by a process restart - Medium
**File:** `research_agent.py`, `api.py` (`BackgroundTasks.add_task`)
**Why it matters:** Research runs as an in-process `BackgroundTask`. If the server restarts
mid-run (a new deploy, a crash, a free-tier host spinning the instance down), the session is
left permanently in `status="running"` with no automatic way to detect or recover from this -
the user just sees a progress page that never updates again.
**Recommended improvement:** Add a periodic sweep (e.g. on startup, or a lightweight
scheduled job) that marks any session stuck in a non-terminal state for longer than a
reasonable timeout as `failed` with an explanatory message. For real production scale, replace
in-process `BackgroundTasks` with a durable task queue (Celery, RQ, or Arq backed by Redis)
so in-flight work survives process restarts.

### 4. Rate limiter keys on a header that may be the proxy's IP, not the client's - Low
**File:** `rate_limiter.py`
**Why it matters:** `RateLimitMiddleware` uses `request.client.host`. Behind Render's or
Railway's reverse proxy, this can report the proxy's own IP for every request rather than the
actual visitor's, which would pool all real users into a single shared rate-limit bucket
(too strict for many users, not strict enough per-abuser).
**Recommended improvement:** When running behind a trusted proxy, parse `X-Forwarded-For` /
`X-Real-IP` instead (with care to only trust it when the proxy is known/configured).

### 5. In-memory rate limiter and SQLite are both single-process - Low
**Files:** `rate_limiter.py`, `database.py`
**Why it matters:** Both are documented in their own module docstrings as single-process-only
by design (appropriate for the free/hobby-tier single-instance deployments this project
targets). If this were scaled horizontally (multiple replicas behind a load balancer), rate
limits wouldn't be shared across instances and SQLite would need to become a real bottleneck/
contention point.
**Recommended improvement:** Swap in Redis-backed rate limiting and a managed PostgreSQL
instance (already supported - just change `DATABASE_URL`) before scaling beyond one instance.

### 6. No authentication or multi-tenancy - Low (by scope, worth flagging explicitly)
**Files:** `api.py`, entire app
**Why it matters:** Every API endpoint is open to anyone who can reach the deployed URL -
there's no login, API key, or per-user data isolation. Any visitor can view, export, or
delete any research session. This is a reasonable scope boundary for a single-user portfolio
demo, but it is a real gap that must be closed before any multi-user or public deployment.
**Recommended improvement:** Add an auth layer (API key header, or OAuth via a provider like
GitHub/Google) and scope `ResearchSession` rows to a `user_id` before exposing this beyond a
single trusted user.

### 7. `SECRET_KEY` is defined but currently unused - Low
**Files:** `config.py`, `.env.example`
**Why it matters:** It's present for forward-compatibility with session/JWT signing once
authentication (see #6) is added, but as shipped nothing reads it. Not a bug, but a reviewer
scanning for dead configuration would correctly flag it.
**Recommended improvement:** Either wire it into an auth implementation, or remove it until
it's needed - left in for now since auth is documented as a near-term future improvement.

### 8. Request body size limit only checks `Content-Length` - Low
**File:** `app.py` (`BodySizeLimitMiddleware`)
**Why it matters:** A request sent with `Transfer-Encoding: chunked` (no `Content-Length`
header) would bypass this check entirely and could stream an arbitrarily large body.
**Recommended improvement:** Additionally enforce a running byte-count cap while consuming
the request body, not just a header pre-check.

### 9. No database migration tooling - Low
**Files:** `database.py`, `models.py`
**Why it matters:** `init_db()` calls `Base.metadata.create_all()`, which creates missing
tables but does not alter existing ones. If `models.py` changes after a database already has
data in it, the running deployment needs manual schema intervention.
**Recommended improvement:** Introduce Alembic if/when this project needs to evolve its schema
against a live database with existing data (not necessary for a fresh local SQLite file each
time, which is the primary supported local-dev path today).

### 10. Source quality scoring is heuristic, not AI-assessed - Informational, by design
**File:** `source_analyzer.py`
**Why it matters:** Authority/relevance/recency/evidence/bias scores come from domain
allowlists, keyword overlap, regex date parsing, and snippet-length heuristics - not another
AI call. This is a deliberate trade-off (fast, free, deterministic, no extra latency or cost
per source) but it means an authoritative source on an unrecognized domain, or a low-quality
source on a domain that merely looks reputable, can be scored incorrectly.
**Recommended improvement:** Acceptable as shipped; if scoring accuracy becomes a priority,
consider an optional AI-assisted scoring pass for sources near the trust-label boundary only
(to control cost).

### 11. "Saved Reports" and "Research History" share the same list endpoint - Informational
**Files:** `templates/reports.html`, `templates/history.html`, `static/js/history.js`
**Why it matters:** Both pages call `GET /api/research` and filter/render client-side; Saved
Reports doesn't show a sources-count column (would require an extra request per row). A minor
UX simplification, not a missing feature - full source data is one click away on the results
page.
**Recommended improvement:** If a sources-count column is wanted, either denormalize a
`source_count` field onto `ResearchSession` (updated when sources are added) or accept the
extra per-row request cost.

## Summary

InsightForge AI's core claims hold up under review: it is a real multi-step agent (not a
single prompt), it genuinely supports three independent AI providers with automatic fallback
and per-stage routing, it uses real tool calling and a real (not simulated) web search, and it
produces validated structured output at every stage. The findings above are the kind of gaps
a careful reviewer should expect in a single-developer portfolio project rather than signs of
incompleteness relative to the stated goal - none of them block running the app locally or
demonstrating the full pipeline, and all are documented here rather than hidden. **This
project should be described as a strong, working demonstration of agentic AI system design -
not as a hardened, multi-tenant production SaaS product**, per items #3 and #6 above in
particular.
