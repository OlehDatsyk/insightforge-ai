"""
anthropic_provider.py
======================
Anthropic Claude implementation of the AIProvider interface.

Claude does not have a dedicated "JSON mode" the way OpenAI does, so
structured output relies on strict prompting plus the base class's
tolerant JSON extraction (which strips markdown fences etc.).
"""
from __future__ import annotations

import logging
import time

from ai_provider import (
    AIProvider,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResult,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger("insightforge.provider.anthropic")


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None, model: str, timeout: int = 30):
        super().__init__(api_key, model, timeout)
        self._client = None
        if api_key:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.4,
    ) -> ProviderResult:
        return await self._call(system_prompt, user_prompt, max_tokens, temperature)

    async def _call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        if not self._client:
            raise ProviderAuthError("anthropic", "Anthropic API key is not configured.")

        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        started = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=self.model,
                system=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except AuthenticationError as exc:
            raise ProviderAuthError("anthropic", "Anthropic authentication failed.") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError("anthropic", "Anthropic rate limit or quota exceeded.") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("anthropic", "Anthropic request timed out.") from exc
        except (APIConnectionError, APIStatusError) as exc:
            raise ProviderUnavailableError("anthropic", "Anthropic service unavailable.") from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        logger.info("anthropic call completed in %sms model=%s", elapsed_ms, self.model)
        return ProviderResult(text=text, provider="anthropic", model=self.model, usage=usage)
