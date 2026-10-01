"""Companies House Public Data API client.

Rate limit: published limit is 600 requests / 5 minutes per key. We default to
500/300s deliberately - the key may be shared with other tools (MCP servers
etc.) and a 429 storm is worse than running 20% slower.

Auth: HTTP basic with the API key as username, empty password.
Key comes from the CH_API_KEY environment variable only - never from config
files (detect-secrets is in pre-commit for a reason).
"""

from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import requests

BASE_URL = "https://api.company-information.service.gov.uk"

# Conservative vs the published 600/5min. Constant lives in code, not config:
# it is a methodological/politeness choice, not a runtime knob.
RATE_LIMIT_REQUESTS = 500
RATE_LIMIT_WINDOW_S = 300.0

MAX_RETRIES = 5
BACKOFF_BASE_S = 2.0


class CHAuthError(RuntimeError):
    pass


@dataclass
class TokenBucket:
    """Sliding-window limiter. clock/sleep injectable for deterministic tests."""

    capacity: int = RATE_LIMIT_REQUESTS
    window_s: float = RATE_LIMIT_WINDOW_S
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _stamps: deque[float] = field(default_factory=deque)

    def acquire(self) -> None:
        now = self.clock()
        while self._stamps and now - self._stamps[0] >= self.window_s:
            self._stamps.popleft()
        if len(self._stamps) >= self.capacity:
            wait = self.window_s - (now - self._stamps[0])
            if wait > 0:
                self.sleep(wait)
            # After sleeping, evict again from the (advanced) clock.
            now = self.clock()
            while self._stamps and now - self._stamps[0] >= self.window_s:
                self._stamps.popleft()
        self._stamps.append(self.clock())


@dataclass
class APIResponse:
    status_code: int
    json: dict | None
    url: str
    etag: str | None = None

    @property
    def not_found(self) -> bool:
        return self.status_code == 404


class CHClient:
    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        key = api_key or os.environ.get("CH_API_KEY")
        if not key:
            raise CHAuthError(
                "No API key. Set the CH_API_KEY environment variable "
                "(free key from developer.company-information.service.gov.uk)."
            )
        self.session = session or requests.Session()
        self.session.auth = (key, "")
        self.bucket = bucket or TokenBucket()
        self._sleep = sleep

    def get(self, path: str, params: dict | None = None) -> APIResponse:
        """GET with rate limiting and retry on 429/5xx.

        Returns APIResponse for 200 and 404 (404 is a meaningful result - the
        company/resource does not exist - and must be cached, not retried).
        Raises for auth errors and after retry exhaustion.
        """
        url = BASE_URL + path
        last_status = None
        for attempt in range(MAX_RETRIES):
            self.bucket.acquire()
            resp = self.session.get(url, params=params, timeout=30)
            last_status = resp.status_code
            if resp.status_code == 200:
                return APIResponse(200, resp.json(), url, etag=resp.headers.get("ETag"))
            if resp.status_code == 404:
                return APIResponse(404, None, url)
            if resp.status_code in (401, 403):
                raise CHAuthError(f"HTTP {resp.status_code} for {url} - check CH_API_KEY")
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else BACKOFF_BASE_S * (2**attempt)
                self._sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                self._sleep(BACKOFF_BASE_S * (2**attempt))
                continue
            # Unexpected status: fail loudly rather than guess.
            raise RuntimeError(f"Unexpected HTTP {resp.status_code} for {url}")
        raise RuntimeError(f"Retries exhausted for {url} (last status {last_status})")
