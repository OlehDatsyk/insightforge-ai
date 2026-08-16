"""
gemini_provider.py
===================
Google Gemini implementation of the AIProvider interface, using the
``google-genai`` SDK. The SDK's client is synchronous by default, so calls
are dispatched through ``asyncio.to_thread`` to keep the provider interface
async without blocking the event loop.
"""
from __future__ import annotations

import asyncio
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

logger = logging.getLogger("insightforge.provider.gemini")


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str | None, model: str, timeout: int = 30):
        super().__init__(api_key, model, timeout)
        self._client = None
        if api_key:
            from google import genai

            self._client = genai.Client(api_key=api_key)

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
            raise ProviderAuthError("gemini", "Gemini API key is not configured.")

        def _sync_call():
            from google.genai import types
            from google.genai import errors as genai_errors

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
            except genai_errors.ClientError as exc:
                status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if status in (401, 403):
                    raise ProviderAuthError("gemini", "Gemini authentication failed.") from exc
                if status == 429:
                    raise ProviderRateLimitError("gemini", "Gemini rate limit or quota exceeded.") from exc
                raise ProviderUnavailableError("gemini", "Gemini service unavailable.") from exc
            except genai_errors.ServerError as exc:
                raise ProviderUnavailableError("gemini", "Gemini service unavailable.") from exc

        started = time.monotonic()
        try:
            response = await asyncio.wait_for(asyncio.to_thread(_sync_call), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise ProviderTimeoutError("gemini", "Gemini request timed out.") from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = response.text or ""
        usage = {}
        if getattr(response, "usage_metadata", None):
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count or 0,
                "completion_tokens": response.usage_metadata.candidates_token_count or 0,
                "total_tokens": response.usage_metadata.total_token_count or 0,
            }
        logger.info("gemini call completed in %sms model=%s", elapsed_ms, self.model)
        return ProviderResult(text=text, provider="gemini", model=self.model, usage=usage)
