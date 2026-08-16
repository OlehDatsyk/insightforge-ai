"""
search_tool.py
===============
Real web search + webpage fetching, used by the ``search_web`` and
``fetch_webpage`` tools.

* Search defaults to DuckDuckGo via the ``ddgs`` package, which requires no
  API key and performs genuine web searches (no simulated/fake results).
  If ``TAVILY_API_KEY`` is set and ``SEARCH_BACKEND=tavily``, Tavily's
  search API is used instead for higher-quality, citation-friendly results.
* Webpage fetching is polite: it sends a descriptive User-Agent, checks
  ``robots.txt`` before fetching, applies a request timeout, and caps page
  size to avoid downloading huge files.
"""
from __future__ import annotations

import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("insightforge.search")

USER_AGENT = "InsightForgeAI-ResearchBot/1.0 (+https://github.com/; educational research tool)"
MAX_PAGE_BYTES = 1_500_000  # ~1.5MB cap per fetched page
_robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request_time: dict[str, float] = {}
MIN_DELAY_PER_DOMAIN = 1.0  # seconds, basic politeness/rate-limit


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    domain: str


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def search_web(query: str, max_results: int = 8, backend: str = "duckduckgo", tavily_api_key: str | None = None) -> list[SearchResult]:
    """Perform a real web search and return deduplicated results."""
    if backend == "tavily" and tavily_api_key:
        raw = _search_tavily(query, max_results, tavily_api_key)
    else:
        raw = _search_duckduckgo(query, max_results)

    seen_domains: set[str] = set()
    seen_urls: set[str] = set()
    deduped: list[SearchResult] = []
    for r in raw:
        if r.url in seen_urls:
            continue
        # Allow at most 2 results from the same domain to keep source diversity.
        domain_count = sum(1 for d in seen_domains if d == r.domain)
        if domain_count >= 2:
            continue
        seen_urls.add(r.url)
        seen_domains.add(r.domain)
        deduped.append(r)
        if len(deduped) >= max_results:
            break
    return deduped


def _search_duckduckgo(query: str, max_results: int) -> list[SearchResult]:
    try:
        from ddgs import DDGS
    except ImportError:  # pragma: no cover - dependency should always be installed
        logger.error("ddgs package not installed")
        return []

    results: list[SearchResult] = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results * 2, safesearch="moderate"):
                url = item.get("href") or item.get("url") or ""
                if not url:
                    continue
                results.append(
                    SearchResult(
                        title=item.get("title", "").strip() or url,
                        url=url,
                        snippet=(item.get("body") or "").strip(),
                        domain=_domain(url),
                    )
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("duckduckgo search failed: %s", type(exc).__name__)
    return results


def _search_tavily(query: str, max_results: int, api_key: str) -> list[SearchResult]:
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results * 2},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("tavily search failed: %s", type(exc).__name__)
        return []

    results = []
    for item in data.get("results", []):
        url = item.get("url", "")
        if not url:
            continue
        results.append(
            SearchResult(
                title=item.get("title", "").strip() or url,
                url=url,
                snippet=(item.get("content") or "")[:500],
                domain=_domain(url),
            )
        )
    return results


def _robots_allowed(url: str) -> bool:
    """Check robots.txt before fetching a page. Fails open (allows) if robots.txt is unreachable."""
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    rp = _robots_cache.get(root)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{root}/robots.txt")
        try:
            rp.read()
        except Exception:  # noqa: BLE001
            # If robots.txt can't be read, allow the fetch (many sites omit it).
            _robots_cache[root] = rp
            return True
        _robots_cache[root] = rp
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001
        return True


def _respect_rate_limit(domain: str) -> None:
    last = _last_request_time.get(domain, 0)
    elapsed = time.time() - last
    if elapsed < MIN_DELAY_PER_DOMAIN:
        time.sleep(MIN_DELAY_PER_DOMAIN - elapsed)
    _last_request_time[domain] = time.time()


def fetch_webpage(url: str, timeout: int = 12) -> str | None:
    """Fetch a webpage's raw HTML, respecting robots.txt and basic rate limits.

    Returns None if disallowed, unreachable, or not HTML.
    """
    domain = _domain(url)
    if not domain:
        return None
    if not _robots_allowed(url):
        logger.info("robots.txt disallows fetching %s", domain)
        return None

    _respect_rate_limit(domain)
    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    return None
                chunks = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > MAX_PAGE_BYTES:
                        break
                    chunks.append(chunk)
                return b"".join(chunks).decode(resp.encoding or "utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        logger.info("fetch_webpage failed for %s: %s", domain, type(exc).__name__)
        return None


def extract_text(html: str, max_chars: int = 6000) -> str:
    """Extract readable text from raw HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        return text[:max_chars]
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_text failed: %s", type(exc).__name__)
        return ""
