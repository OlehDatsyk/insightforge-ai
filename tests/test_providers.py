"""Tests for provider configuration detection and selection (sections 3, 24)."""
import os

from config import Settings
from provider_router import ProviderRouter


def test_no_providers_configured_by_default():
    settings = Settings(openai_api_key=None, anthropic_api_key=None, gemini_api_key=None)
    assert settings.configured_providers == []


def test_configured_providers_detected():
    settings = Settings(openai_api_key="sk-test", anthropic_api_key=None, gemini_api_key="g-test")
    assert set(settings.configured_providers) == {"openai", "gemini"}


def test_fallback_chain_deduplicates():
    settings = Settings(primary_ai_provider="openai", fallback_ai_provider="openai", secondary_fallback_ai_provider="gemini")
    assert settings.fallback_chain == ["openai", "gemini"]


def test_provider_status_reports_all_three_vendors():
    settings = Settings(openai_api_key="sk-test")
    router = ProviderRouter(settings)
    status = router.provider_status()
    names = {s["name"] for s in status}
    assert names == {"openai", "anthropic", "gemini"}
    openai_status = next(s for s in status if s["name"] == "openai")
    assert openai_status["configured"] is True
    anthropic_status = next(s for s in status if s["name"] == "anthropic")
    assert anthropic_status["configured"] is False


def test_ordered_chain_only_includes_configured_providers():
    settings = Settings(
        openai_api_key=None,
        anthropic_api_key="claude-key",
        gemini_api_key="gemini-key",
        primary_ai_provider="openai",
        fallback_ai_provider="anthropic",
        secondary_fallback_ai_provider="gemini",
        planning_provider="openai",
    )
    router = ProviderRouter(settings)
    chain = router._ordered_chain_for_stage("planning")
    # openai is preferred but not configured, so it must be excluded
    assert "openai" not in chain
    assert chain[0] == "anthropic"
    assert "gemini" in chain


def test_routing_overrides_change_stage_preference():
    settings = Settings(openai_api_key="k1", anthropic_api_key="k2", gemini_api_key="k3", planning_provider="openai")
    router = ProviderRouter(settings)
    assert router._preferred_for_stage("planning") == "openai"
    router.load_routing_overrides({"planning": "gemini"})
    assert router._preferred_for_stage("planning") == "gemini"
