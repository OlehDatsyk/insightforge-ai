"""
provider_router.py
===================
Ties the provider abstraction layer together:

1. **Fallback system** - for any given call, try the preferred provider
   first; if it fails with a retriable error (rate limit, timeout, quota,
   unavailable model, transient service failure), automatically move to the
   next provider in the configured fallback chain. Non-retriable errors
   (bad API key) also cause an immediate move to the next provider, just
   without wasting retries on it.

2. **Model routing** - different pipeline stages (planning, analysis,
   cross-checking, synthesis) can be assigned to different providers via
   ``PLANNING_PROVIDER`` / ``ANALYSIS_PROVIDER`` / ``CROSSCHECK_PROVIDER`` /
   ``SYNTHESIS_PROVIDER``. A stage's configured provider is tried first;
   the standard fallback chain is appended after it so a stage never fails
   just because its "favourite" provider is down.

No internal error detail (stack traces, raw exception text, API responses)
ever crosses back to the HTTP layer - callers only see
``AllProvidersFailedError`` with a single friendly message. Full detail is
logged server-side via the standard ``logging`` module.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from ai_provider import AIProvider, ProviderError, ProviderResult
from anthropic_provider import AnthropicProvider
from config import Settings, get_settings
from gemini_provider import GeminiProvider
from openai_provider import OpenAIProvider

logger = logging.getLogger("insightforge.router")

STAGE_ENV_MAP = {
    "planning": "planning_provider",
    "analysis": "analysis_provider",
    "crosscheck": "crosscheck_provider",
    "synthesis": "synthesis_provider",
}


class AllProvidersFailedError(Exception):
    """Raised when every provider in the fallback chain failed.

    ``user_message`` is safe to show directly to end users.
    """

    def __init__(self, user_message: str, attempts: list[dict]):
        self.user_message = user_message
        self.attempts = attempts
        super().__init__(user_message)


class ProviderRouter:
    """Builds provider instances once and orchestrates fallback + routing."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        # Runtime routing overrides (section 25 Settings page). Keys are either
        # a stage name ("planning"/"analysis"/"crosscheck"/"synthesis") or
        # "primary"/"fallback"/"secondary_fallback". Values are provider names.
        # These NEVER include API keys - only which configured provider to
        # prefer for a given role. Persisted in the AppSetting table.
        self._routing_overrides: dict[str, str] = {}
        self._providers: dict[str, AIProvider] = {
            "openai": OpenAIProvider(
                self.settings.openai_api_key, self.settings.openai_model, self.settings.request_timeout_seconds
            ),
            "anthropic": AnthropicProvider(
                self.settings.anthropic_api_key,
                self.settings.anthropic_model,
                self.settings.request_timeout_seconds,
            ),
            "gemini": GeminiProvider(
                self.settings.gemini_api_key, self.settings.gemini_model, self.settings.request_timeout_seconds
            ),
        }

    # ------------------------------------------------------------------
    # Runtime routing overrides (Settings page - section 25)
    # ------------------------------------------------------------------
    def load_routing_overrides(self, overrides: dict[str, str]) -> None:
        """Replace in-memory overrides, e.g. loaded from the AppSetting table at startup."""
        valid_providers = set(self._providers.keys())
        self._routing_overrides = {
            k: v for k, v in overrides.items() if v in valid_providers or v == "auto"
        }

    def get_routing_overrides(self) -> dict[str, str]:
        return dict(self._routing_overrides)

    def _preferred_for_stage(self, stage: str) -> str | None:
        return self._routing_overrides.get(stage) or getattr(self.settings, STAGE_ENV_MAP.get(stage, ""), None)

    def _effective_fallback_chain(self) -> list[str]:
        primary = self._routing_overrides.get("primary", self.settings.primary_ai_provider)
        fallback = self._routing_overrides.get("fallback", self.settings.fallback_ai_provider)
        secondary = self._routing_overrides.get("secondary_fallback", self.settings.secondary_fallback_ai_provider)
        seen: set[str] = set()
        ordered: list[str] = []
        for p in (primary, fallback, secondary):
            if p and p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered

    # ------------------------------------------------------------------
    def provider_status(self) -> list[dict]:
        """Configuration status for every known provider (no API calls made)."""
        roles: dict[str, list[str]] = {}
        for stage in STAGE_ENV_MAP:
            preferred = self._preferred_for_stage(stage)
            roles.setdefault(preferred, []).append(stage)

        out = []
        for name, provider in self._providers.items():
            out.append(
                {
                    "name": name,
                    "configured": provider.is_configured,
                    "model": provider.model,
                    "role": roles.get(name, []),
                }
            )
        return out

    def _ordered_chain_for_stage(self, stage: str) -> list[str]:
        """Preferred provider for a stage, followed by the global fallback chain."""
        preferred = self._preferred_for_stage(stage)
        chain = self._effective_fallback_chain()
        ordered = []
        if preferred and preferred != "auto":
            ordered.append(preferred)
        for p in chain:
            if p not in ordered:
                ordered.append(p)
        # Only attempt providers that are actually configured.
        return [p for p in ordered if self._providers.get(p) and self._providers[p].is_configured]

    # ------------------------------------------------------------------
    async def run_structured(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        usage_recorder=None,
    ) -> ProviderResult:
        return await self._run(
            stage=stage,
            structured=True,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_hint=schema_hint,
            max_tokens=max_tokens,
            temperature=temperature,
            usage_recorder=usage_recorder,
        )

    async def run_text(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.4,
        usage_recorder=None,
    ) -> ProviderResult:
        return await self._run(
            stage=stage,
            structured=False,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_hint="",
            max_tokens=max_tokens,
            temperature=temperature,
            usage_recorder=usage_recorder,
        )

    # ------------------------------------------------------------------
    async def _run(
        self,
        *,
        stage: str,
        structured: bool,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
        max_tokens: int,
        temperature: float,
        usage_recorder,
    ) -> ProviderResult:
        chain = self._ordered_chain_for_stage(stage)
        if not chain:
            raise AllProvidersFailedError(
                "No AI provider is configured. Please add at least one API key "
                "(OpenAI, Anthropic, or Gemini) in your environment configuration.",
                attempts=[],
            )

        chain = chain[: self.settings.provider_fallback_limit]
        attempts: list[dict] = []

        for index, provider_name in enumerate(chain):
            provider = self._providers[provider_name]
            is_fallback = index > 0
            for retry in range(self.settings.max_provider_retries + 1):
                started = time.monotonic()
                try:
                    if structured:
                        result = await asyncio.wait_for(
                            provider.generate_structured(
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                schema_hint=schema_hint,
                                max_tokens=max_tokens,
                                temperature=temperature,
                            ),
                            timeout=self.settings.request_timeout_seconds,
                        )
                    else:
                        result = await asyncio.wait_for(
                            provider.generate_text(
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                max_tokens=max_tokens,
                                temperature=temperature,
                            ),
                            timeout=self.settings.request_timeout_seconds,
                        )

                    duration_ms = int((time.monotonic() - started) * 1000)
                    if is_fallback:
                        logger.warning(
                            "provider fallback succeeded: stage=%s provider=%s attempt=%s",
                            stage,
                            provider_name,
                            index,
                        )
                    if usage_recorder:
                        usage_recorder(
                            stage=stage,
                            provider=provider_name,
                            model=provider.model,
                            success=True,
                            was_fallback=is_fallback,
                            duration_ms=duration_ms,
                            error_type=None,
                        )
                    return result

                except asyncio.TimeoutError:
                    error_type = "timeout"
                    retriable = True
                except ProviderError as exc:
                    error_type = type(exc).__name__
                    retriable = exc.retriable
                except Exception as exc:  # noqa: BLE001 - defensive: unknown SDK error
                    logger.exception("unexpected provider error stage=%s provider=%s", stage, provider_name)
                    error_type = "unexpected_error"
                    retriable = True

                duration_ms = int((time.monotonic() - started) * 1000)
                logger.warning(
                    "provider call failed: stage=%s provider=%s attempt=%s error_type=%s retriable=%s",
                    stage,
                    provider_name,
                    retry,
                    error_type,
                    retriable,
                )
                if usage_recorder:
                    usage_recorder(
                        stage=stage,
                        provider=provider_name,
                        model=provider.model,
                        success=False,
                        was_fallback=is_fallback,
                        duration_ms=duration_ms,
                        error_type=error_type,
                    )
                attempts.append({"provider": provider_name, "attempt": retry, "error_type": error_type})

                if not retriable:
                    break  # move to next provider immediately
                if retry < self.settings.max_provider_retries:
                    await asyncio.sleep(min(2**retry * 0.5, 4))  # bounded exponential backoff
                    continue
                break  # exhausted retries for this provider, move to next

        logger.error("all providers failed for stage=%s attempts=%s", stage, attempts)
        raise AllProvidersFailedError(
            "Our AI research service is temporarily unavailable. Please try again in a few minutes.",
            attempts=attempts,
        )


_router: Optional[ProviderRouter] = None


def get_router() -> ProviderRouter:
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router
