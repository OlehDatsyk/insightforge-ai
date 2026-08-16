"""Tests for the tool-calling infrastructure and agent loop safety (sections 10, 27)."""
import pytest

from tools import ToolCallLimitExceeded, ToolExecutionError, ToolRegistry, calculate, get_current_date


def test_calculate_basic_arithmetic():
    assert calculate("2 + 2") == 4
    assert calculate("(100 - 80) / 80 * 100") == 25.0


def test_calculate_rejects_unsafe_expressions():
    with pytest.raises(ValueError):
        calculate("__import__('os').system('echo hi')")


def test_get_current_date_format():
    date_str = get_current_date()
    assert len(date_str) == 10
    assert date_str.count("-") == 2


def test_tool_registry_executes_registered_tool():
    registry = ToolRegistry(max_calls=5)
    registry.register("double", "doubles a number", {"n": "number"}, lambda n: n * 2)
    assert registry.execute("double", n=4) == 8
    assert registry.call_count == 1


def test_tool_registry_unknown_tool_raises():
    registry = ToolRegistry(max_calls=5)
    with pytest.raises(ToolExecutionError):
        registry.execute("does_not_exist")


def test_tool_registry_enforces_call_limit():
    registry = ToolRegistry(max_calls=2)
    registry.register("noop", "does nothing", {}, lambda: True)
    registry.execute("noop")
    registry.execute("noop")
    with pytest.raises(ToolCallLimitExceeded):
        registry.execute("noop")


def test_tool_registry_logs_failed_calls():
    registry = ToolRegistry(max_calls=5)

    def boom():
        raise RuntimeError("boom")

    registry.register("boom", "always fails", {}, boom)
    with pytest.raises(ToolExecutionError):
        registry.execute("boom")
    assert registry.call_log[-1]["success"] is False
