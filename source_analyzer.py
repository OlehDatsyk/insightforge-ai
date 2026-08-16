"""
source_analyzer.py
===================
Two responsibilities:

1. **Heuristic source quality scoring** (section 13) - authority, relevance,
   recency, evidence quality, and bias risk, computed from cheap signals
   (domain reputation, snippet content, publish date) without any extra AI
   calls. This runs on every collected source.

2. **AI-assisted conflict detection** (section 14) - after sources for a
   research task have been summarized, ask the "crosscheck" provider to
   compare them and flag factual disagreements (e.g. different prices,
   dates, statistics) instead of silently picking one source's version.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from provider_router import ProviderRouter
from schemas import ConflictItem

logger = logging.getLogger("insightforge.analyzer")

HIGH_AUTHORITY_TLDS = (".gov", ".edu")
HIGH_AUTHORITY_DOMAINS = (
    "wikipedia.org",
    "reuters.com",
    "apnews.com",
    "nature.com",
    "sciencedirect.com",
    "ieee.org",
    "bbc.com",
    "nytimes.com",
    "bloomberg.com",
    "wsj.com",
    "github.com",
    "stackoverflow.com",
    "docs.python.org",
)
LOW_AUTHORITY_HINTS = ("blogspot.", "medium.com/@", "quora.com", "pinterest.")

DATE_PATTERN = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})")


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _authority_score(domain: str) -> float:
    if any(domain.endswith(tld) for tld in HIGH_AUTHORITY_TLDS):
        return 0.95
    if any(d in domain for d in HIGH_AUTHORITY_DOMAINS):
        return 0.9
    if any(h in domain for h in LOW_AUTHORITY_HINTS):
        return 0.35
    return 0.6  # neutral default for unrecognized but plausible domains


def _relevance_score(query: str, title: str, snippet: str) -> float:
    query_terms = {t.lower() for t in re.findall(r"\w+", query) if len(t) > 2}
    if not query_terms:
        return 0.5
    text = f"{title} {snippet}".lower()
    hits = sum(1 for t in query_terms if t in text)
    return round(min(1.0, hits / max(1, len(query_terms))), 2)


def _recency_score(published_date: str | None) -> float:
    if not published_date:
        return 0.5  # unknown recency: neutral, not penalized
    match = DATE_PATTERN.search(published_date)
    if not match:
        return 0.5
    try:
        year, month, day = (int(x) for x in match.groups())
        published = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    age_days = (datetime.now(timezone.utc) - published).days
    if age_days < 0:
        return 0.5
    if age_days <= 180:
        return 1.0
    if age_days <= 365:
        return 0.8
    if age_days <= 365 * 2:
        return 0.6
    if age_days <= 365 * 5:
        return 0.4
    return 0.2


def _evidence_score(snippet: str) -> float:
    if not snippet:
        return 0.3
    has_numbers = bool(re.search(r"\d", snippet))
    length_score = min(1.0, len(snippet) / 400)
    return round(0.4 + (0.3 if has_numbers else 0) + 0.3 * length_score, 2)


def _bias_risk(domain: str) -> str:
    if any(domain.endswith(tld) for tld in HIGH_AUTHORITY_TLDS) or any(d in domain for d in HIGH_AUTHORITY_DOMAINS):
        return "low"
    if any(h in domain for h in LOW_AUTHORITY_HINTS):
        return "high"
    return "medium"


def score_source(*, query: str, title: str, url: str, snippet: str, published_date: str | None = None) -> dict:
    """Compute heuristic quality scores for a single source. No AI call, no network access."""
    domain = _domain_of(url)
    authority = _authority_score(domain)
    relevance = _relevance_score(query, title, snippet)
    recency = _recency_score(published_date)
    evidence = _evidence_score(snippet)
    bias = _bias_risk(domain)

    overall = round(0.35 * authority + 0.30 * relevance + 0.15 * recency + 0.20 * evidence, 3)
    if overall >= 0.7 and bias in ("low", "medium"):
        trust_label = "verified"
    elif overall < 0.4 or bias == "high":
        trust_label = "uncertain"
    else:
        trust_label = "uncertain"

    return {
        "domain": domain,
        "authority_score": authority,
        "relevance_score": relevance,
        "recency_score": recency,
        "evidence_score": evidence,
        "bias_risk": bias,
        "overall_quality": overall,
        "trust_label": trust_label,
    }


CROSSCHECK_SYSTEM_PROMPT = (
    "You are the cross-checking module of InsightForge AI. You compare summaries from "
    "multiple independently-collected sources about the same research question and "
    "identify factual disagreements (different numbers, dates, claims, or conclusions). "
    "You do NOT silently pick a winner - you report the disagreement and both source's "
    "values. If sources agree or there isn't enough overlapping detail to compare, return "
    "an empty conflicts list. Always respond with valid JSON only."
)

CROSSCHECK_SCHEMA_HINT = """{
  "conflicts": [
    {
      "topic": "<short label for what disagrees, e.g. 'Subscription price'>",
      "description": "<one sentence explaining the disagreement>",
      "source_a_title": "<title>",
      "source_a_value": "<claim/value from source A>",
      "source_b_title": "<title>",
      "source_b_value": "<claim/value from source B>"
    }
  ]
}"""


async def detect_conflicts(
    router: ProviderRouter,
    *,
    research_question: str,
    sources: list[dict],
    usage_recorder=None,
) -> list[ConflictItem]:
    """Ask the crosscheck provider to compare source summaries and flag conflicts.

    ``sources`` is a list of dicts with at least ``title`` and ``summary`` keys.
    Returns an empty list (never raises) if there are too few sources to compare
    or if the provider call fails - conflict detection is a best-effort
    enhancement, not a hard requirement for producing a report.
    """
    if len(sources) < 2:
        return []

    source_block = "\n\n".join(
        f"Source: {s.get('title', 'Untitled')}\nSummary: {s.get('summary', '')[:600]}" for s in sources[:12]
    )
    user_prompt = (
        f'Research question: "{research_question}"\n\n'
        f"Here are summaries from {len(sources)} sources:\n\n{source_block}\n\n"
        "Identify any factual conflicts between these sources."
    )

    try:
        result = await router.run_structured(
            stage="crosscheck",
            system_prompt=CROSSCHECK_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema_hint=CROSSCHECK_SCHEMA_HINT,
            max_tokens=1200,
            temperature=0.1,
            usage_recorder=usage_recorder,
        )
    except Exception as exc:  # noqa: BLE001 - conflict detection must never break the pipeline
        logger.warning("conflict detection skipped: %s", type(exc).__name__)
        return []

    raw_conflicts = (result.raw_json or {}).get("conflicts", [])
    conflicts: list[ConflictItem] = []
    for c in raw_conflicts:
        try:
            conflicts.append(ConflictItem.model_validate(c))
        except Exception:  # noqa: BLE001
            continue
    return conflicts
