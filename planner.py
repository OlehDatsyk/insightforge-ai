"""
planner.py
==========
Converts a raw research question into a structured research plan
(``schemas.ResearchPlan``) using the AI provider assigned to the
"planning" stage (configurable, defaults to OpenAI - see ``.env.example``).

The plan is real structured output validated against a Pydantic model, not
free-form text the rest of the pipeline has to guess at.
"""
from __future__ import annotations

import logging

from pydantic import ValidationError

from provider_router import ProviderRouter
from schemas import PlannedTask, ResearchPlan

logger = logging.getLogger("insightforge.planner")

SYSTEM_PROMPT = (
    "You are the planning module of InsightForge AI, an agentic research system. "
    "Your ONLY job is to break a research question into a small set of concrete, "
    "independently-researchable sub-tasks. You never answer the question yourself. "
    "You always respond with valid JSON and nothing else."
)

SCHEMA_HINT = """{
  "research_question": "<restated question>",
  "priority": "low|medium|high",
  "expected_output": "<one sentence describing what the final report should deliver>",
  "tasks": [
    {
      "title": "<short task title>",
      "description": "<what to research for this task>",
      "priority": "low|medium|high",
      "expected_output": "<what this task should produce>"
    }
  ]
}"""

MODE_TASK_COUNTS = {
    "quick": 3,
    "standard": 5,
    "deep": 8,
    "custom": 6,
}


async def create_research_plan(
    router: ProviderRouter,
    *,
    research_question: str,
    mode: str = "standard",
    max_tasks: int = 8,
    usage_recorder=None,
) -> ResearchPlan:
    """Generate and validate a structured research plan."""
    target_tasks = min(MODE_TASK_COUNTS.get(mode, 5), max_tasks)

    user_prompt = (
        f'Research question: "{research_question}"\n\n'
        f"Break this into exactly {target_tasks} concrete research sub-tasks that, together, "
        "cover everything needed to answer the question thoroughly. Each task should be "
        "narrow enough to research independently via web search. Order tasks logically "
        "(foundational tasks first, comparison/synthesis-oriented tasks last)."
    )

    result = await router.run_structured(
        stage="planning",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema_hint=SCHEMA_HINT,
        max_tokens=1500,
        temperature=0.3,
        usage_recorder=usage_recorder,
    )

    data = result.raw_json or {}
    data.setdefault("research_question", research_question)

    try:
        plan = ResearchPlan.model_validate(data)
    except ValidationError as exc:
        logger.warning("planner produced invalid structured output, applying repair: %s", exc)
        plan = _repair_plan(data, research_question)

    if not plan.tasks:
        plan = _fallback_plan(research_question, target_tasks)

    plan.tasks = plan.tasks[:max_tasks]
    return plan


def _repair_plan(data: dict, research_question: str) -> ResearchPlan:
    """Best-effort recovery when the model's JSON is close but not schema-valid."""
    raw_tasks = data.get("tasks") or []
    tasks: list[PlannedTask] = []
    for t in raw_tasks:
        if not isinstance(t, dict):
            continue
        title = str(t.get("title") or t.get("name") or "").strip()
        description = str(t.get("description") or t.get("goal") or title).strip()
        if not title:
            continue
        priority = t.get("priority") if t.get("priority") in ("low", "medium", "high") else "medium"
        tasks.append(
            PlannedTask(
                title=title[:300],
                description=description or title,
                priority=priority,
                expected_output=str(t.get("expected_output") or ""),
            )
        )
    return ResearchPlan(
        research_question=research_question,
        tasks=tasks,
        priority="medium",
        expected_output=str(data.get("expected_output") or ""),
    )


def _fallback_plan(research_question: str, target_tasks: int) -> ResearchPlan:
    """Deterministic plan used only if the AI provider returns no usable tasks at all."""
    generic = [
        ("Background and context", f"Gather background context and definitions relevant to: {research_question}"),
        ("Key facts and data", f"Collect the key facts, figures, and data points needed to answer: {research_question}"),
        ("Comparative analysis", "Compare the main options/entities identified so far."),
        ("Expert and community perspectives", "Find expert opinions, reviews, or community consensus."),
        ("Recent developments", "Identify recent news or changes relevant to the question."),
        ("Synthesis", "Synthesize findings into a coherent answer."),
    ][:target_tasks]
    tasks = [
        PlannedTask(title=title, description=desc, priority="medium", expected_output="A short written summary")
        for title, desc in generic
    ]
    return ResearchPlan(research_question=research_question, tasks=tasks, priority="medium", expected_output="")
