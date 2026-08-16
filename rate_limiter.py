"""
rate_limiter.py
================
A small in-memory, fixed-window rate limiter (section 28: "Rate limiting
where practical"). Good enough for a single-process deployment (Render/
Railway free/hobby tiers run one instance); if this app is ever scaled to
multiple instances behind a load balancer, swap this for a shared store
(e.g. Redis) - the interface is intentionally minimal so that's a drop-in
change.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 30, exempt_paths: tuple[str, ...] = ("/static", "/health")):
        super().__init__(app)
        self.limit = requests_per_minute
        self.window_seconds = 60
        self.exempt_paths = exempt_paths
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in self.exempt_paths) or not path.startswith("/api"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self._hits[client_ip]

        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
            )

        bucket.append(now)
        return await call_next(request)
