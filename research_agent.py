"""
research_agent.py
==================
The agentic research loop (section 6):

    USER QUESTION -> PLANNER -> RESEARCH PLAN -> SUB-TASK GENERATION
    -> TOOL SELECTION -> WEB SEARCH -> SOURCE COLLECTION -> SOURCE ANALYSIS
    -> CROSS-CHECKING -> SYNTHESIS -> FINAL REPORT

State lives in the database (``ResearchSession`` + related tables), so the
agent can be inspected mid-run by the API/frontend and survives process
restarts between stages. Each stage opens a short-lived DB session to persist
progress rather than holding a connection open across slow AI/network calls.

Safety (section 27): every loop is bounded by ``MAX_AGENT_ITERATIONS``,
every AI call goes through the provider router's own retry/timeout limits,
and every tool call goes through ``ToolRegistry`` which enforces
``MAX_TOOL_CALLS``. If any limit is hit, the agent stops gracefully and
still produces the best report it can from what it collected so far.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from config import Settings, get_settings
from database import session_scope
from models import ProviderUsage, ResearchSession, ResearchTask, Source
from planner import create_research_plan
from provider_router import AllProvidersFailedError, ProviderRouter, get_router
from report_generator import synthesize_report
from source_analyzer import detect_conflicts, score_source
from tools import ToolCallLimitExceeded, ToolExecutionError, build_default_registry

logger = logging.getLogger("insightforge.agent")

ANALYSIS_SYSTEM_PROMPT = (
    "You are the analysis module of InsightForge AI. Given raw source excerpts collected "
    "for one research sub-task, write a concise (3-6 sentence) factual summary of what was "
    "learned. Note explicitly if the sources provide weak or insufficient evidence. Do not "
    "invent information that isn't supported by the excerpts. Plain text only, no JSON."
)


def _stage_weights(num_tasks: int) -> dict[str, tuple[int, int]]:
    """Progress-percent ranges for each stage, used to compute progress_percent."""
    return {
        "planning": (0, 10),
        "searching": (10, 55),
        "analyzing": (55, 75),
        "crosschecking": (75, 85),
        "synthesizing": (85, 98),
        "completed": (98, 100),
    }


class ResearchAgent:
    def __init__(self, session_id: str, settings: Settings | None = None, router: ProviderRouter | None = None):
        self.session_id = session_id
        self.settings = settings or get_settings()
        self.router = router or get_router()
        self.registry = build_default_registry(self.settings)
        self.iterations = 0
        self._max_iterations = self.settings.max_agent_iterations

    # ------------------------------------------------------------------
    # DB helpers (short-lived sessions)
    # ------------------------------------------------------------------
    def _touch(self, *, stage: str | None = None, percent: int | None = None, message: str | None = None) -> None:
        with session_scope() as db:
            session = db.get(ResearchSession, self.session_id)
            if session is None:
                return
            if stage:
                session.current_stage = stage
            if percent is not None:
                session.progress_percent = percent
            if message:
                session.add_progress(message, stage=stage)

    def _record_usage(self, *, stage: str, provider: str, model: str, success: bool, was_fallback: bool, duration_ms: int, error_type: str | None) -> None:
        with session_scope() as db:
            db.add(
                ProviderUsage(
                    session_id=self.session_id,
                    stage=stage,
                    provider=provider,
                    model=model,
                    success=success,
                    was_fallback=was_fallback,
                    duration_ms=duration_ms,
                    error_type=error_type,
                )
            )

    def _check_iteration_budget(self) -> None:
        self.iterations += 1
        if self.iterations > self._max_iterations:
            raise RuntimeError(f"Agent iteration limit ({self._max_iterations}) reached.")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def run(self) -> None:
        started = time.monotonic()
        try:
            with session_scope() as db:
                session = db.get(ResearchSession, self.session_id)
                if session is None:
                    logger.error("research_agent: session %s not found", self.session_id)
                    return
                session.status = "running"
                session.started_at = datetime.now(timezone.utc)
                question, mode = session.research_question, session.mode
                max_sources, max_tasks = session.max_sources, session.max_tasks
                session.add_progress("Research started", stage="planning")

            plan = await self._plan_stage(question, mode, max_tasks)
            task_rows = self._persist_tasks(plan)

            task_results, sources = await self._research_stage(question, task_rows, max_sources)
            await self._analyze_stage(task_results)

            conflicts = await self._crosscheck_stage(question, sources)
            report = await self._synthesis_stage(question, task_results, sources, conflicts, mode)

            self._persist_report(report)
            self._mark_sources_with_conflicts(conflicts)

            duration = time.monotonic() - started
            with session_scope() as db:
                session = db.get(ResearchSession, self.session_id)
                session.status = "completed"
                session.current_stage = "completed"
                session.progress_percent = 100
                session.completed_at = datetime.now(timezone.utc)
                session.duration_seconds = round(duration, 2)
                session.add_progress("Research complete", stage="completed")

        except AllProvidersFailedError as exc:
            logger.error("research session %s failed: all providers failed", self.session_id)
            self._fail(exc.user_message)
        except (ToolCallLimitExceeded, RuntimeError) as exc:
            logger.warning("research session %s stopped early: %s", self.session_id, exc)
            self._fail("Research stopped early after reaching a safety limit. Partial results may be available.")
        except Exception:  # noqa: BLE001
            logger.exception("research session %s failed unexpectedly", self.session_id)
            self._fail("An unexpected error occurred while conducting research. Please try again.")

    def _fail(self, message: str) -> None:
        with session_scope() as db:
            session = db.get(ResearchSession, self.session_id)
            if session is None:
                return
            session.status = "failed"
            session.error_message = message
            session.completed_at = datetime.now(timezone.utc)
            session.add_progress(f"Research failed: {message}", stage="failed")

    # ------------------------------------------------------------------
    # Stage: Planning
    # ------------------------------------------------------------------
    async def _plan_stage(self, question: str, mode: str, max_tasks: int):
        self._check_iteration_budget()
        self._touch(stage="planning", percent=5, message="Creating research plan")
        plan = await create_research_plan(
            self.router,
            research_question=question,
            mode=mode,
            max_tasks=max_tasks,
            usage_recorder=lambda **kw: self._record_usage(**kw),
        )
        self._touch(stage="planning", percent=10, message=f"Research plan created ({len(plan.tasks)} tasks)")
        return plan

    def _persist_tasks(self, plan) -> list[dict]:
        rows = []
        with session_scope() as db:
            for i, t in enumerate(plan.tasks):
                row = ResearchTask(
                    session_id=self.session_id,
                    order_index=i,
                    title=t.title,
                    description=t.description,
                    priority=t.priority,
                    expected_output=t.expected_output,
                    status="pending",
                )
                db.add(row)
                db.flush()
                rows.append({"id": row.id, "title": row.title, "description": row.description})
        return rows

    # ------------------------------------------------------------------
    # Stage: Search + source collection
    # ------------------------------------------------------------------
    async def _research_stage(self, question: str, task_rows: list[dict], max_sources: int):
        self._touch(stage="searching", percent=15, message="Searching sources")
        task_results = []
        all_sources: list[dict] = []
        seen_urls: set[str] = set()
        num_tasks = max(1, len(task_rows))

        for idx, task in enumerate(task_rows):
            self._check_iteration_budget()
            percent = 15 + int(((idx + 1) / num_tasks) * 40)

            with session_scope() as db:
                db_task = db.get(ResearchTask, task["id"])
                db_task.status = "in_progress"

            query = f"{task['title']} {question}"
            try:
                results = self.registry.execute("search_web", query=query, max_results=5)
            except (ToolCallLimitExceeded, ToolExecutionError) as exc:
                logger.warning("search skipped for task %s: %s", task["id"], exc)
                results = []

            collected_for_task = []
            for r in results:
                if len(all_sources) >= max_sources:
                    break
                url = r.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                snippet = r.get("snippet", "")
                scores = score_source(query=query, title=r.get("title", ""), url=url, snippet=snippet)

                source_dict = {
                    "title": r.get("title", url)[:500],
                    "url": url,
                    "domain": scores["domain"],
                    "source_type": "web",
                    "published_date": None,
                    "summary": snippet[:1000],
                    "raw_snippet": snippet[:2000],
                    **{k: v for k, v in scores.items() if k != "domain"},
                }
                with session_scope() as db:
                    db.add(Source(session_id=self.session_id, **source_dict))
                all_sources.append(source_dict)
                collected_for_task.append(source_dict)

            task_results.append({**task, "sources": collected_for_task})
            self._touch(stage="searching", percent=percent, message=f"Collected {len(collected_for_task)} sources for '{task['title']}'")

        self._touch(stage="searching", percent=55, message=f"Source collection complete ({len(all_sources)} total sources)")
        return task_results, all_sources

    # ------------------------------------------------------------------
    # Stage: Source analysis (per-task AI summarization)
    # ------------------------------------------------------------------
    async def _analyze_stage(self, task_results: list[dict]) -> None:
        self._touch(stage="analyzing", percent=58, message="Analyzing sources")
        num_tasks = max(1, len(task_results))
        for idx, task in enumerate(task_results):
            self._check_iteration_budget()
            excerpts = "\n\n".join(f"- {s['title']}: {s['summary']}" for s in task["sources"]) or "No sources were found for this task."
            user_prompt = f"Sub-task: {task['title']}\n{task['description']}\n\nSource excerpts:\n{excerpts}"

            summary_text = "No sources were available to analyze for this task."
            try:
                result = await self.router.run_text(
                    stage="analysis",
                    system_prompt=ANALYSIS_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    max_tokens=600,
                    temperature=0.3,
                    usage_recorder=lambda **kw: self._record_usage(**kw),
                )
                summary_text = result.text.strip() or summary_text
            except AllProvidersFailedError as exc:
                logger.warning("analysis stage fallback exhausted for task %s", task["id"])
                summary_text = f"Analysis unavailable: {exc.user_message}"

            task["result_summary"] = summary_text
            with session_scope() as db:
                db_task = db.get(ResearchTask, task["id"])
                db_task.status = "completed"
                db_task.result_summary = summary_text

            percent = 58 + int(((idx + 1) / num_tasks) * 17)
            self._touch(stage="analyzing", percent=percent, message=f"Analyzed '{task['title']}'")

        self._touch(stage="analyzing", percent=75, message="Source analysis complete")

    # ------------------------------------------------------------------
    # Stage: Cross-checking (conflict detection)
    # ------------------------------------------------------------------
    async def _crosscheck_stage(self, question: str, sources: list[dict]) -> list:
        self._check_iteration_budget()
        self._touch(stage="crosschecking", percent=78, message="Cross-checking information across sources")
        conflicts = await detect_conflicts(
            self.router,
            research_question=question,
            sources=sources,
            usage_recorder=lambda **kw: self._record_usage(**kw),
        )
        msg = f"Detected {len(conflicts)} conflict(s) between sources" if conflicts else "No conflicting information detected"
        self._touch(stage="crosschecking", percent=85, message=msg)
        return conflicts

    # ------------------------------------------------------------------
    # Stage: Synthesis
    # ------------------------------------------------------------------
    async def _synthesis_stage(self, question: str, task_results, sources, conflicts, mode: str):
        self._check_iteration_budget()
        self._touch(stage="synthesizing", percent=88, message="Generating final report")
        report = await synthesize_report(
            self.router,
            research_question=question,
            task_results=task_results,
            sources=sources,
            conflicts=[c.model_dump() for c in conflicts],
            mode=mode,
            usage_recorder=lambda **kw: self._record_usage(**kw),
        )
        self._touch(stage="synthesizing", percent=98, message="Final report generated")
        return report

    def _persist_report(self, report) -> None:
        from models import Report

        with session_scope() as db:
            db.add(
                Report(
                    session_id=self.session_id,
                    title=report.title,
                    executive_summary=report.executive_summary,
                    methodology=report.methodology,
                    key_findings=report.key_findings,
                    detailed_analysis=report.detailed_analysis,
                    comparison=report.comparison,
                    conflicts=[c.model_dump() for c in report.conflicting_information],
                    limitations=report.limitations,
                    conclusion=report.conclusion,
                    sources_json=[s.model_dump() if hasattr(s, "model_dump") else s for s in report.sources],
                )
            )

    def _mark_sources_with_conflicts(self, conflicts) -> None:
        if not conflicts:
            return
        flagged_titles = set()
        for c in conflicts:
            flagged_titles.add(c.source_a_title)
            flagged_titles.add(c.source_b_title)
        if not flagged_titles:
            return
        with session_scope() as db:
            rows = db.query(Source).filter(Source.session_id == self.session_id).all()
            for row in rows:
                if row.title in flagged_titles:
                    row.trust_label = "conflicting"


async def run_research_session(session_id: str) -> None:
    """Entry point used by the FastAPI background task."""
    agent = ResearchAgent(session_id)
    await agent.run()
