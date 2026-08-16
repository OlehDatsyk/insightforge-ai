"""
config.py
=========
Centralized application configuration.

Every configurable value in InsightForge AI flows through this module.
Values are loaded from environment variables (and a local ``.env`` file in
development) via ``pydantic-settings``. Nothing in this file should ever
contain a real secret - see ``.env.example`` for the documented list of
variables an operator must set.

Design notes
------------
* This is the ONLY module allowed to read ``os.environ`` directly (through
  pydantic-settings). Every other module receives configuration through the
  ``get_settings()`` accessor so behaviour stays testable and predictable.
* ``get_settings()`` is cached with ``functools.lru_cache`` so the .env file
  is parsed once per process, not on every request.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "anthropic", "gemini"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "development"
    app_name: str = "InsightForge AI"
    log_level: str = "INFO"
    secret_key: str = "dev-secret-key-change-me"
    allowed_origins: str = "*"
    rate_limit_per_minute: int = 30
    max_request_body_bytes: int = 1_048_576
    port: int = 8000

    # --- Database ---
    database_url: str = "sqlite:///./data/insightforge.db"

    # --- AI provider API keys (never logged, never sent to the frontend) ---
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # --- AI provider models ---
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    gemini_model: str = "gemini-2.0-flash"

    # --- Provider fallback chain ---
    primary_ai_provider: ProviderName = "openai"
    fallback_ai_provider: ProviderName = "anthropic"
    secondary_fallback_ai_provider: ProviderName = "gemini"

    # --- Task -> provider routing (each may be "auto" to follow the chain above) ---
    planning_provider: str = "openai"
    analysis_provider: str = "anthropic"
    crosscheck_provider: str = "gemini"
    synthesis_provider: str = "anthropic"

    # --- Web search ---
    search_backend: Literal["duckduckgo", "tavily"] = "duckduckgo"
    tavily_api_key: Optional[str] = None

    # --- Agent / cost safety limits ---
    max_agent_iterations: int = 10
    max_tool_calls: int = 20
    max_sources: int = 10
    max_research_tasks: int = 8
    max_tokens_per_request: int = 4000
    request_timeout_seconds: int = 30
    max_provider_retries: int = 2
    provider_fallback_limit: int = 3

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------
    @property
    def configured_providers(self) -> list[ProviderName]:
        """Providers that currently have an API key set."""
        result: list[ProviderName] = []
        if self.openai_api_key:
            result.append("openai")
        if self.anthropic_api_key:
            result.append("anthropic")
        if self.gemini_api_key:
            result.append("gemini")
        return result

    def is_configured(self, provider: str) -> bool:
        return provider in self.configured_providers

    @property
    def fallback_chain(self) -> list[ProviderName]:
        """Ordered provider chain, deduplicated, keeping only configured providers."""
        chain = [
            self.primary_ai_provider,
            self.fallback_ai_provider,
            self.secondary_fallback_ai_provider,
        ]
        seen: set[str] = set()
        ordered: list[ProviderName] = []
        for p in chain:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        return ordered

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""
    return Settings()
