"""
openai_provider.py
===================
OpenAI implementation of the AIProvider interface.

Uses the official ``openai`` SDK's async client and native JSON-mode
structured output (``response_format={"type": "json_object"}``) for
reliability, falling back to the base class's best-effort JSON extraction
only if that mode is unavailable for the configured model.
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

logger = logging.getLogger("insightforge.provider.openai")


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None, model: str, timeout: int = 30):
        super().__init__(api_key, model, timeout)
        self._client = None
        if api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.4,
    ) -> ProviderResult:
        return await self._call(system_prompt, user_prompt, max_tokens, temperature, json_mode=False)

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> ProviderResult:
        full_prompt = (
            f"{user_prompt}\n\nRespond with a single JSON object matching this shape:\n{schema_hint}"
        )
        result = await self._call(system_prompt, full_prompt, max_tokens, temperature, json_mode=True)
        result.raw_json = self._extract_json(result.text, provider=self.name)
        return result

    async def _call(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> ProviderResult:
        if not self._client:
            raise ProviderAuthError("openai", "OpenAI API key is not configured.")

        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        started = time.monotonic()
        try:
            kwargs: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise ProviderAuthError("openai", "OpenAI authentication failed.") from exc
        except RateLimitError as exc:
            raise ProviderRateLimitError("openai", "OpenAI rate limit or quota exceeded.") from exc
        except APITimeoutError as exc:
            raise ProviderTimeoutError("openai", "OpenAI request timed out.") from exc
        except (APIConnectionError, APIError) as exc:
            raise ProviderUnavailableError("openai", "OpenAI service unavailable.") from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        logger.info("openai call completed in %sms model=%s", elapsed_ms, self.model)
        return ProviderResult(text=text, provider="openai", model=self.model, usage=usage)
