"""
Tests for the automatic provider fallback system (section 3) - the core
requirement that if the primary provider fails, the app transparently
tries the next configured provider, and only raises a user-friendly error
if every provider fails.
"""
import pytest

from ai_provider import AIProvider, ProviderRateLimitError, ProviderResult
from config import Settings
from provider_router import AllProvidersFailedError, ProviderRouter


class _FailingProvider(AIProvider):
    name = "openai"

    def __init__(self):
        super().__init__(api_key="fake-key", model="fake-model")

    async def generate_text(self, **kwargs):
        raise ProviderRateLimitError("openai", "simulated rate limit")


class _WorkingProvider(AIProvider):
    name = "anthropic"

    def __init__(self):
        super().__init__(api_key="fake-key", model="fake-model")

    async def generate_text(self, **kwargs):
        return ProviderResult(text="synthesized answer", provider="anthropic", model="fake-model")


class _AlwaysAuthFailProvider(AIProvider):
    name = "gemini"

    def __init__(self):
        super().__init__(api_key="fake-key", model="fake-model")

    async def generate_text(self, **kwargs):
        from ai_provider import ProviderAuthError

        raise ProviderAuthError("gemini", "simulated bad key")


@pytest.mark.asyncio
async def test_fallback_moves_to_next_provider_on_failure():
    settings = Settings(
        openai_api_key="k1",
        anthropic_api_key="k2",
        gemini_api_key="k3",
        primary_ai_provider="openai",
        fallback_ai_provider="anthropic",
        secondary_fallback_ai_provider="gemini",
        max_provider_retries=0,
    )
    router = ProviderRouter(settings)
    router._providers["openai"] = _FailingProvider()
    router._providers["anthropic"] = _WorkingProvider()

    result = await router.run_text(stage="synthesis", system_prompt="sys", user_prompt="hi")
    assert result.provider == "anthropic"
    assert result.text == "synthesized answer"


@pytest.mark.asyncio
async def test_all_providers_failed_raises_friendly_error():
    settings = Settings(
        openai_api_key="k1",
        anthropic_api_key="k2",
        gemini_api_key="k3",
        primary_ai_provider="openai",
        fallback_ai_provider="anthropic",
        secondary_fallback_ai_provider="gemini",
        max_provider_retries=0,
    )
    router = ProviderRouter(settings)
    router._providers["openai"] = _FailingProvider()
    router._providers["anthropic"] = _AlwaysAuthFailProvider()
    router._providers["gemini"] = _AlwaysAuthFailProvider()

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.run_text(stage="synthesis", system_prompt="sys", user_prompt="hi")

    # The user-facing message must never contain internal error details.
    assert "simulated" not in exc_info.value.user_message
    assert "temporarily unavailable" in exc_info.value.user_message.lower()


@pytest.mark.asyncio
async def test_no_configured_providers_raises_immediately():
    settings = Settings(openai_api_key=None, anthropic_api_key=None, gemini_api_key=None)
    router = ProviderRouter(settings)
    with pytest.raises(AllProvidersFailedError):
        await router.run_text(stage="planning", system_prompt="sys", user_prompt="hi")
