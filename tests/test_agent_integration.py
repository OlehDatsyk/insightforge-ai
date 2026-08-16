"""
End-to-end integration test for the full agentic research loop (section 6),
run entirely offline: the AI provider layer and the web-search tool are
replaced with deterministic fakes so the test doesn't depend on network
access or real API keys, but every other piece of the pipeline - planning,
task persistence, source scoring, DB writes, conflict detection, report
synthesis, and every export format - runs for real.
"""
from __future__ import annotations

import json

import pytest

from ai_provider import ProviderResult


class _FakeRouter:
    """Stands in for ProviderRouter, returning canned-but-realistic structured output."""

    async def run_structured(self, *, stage, system_prompt, user_prompt, schema_hint, max_tokens=0, temperature=0, usage_recorder=None):
        if usage_recorder:
            usage_recorder(stage=stage, provider="openai", model="fake-model", success=True, was_fallback=False, duration_ms=5, error_type=None)

        if stage == "planning":
            data = {
                "research_question": "Compare Python web frameworks",
                "priority": "medium",
                "expected_output": "a comparison",
                "tasks": [
                    {"title": "Identify major frameworks", "description": "List popular frameworks", "priority": "high", "expected_output": "list"},
                    {"title": "Compare performance", "description": "Compare benchmarks", "priority": "medium", "expected_output": "summary"},
                ],
            }
        elif stage == "crosscheck":
            data = {
                "conflicts": [
                    {
                        "topic": "Benchmark results",
                        "description": "Sources disagree on relative performance",
                        "source_a_title": "Example Source 1",
                        "source_a_value": "Framework A is fastest",
                        "source_b_title": "Example Source 2",
                        "source_b_value": "Framework B is fastest",
                    }
                ]
            }
        elif stage == "synthesis":
            data = {
                "title": "Python Web Framework Comparison",
                "executive_summary": "This report compares popular Python web frameworks.",
                "methodology": "Sources were collected via web search and cross-checked.",
                "key_findings": ["Framework A is lightweight", "Framework B has more features"],
                "detailed_analysis": "Detailed analysis text goes here.",
                "comparison": "Framework A vs Framework B comparison text.",
                "limitations": ["Limited number of sources reviewed"],
                "conclusion": "Both frameworks are solid choices depending on use case.",
            }
        else:
            data = {}
        return ProviderResult(text=json.dumps(data), provider="openai", model="fake-model", raw_json=data)

    async def run_text(self, *, stage, system_prompt, user_prompt, max_tokens=0, temperature=0, usage_recorder=None):
        if usage_recorder:
            usage_recorder(stage=stage, provider="anthropic", model="fake-model", success=True, was_fallback=False, duration_ms=5, error_type=None)
        return ProviderResult(text="This task found solid evidence from the collected sources.", provider="anthropic", model="fake-model")


def _fake_search_web(query, max_results=5, backend="duckduckgo", tavily_api_key=None):
    from search_tool import SearchResult

    return [
        SearchResult(
            title=f"Example Source {i+1} for {query[:20]}",
            url=f"https://example.com/article-{i+1}",
            snippet=f"This is a snippet with real information about {query[:30]} including some numbers like {2020+i}.",
            domain="example.com",
        )
        for i in range(min(3, max_results))
    ]


@pytest.mark.asyncio
async def test_full_research_pipeline_runs_and_produces_report(client, monkeypatch):
    import search_tool
    import tools

    monkeypatch.setattr(search_tool, "search_web", _fake_search_web)
    monkeypatch.setattr(tools, "search_web", _fake_search_web, raising=False)

    from database import session_scope
    from models import ResearchSession
    from research_agent import ResearchAgent

    with session_scope() as db:
        session = ResearchSession(
            research_question="Compare Python web frameworks for building APIs",
            mode="quick",
            status="pending",
            max_sources=6,
            max_tasks=2,
        )
        db.add(session)
        db.flush()
        session_id = session.id

    agent = ResearchAgent(session_id, router=_FakeRouter())
    # Patch the agent's tool registry to use our fake search function directly.
    agent.registry.register(
        "search_web",
        "fake search",
        {},
        lambda query, max_results=5: [r.__dict__ for r in _fake_search_web(query, max_results)],
    )

    await agent.run()

    with session_scope() as db:
        result = db.get(ResearchSession, session_id)
        assert result.status == "completed"
        assert result.progress_percent == 100
        assert len(result.tasks) == 2
        assert all(t.status == "completed" for t in result.tasks)
        assert len(result.sources) > 0
        assert result.report is not None
        assert result.report.title == "Python Web Framework Comparison"
        assert len(result.report.conflicts) == 1


@pytest.mark.asyncio
async def test_export_formats_render_from_completed_session(client, monkeypatch):
    """Uses the API's export endpoint against a session created by the pipeline test flow."""
    import search_tool
    import tools

    monkeypatch.setattr(search_tool, "search_web", _fake_search_web)
    monkeypatch.setattr(tools, "search_web", _fake_search_web, raising=False)

    from database import session_scope
    from models import ResearchSession
    from research_agent import ResearchAgent

    with session_scope() as db:
        session = ResearchSession(
            research_question="Compare Python web frameworks for building APIs",
            mode="quick",
            status="pending",
            max_sources=4,
            max_tasks=2,
        )
        db.add(session)
        db.flush()
        session_id = session.id

    agent = ResearchAgent(session_id, router=_FakeRouter())
    agent.registry.register(
        "search_web", "fake search", {}, lambda query, max_results=5: [r.__dict__ for r in _fake_search_web(query, max_results)]
    )
    await agent.run()

    for fmt in ["markdown", "html", "txt", "json", "pdf"]:
        resp = client.post(f"/api/research/{session_id}/export", json={"format": fmt})
        assert resp.status_code == 200, f"{fmt} export failed: {resp.text}"
        assert len(resp.content) > 50
