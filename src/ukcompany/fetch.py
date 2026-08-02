"""Fetch orchestration: input list -> cached raw responses. Resumable.

v1 endpoints:
  profile     GET /company/{number}            (always)
  insolvency  GET /company/{number}/insolvency (only when the profile carries an
                                                insolvency link - per plan, the
                                                flag must carry case-level
                                                evidence, not just a boolean)

Officers / filing-history / PSC are phase 1.1: they paginate (35-100 items per
page) and are deliberately not half-implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .cache import RawCache
from .client import CHClient

log = logging.getLogger(__name__)

PROFILE = "profile"
INSOLVENCY = "insolvency"

_PATHS = {
    PROFILE: "/company/{number}",
    INSOLVENCY: "/company/{number}/insolvency",
}


@dataclass
class FetchStats:
    fetched: int = 0
    from_cache: int = 0
    not_found: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"fetched: {self.fetched}  cache hits: {self.from_cache}  "
            f"not found: {len(self.not_found)}  errors: {len(self.errors)}"
        ]
        lines += [f"  NOT FOUND {n}" for n in self.not_found]
        lines += [f"  ERROR {n}: {e}" for n, e in self.errors]
        return "\n".join(lines)


def _fetch_one(
    client: CHClient, cache: RawCache, number: str, endpoint: str, max_age_days: float
) -> tuple[bool, dict | None]:
    """Returns (was_network_fetch, data). Cached 404 -> (False, None)."""
    if cache.is_fresh(number, endpoint, max_age_days):
        cached = cache.read(number, endpoint)
        assert cached is not None
        return False, cached.data
    resp = client.get(_PATHS[endpoint].format(number=number))
    cache.write(number, endpoint, resp.status_code, resp.url, resp.json, etag=resp.etag)
    return True, resp.json


def fetch_companies(
    client: CHClient,
    cache: RawCache,
    numbers: list[str],
    max_age_days: float = 7.0,
) -> FetchStats:
    """Fetch profiles (+ insolvency resource where linked) for a list of numbers.

    Fail-soft per company: one bad number must not kill a 500-company run.
    Errors are collected and reported, never swallowed silently.
    """
    stats = FetchStats()
    for i, number in enumerate(numbers, 1):
        try:
            was_fetch, profile = _fetch_one(client, cache, number, PROFILE, max_age_days)
            stats.fetched += int(was_fetch)
            stats.from_cache += int(not was_fetch)
            if profile is None:
                stats.not_found.append(number)
                continue
            links = profile.get("links") or {}
            if links.get("insolvency"):
                was_fetch_i, _ = _fetch_one(client, cache, number, INSOLVENCY, max_age_days)
                stats.fetched += int(was_fetch_i)
                stats.from_cache += int(not was_fetch_i)
        except Exception as exc:  # noqa: BLE001 - collected and reported, run continues
            log.warning("fetch failed for %s: %s", number, exc)
            stats.errors.append((number, str(exc)))
        if i % 50 == 0:
            log.info("progress: %d/%d", i, len(numbers))
    return stats
