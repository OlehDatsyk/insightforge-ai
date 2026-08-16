"""
tools.py
========
Tool registry + tool-calling infrastructure used by the research agent.

The agent never "pretends" to search, fetch, or calculate - every action it
takes goes through ``ToolRegistry.execute()``, which dispatches to a real
Python function, enforces the ``MAX_TOOL_CALLS`` safety limit, and logs each
call. Adding a new tool is a matter of writing a function and calling
``registry.register(...)`` - no other code needs to change.
"""
from __future__ import annotations

import ast
import logging
import operator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("insightforge.tools")


class ToolCallLimitExceeded(Exception):
    """Raised when an agent run exceeds MAX_TOOL_CALLS. Prevents infinite loops."""


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute. Safe message only."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str]  # param_name -> human description (used for prompting/UI, not JSON schema strictness)
    handler: Callable[..., Any]


@dataclass
class ToolRegistry:
    """Holds registered tools and enforces the call-count safety limit."""

    max_calls: int = 20
    _tools: dict[str, ToolSpec] = field(default_factory=dict)
    call_count: int = 0
    call_log: list[dict] = field(default_factory=list)

    def register(self, name: str, description: str, parameters: dict[str, str], handler: Callable[..., Any]) -> None:
        self._tools[name] = ToolSpec(name=name, description=description, parameters=parameters, handler=handler)

    def list_tools(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def execute(self, name: str, **kwargs) -> Any:
        if self.call_count >= self.max_calls:
            raise ToolCallLimitExceeded(
                f"Tool call limit ({self.max_calls}) reached for this research session."
            )
        spec = self._tools.get(name)
        if spec is None:
            raise ToolExecutionError(f"Unknown tool: {name}")

        self.call_count += 1
        started = datetime.now(timezone.utc)
        try:
            result = spec.handler(**kwargs)
            self.call_log.append(
                {
                    "tool": name,
                    "args": {k: str(v)[:200] for k, v in kwargs.items()},
                    "success": True,
                    "timestamp": started.isoformat(),
                }
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("tool %s failed: %s", name, type(exc).__name__)
            self.call_log.append(
                {
                    "tool": name,
                    "args": {k: str(v)[:200] for k, v in kwargs.items()},
                    "success": False,
                    "error": type(exc).__name__,
                    "timestamp": started.isoformat(),
                }
            )
            raise ToolExecutionError(f"Tool '{name}' failed: {type(exc).__name__}") from exc


# ----------------------------------------------------------------------------
# Built-in, stateless tools
# ----------------------------------------------------------------------------
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


def calculate(expression: str) -> float:
    """Safely evaluate an arithmetic expression (+ - * / // % ** and parentheses only)."""
    try:
        tree = ast.parse(expression, mode="eval")
        return _safe_eval(tree.body)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid expression: {expression}") from exc


def get_current_date() -> str:
    """Return today's date in ISO format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_default_registry(settings) -> ToolRegistry:
    """Build a ToolRegistry with the core stateless tools registered."""
    from search_tool import extract_text, fetch_webpage, search_web

    registry = ToolRegistry(max_calls=settings.max_tool_calls)

    registry.register(
        "search_web",
        "Search the web for a query and return a list of candidate sources (title, url, snippet, domain).",
        {"query": "search query string", "max_results": "max number of results to return"},
        lambda query, max_results=8: [
            r.__dict__
            for r in search_web(
                query,
                max_results=max_results,
                backend=settings.search_backend,
                tavily_api_key=settings.tavily_api_key,
            )
        ],
    )
    registry.register(
        "fetch_webpage",
        "Fetch the raw HTML of a webpage, respecting robots.txt and rate limits.",
        {"url": "the URL to fetch"},
        lambda url: fetch_webpage(url),
    )
    registry.register(
        "extract_text",
        "Extract readable plain text from raw HTML content.",
        {"html": "raw HTML string", "max_chars": "maximum characters to return"},
        lambda html, max_chars=6000: extract_text(html, max_chars=max_chars),
    )
    registry.register(
        "calculate",
        "Evaluate a basic arithmetic expression.",
        {"expression": "arithmetic expression, e.g. '(100 - 80) / 80 * 100'"},
        calculate,
    )
    registry.register(
        "get_current_date",
        "Get today's date (UTC, ISO format). Useful for recency judgments.",
        {},
        get_current_date,
    )
    return registry
