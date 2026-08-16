"""
logging_config.py
==================
Structured application logging (section 29).

Logs: research session id, provider used, tool used, execution time, errors,
and fallback events (emitted by provider_router.py / research_agent.py).

Never logs: API keys, full user research questions (only a truncated,
non-sensitive preview), or raw provider responses.
"""
from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class SecretRedactionFilter(logging.Filter):
    """Defense-in-depth: strip anything that looks like a bearer token or API key."""

    _PATTERNS = ("sk-", "api_key", "apikey", "authorization", "bearer ")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage()).lower()
        if any(p in msg for p in self._PATTERNS):
            record.msg = "[redacted log message containing potential secret]"
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SecretRedactionFilter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel("WARNING")
