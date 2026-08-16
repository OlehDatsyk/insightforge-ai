"""Tests for the tolerant JSON extraction used by structured AI output (section 8)."""
import pytest

from ai_provider import AIProvider, StructuredOutputParseError


def test_extract_json_plain():
    data = AIProvider._extract_json('{"a": 1, "b": "two"}', provider="test")
    assert data == {"a": 1, "b": "two"}


def test_extract_json_with_markdown_fence():
    text = '```json\n{"a": 1}\n```'
    data = AIProvider._extract_json(text, provider="test")
    assert data == {"a": 1}


def test_extract_json_with_surrounding_commentary():
    text = 'Sure! Here is the JSON:\n{"a": 1, "nested": {"b": 2}}\nHope that helps.'
    data = AIProvider._extract_json(text, provider="test")
    assert data["a"] == 1
    assert data["nested"]["b"] == 2


def test_extract_json_invalid_raises():
    with pytest.raises(StructuredOutputParseError):
        AIProvider._extract_json("this is not json at all", provider="test")
