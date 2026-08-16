# InsightForge AI

**An agentic, multi-model AI research platform.** Give it a research question; it plans the
research, searches the real web, collects and scores sources, cross-checks facts for
conflicts, and synthesizes a structured, citable report - using OpenAI, Anthropic Claude,
and Google Gemini together, with automatic fallback if any provider fails.

This is not a chatbot wrapper. It is a multi-step agent with real tool calling, structured
output contracts, a provider abstraction layer, and safety-bounded execution.

---

## Table of Contents

- [InsightForge AI](#insightforge-ai)
  - [Table of Contents](#table-of-contents)
  - [Project Overview](#project-overview)
  - [Features](#features)
  - [Architecture](#architecture)
  - [AI Provider Architecture](#ai-provider-architecture)
    - [Fallback system](#fallback-system)
  - [Agent Architecture](#agent-architecture)
  - [Tool Calling](#tool-calling)
  - [Multi-Model Strategy](#multi-model-strategy)
  - [Installation](#installation)
  - [Environment Setup](#environment-setup)
  - [API Keys](#api-keys)
  - [Running Locally](#running-locally)
  - [GitHub Setup](#github-setup)
  - [Render Deployment](#render-deployment)
  - [Railway Deployment](#railway-deployment)
  - [Security](#security)
  - [Troubleshooting](#troubleshooting)
  - [Future Improvements](#future-improvements)

---

## Project Overview

InsightForge AI accepts a research question and runs it through a real agentic pipeline:

```
QUESTION -> PLAN -> SUB-TASKS -> WEB SEARCH -> SOURCE ANALYSIS -> CROSS-CHECK -> SYNTHESIS -> REPORT
```

Every stage is backed by real code: a genuine web search (DuckDuckGo, no API key required),
real AI provider calls (OpenAI / Anthropic / Gemini), a real SQLite/PostgreSQL-compatible
database, and real export rendering (Markdown, HTML, PDF, TXT, JSON). Nothing is simulated.

For the full list of functional requirements this project satisfies, see
[`PROJECT_REVIEW.md`](PROJECT_REVIEW.md), which also documents known limitations honestly.

## Features

- **Agentic research loop** - planning, sub-task generation, tool selection, web search,
  source collection, analysis, cross-checking, and synthesis (not a single prompt-and-done call).
- **Three AI providers** (OpenAI, Anthropic, Gemini) behind one abstraction layer, with a
  configurable primary -> fallback -> secondary-fallback chain.
- **Meaningful multi-model routing** - planning, analysis, cross-checking, and synthesis can
  each use a different provider, configurable via environment variables or the Settings page.
- **Structured output everywhere** - research plans, sources, and reports are validated
  Pydantic models, not scraped free text.
- **Real web search tool** with robots.txt respect, per-domain rate limiting, and source
  deduplication.
- **Source quality scoring** - authority, relevance, recency, evidence quality, bias risk.
- **Conflict detection** - when sources disagree, InsightForge says so explicitly instead of
  silently picking one.
- **Four research modes** - Quick, Standard, Deep, Custom.
- **Live progress UI** via Server-Sent Events, showing a safe high-level activity log (never
  hidden model chain-of-thought).
- **Full report export** - Markdown, HTML, PDF, TXT, JSON.
- **Research history & saved reports** - search, open, delete, export past sessions.
- **Cost & safety controls** - max iterations, max tool calls, max sources, request timeouts,
  provider retry/fallback limits - all configurable, all enforced.
- **Production concerns handled** - structured logging, rate limiting, request size limits,
  safe error handling, no secret leakage, Docker/Render/Railway deployment configs.

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full breakdown. Summary:

```
templates/, static/ -> Frontend (Jinja2 + vanilla HTML/CSS/JS)
app.py, api.py -> FastAPI app + REST endpoints
research_agent.py -> Agent orchestration (the pipeline state machine)
planner.py -> Research planning (structured output)
source_analyzer.py -> Source quality scoring + conflict detection
report_generator.py -> Final report synthesis + export rendering
tools.py, search_tool.py -> Tool-calling infrastructure + real web search
ai_provider.py -> Provider abstraction (ABC)
openai_provider.py -> OpenAI implementation
anthropic_provider.py -> Anthropic implementation
gemini_provider.py -> Gemini implementation
provider_router.py -> Fallback + task-routing orchestration
config.py -> All environment-driven configuration
database.py, models.py -> SQLAlchemy engine/session + ORM models
schemas.py -> Pydantic request/response/structured-output models
```

## AI Provider Architecture

Every vendor implements the same interface:

```
AIProvider (abstract)
    ├── OpenAIProvider
    ├── AnthropicProvider
    └── GeminiProvider
```

Adding a new provider (Mistral, Groq, DeepSeek, OpenRouter, ...) means writing one class that
implements `AIProvider.generate_text()` / `generate_structured()`, registering it in
`provider_router.py`'s provider map, and adding its env vars. Nothing else in the codebase
needs to change - no other module imports a vendor SDK directly.

### Fallback system

```
PRIMARY_AI_PROVIDER=openai
FALLBACK_AI_PROVIDER=anthropic
SECONDARY_FALLBACK_AI_PROVIDER=gemini
```

If the primary provider fails with a retriable error (rate limit, timeout, quota exceeded,
unavailable model, transient failure), the router automatically retries (bounded by
`MAX_PROVIDER_RETRIES`) and then moves to the next provider in the chain. Non-retriable
errors (bad API key) skip straight to the next provider. If every provider fails, the API
returns one generic, user-friendly error - never internal error details or stack traces.
Every attempt is logged server-side with provider, stage, duration, and error type.

## Agent Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md#agent) for the full pipeline diagram. In short,
`research_agent.py`'s `ResearchAgent` class walks a session through:
`planning -> searching -> analyzing -> crosschecking -> synthesizing -> completed`, persisting
progress to the database after each step so the frontend can poll or stream live updates.
Every loop is bounded by `MAX_AGENT_ITERATIONS`; every tool call is bounded by
`MAX_TOOL_CALLS`. If a safety limit is hit, the agent stops gracefully and still returns
whatever partial results it collected.

## Tool Calling

The agent never pretends to have searched or fetched something - every action goes through
`ToolRegistry.execute()`, which dispatches to real Python functions:

| Tool | Description |
|---|---|
| `search_web` | Real web search (DuckDuckGo by default; Tavily optional) |
| `fetch_webpage` | Fetches a page's HTML, respecting robots.txt and rate limits |
| `extract_text` | Extracts readable text from HTML |
| `calculate` | Safe arithmetic evaluation (AST-based, no `eval`) |
| `get_current_date` | Returns today's date for recency judgments |

Adding a tool is one `registry.register(name, description, params, handler)` call.

## Multi-Model Strategy

Different stages use different providers by default (fully configurable):

| Stage | Default Provider | Why |
|---|---|---|
| Research Planning | OpenAI | Fast, reliable structured JSON output |
| Source Analysis | Anthropic Claude | Strong at careful, grounded summarization |
| Cross-Checking | Google Gemini | Independent "second opinion" model reduces correlated errors |
| Final Synthesis | Anthropic Claude | Strong long-form writing and reasoning |

Change any of these on the **Settings** page or via env vars (`PLANNING_PROVIDER`,
`ANALYSIS_PROVIDER`, `CROSSCHECK_PROVIDER`, `SYNTHESIS_PROVIDER`).

## Installation

See [`INSTRUCTION.md`](INSTRUCTION.md) for a complete, beginner-friendly, step-by-step guide
(installing Python/Git/VS Code, virtual environments, running locally, deploying). Quick
version for experienced developers:

```bash
git clone <your-repo-url>
cd insightforge-ai
python -m venv venv
source venv/bin/activate # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env # then add at least one API key
uvicorn app:app --reload
```

Or just double-click **`Start App.bat`** (Windows) or run **`Start App (Mac).command`**
(macOS/Linux) - both scripts handle the virtual environment, dependencies, and `.env` setup
automatically.

## Environment Setup

All configuration lives in environment variables - see [`.env.example`](.env.example) for
the full documented list (provider keys/models, fallback chain, task routing, search backend,
safety limits, database URL, security settings). Copy it to `.env` and fill in your values;
`.env` is git-ignored and must never be committed.

## API Keys

You need **at least one** of these for research to run (all three is recommended to exercise
the fallback system):

- OpenAI: https://platform.openai.com/api-keys
- Anthropic: https://console.anthropic.com/settings/keys
- Google Gemini: https://aistudio.google.com/apikey

Put them in `.env` as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`. The app works
with partial configuration and reports each provider's status on the Dashboard/Settings pages
without ever making a live API call just to check configuration.

## Running Locally

```bash
uvicorn app:app --reload --port 8000
```

Open http://127.0.0.1:8000 in your browser. The interactive API docs are at
http://127.0.0.1:8000/api/docs.

## GitHub Setup

```bash
git init
git add .
git commit -m "Initial commit: InsightForge AI"
git branch -M main
git remote add origin https://github.com/<your-username>/insightforge-ai.git
git push -u origin main
```

`.gitignore` already excludes `.env`, `venv/`, `__pycache__/`, the local SQLite database, and
generated exports, so the repo stays small and secret-free.

## Render Deployment

1. Push this repository to GitHub.
2. In the Render dashboard: **New -> Blueprint**, point it at your repo (Render reads
   `render.yaml` automatically).
3. When prompted, add your `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (and
   `TAVILY_API_KEY` if used) as environment variables - these are marked `sync: false` in
   `render.yaml` so Render always prompts for them rather than expecting them committed.
4. Deploy. Render runs `uvicorn app:app --host 0.0.0.0 --port $PORT` automatically.

## Railway Deployment

1. Push this repository to GitHub.
2. In Railway: **New Project -> Deploy from GitHub repo**.
3. Railway detects `railway.json` and uses Nixpacks to build automatically.
4. Add the same environment variables as above in the Railway dashboard's **Variables** tab.
5. Railway injects `$PORT` automatically; the start command already binds to `0.0.0.0:$PORT`.

## Security

- No API keys are ever hard-coded, committed, logged, or sent to the frontend.
- All configuration flows through environment variables (`config.py` is the only module that
  reads `os.environ`, via `pydantic-settings`).
- Structured logging redacts anything resembling a secret (`logging_config.py`).
- Requests are size-limited and rate-limited (`rate_limiter.py`, `app.py`).
- All input is validated with Pydantic (`schemas.py`) before touching the database or an AI
  provider.
- Errors returned to clients are generic and safe; full detail is logged server-side only.
- Agent loops and tool calls are hard-bounded to prevent runaway costs or infinite loops.

## Troubleshooting

See [`INSTRUCTION.md`](INSTRUCTION.md#troubleshooting) for a full troubleshooting table. Common issues:

- **"No AI provider is configured"** - add at least one API key to `.env` and restart the app.
- **Search returns no results** - some sandboxed/corporate networks block outbound requests to
  search engines; this works normally on a personal machine, Render, or Railway.
- **Port already in use** - another process is using port 8000; stop it or run
  `uvicorn app:app --port 8001`.

## Future Improvements

Documented honestly in [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md), including: streaming
token-level output, per-user authentication/multi-tenancy, a vector-store-backed source
cache, WebSocket-based (rather than polling SSE) progress, and additional providers
(Mistral, Groq, DeepSeek, OpenRouter) using the existing `AIProvider` interface.

---

**License:** MIT - see [`LICENSE`](LICENSE).
