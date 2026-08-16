"""
ai_provider.py
===============
Provider abstraction layer.

Every AI vendor (OpenAI, Anthropic, Gemini, and any future addition such as
Mistral/Groq/DeepSeek/OpenRouter) implements the same ``AIProvider``
interface. Nothing else in the codebase is allowed to import an SDK
(``openai``, ``anthropic``, ``google.genai``) directly - only the provider
modules do. This is what lets ``provider_router.py`` swap providers, retry,
and fall back between them without caring which vendor it is talking to.

Adding a new provider later means: (1) write a class that implements
``AIProvider``, (2) register it in ``provider_router.py``'s provider map,
(3) add its env vars to ``.env.example``. Nothing else changes.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("insightforge.provider")


# ----------------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------------
class ProviderError(Exception):
    """Base class for all provider failures. Safe, non-sensitive message only."""

    def __init__(self, provider: str, message: str, retriable: bool = True):
        self.provider = provider
        self.retriable = retriable
        super().__init__(message)


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    """Bad/missing API key. Not retriable - retrying won't help."""

    def __init__(self, provider: str, message: str):
        super().__init__(provider, message, retriable=False)


class ProviderUnavailableError(ProviderError):
    pass


class StructuredOutputParseError(ProviderError):
    """The provider responded but its output could not be parsed as valid JSON."""


# ----------------------------------------------------------------------------
# Result container
# ----------------------------------------------------------------------------
@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    raw_json: Optional[dict[str, Any]] = None
    usage: dict[str, int] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Base class
# ----------------------------------------------------------------------------
class AIProvider(ABC):
    """Common interface every AI vendor integration must implement."""

    name: str = "base"

    def __init__(self, api_key: Optional[str], model: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.4,
    ) -> ProviderResult:
        """Plain-text completion."""
        raise NotImplementedError

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: str,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> ProviderResult:
        """
        Ask the model for a JSON object matching ``schema_hint`` (a
        human-readable description of the expected JSON shape) and parse it.

        The default implementation appends explicit JSON-only instructions to
        the prompt and parses the response as JSON, tolerating markdown code
        fences. Providers with native JSON modes override this for extra
        reliability.
        """
        json_instruction = (
            f"{user_prompt}\n\n"
            "Respond with ONLY a single valid JSON object - no markdown code "
            "fences, no commentary before or after. Match this shape exactly:\n"
            f"{schema_hint}"
        )
        result = await self.generate_text(
            system_prompt=system_prompt,
            user_prompt=json_instruction,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        result.raw_json = self._extract_json(result.text, provider=self.name)
        return result

    @staticmethod
    def _extract_json(text: str, provider: str) -> dict[str, Any]:
        """Best-effort extraction of a JSON object from model output."""
        candidate = text.strip()

        # Strip ```json ... ``` or ``` ... ``` fences if present.
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1).strip()

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Fall back to grabbing the first {...} block.
        brace_match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError as exc:
                raise StructuredOutputParseError(
                    provider, f"Model output was not valid JSON: {exc}"
                ) from exc

        raise StructuredOutputParseError(provider, "Model output contained no JSON object.")
