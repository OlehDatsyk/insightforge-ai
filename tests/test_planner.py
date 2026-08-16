"""Tests for research planning / structured output validation (section 7)."""
import pytest

from ai_provider import ProviderResult
from planner import _fallback_plan, _repair_plan, create_research_plan
from schemas import ResearchPlan


def test_fallback_plan_has_tasks():
    plan = _fallback_plan("What is the best programming language?", target_tasks=3)
    assert isinstance(plan, ResearchPlan)
    assert len(plan.tasks) == 3
    assert all(t.title for t in plan.tasks)


def test_repair_plan_recovers_loosely_shaped_json():
    messy = {
        "tasks": [
            {"name": "Find pricing", "goal": "Look up pricing info"},
            {"title": "Compare features", "description": "Compare feature sets"},
            {"title": "", "description": "should be skipped, no title"},
        ],
        "expected_output": "a comparison table",
    }
    plan = _repair_plan(messy, "Compare tool A and tool B")
    assert len(plan.tasks) == 2
    assert plan.tasks[0].title == "Find pricing"
    assert plan.tasks[1].title == "Compare features"


class _FakeRouter:
    def __init__(self, raw_json):
        self.raw_json = raw_json

    async def run_structured(self, **kwargs):
        return ProviderResult(text="{}", provider="openai", model="fake", raw_json=self.raw_json)


@pytest.mark.asyncio
async def test_create_research_plan_validates_and_truncates():
    raw = {
        "research_question": "Compare cloud providers",
        "priority": "high",
        "expected_output": "a comparison",
        "tasks": [
            {"title": f"Task {i}", "description": f"Research item {i}", "priority": "medium", "expected_output": "summary"}
            for i in range(10)
        ],
    }
    router = _FakeRouter(raw)
    plan = await create_research_plan(router, research_question="Compare cloud providers", mode="deep", max_tasks=4)
    assert len(plan.tasks) == 4
    assert plan.research_question == "Compare cloud providers"


@pytest.mark.asyncio
async def test_create_research_plan_falls_back_when_no_tasks_returned():
    router = _FakeRouter({"research_question": "X", "tasks": []})
    plan = await create_research_plan(router, research_question="X", mode="quick", max_tasks=3)
    assert len(plan.tasks) > 0
