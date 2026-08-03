"""Fetch orchestration: input list -> cached raw responses. Resumable.

v1 endpoints:
  profile     GET /company/{number}            (always)
  insolvency  GET /company/{number}/insolvency (only when the profile carries an
                                                insolvency link - per plan, the
                                                flag must carry case-level
                                                evidence, not just a boolean)
  officers    GET /company/{number}/officers   (always, for found companies;
                                                PAGINATES - see _fetch_paginated)
  psc         GET /company/{number}/persons-with-significant-control
  psc_stmts   GET /company/{number}/persons-with-significant-control-statements
                                                (both always, for found
                                                companies; PAGINATE; 404 is a
                                                legitimate "none filed" result
                                                for many companies, not an error)

Filing history remains phase 1.1: it paginates too and is deliberately not
half-implemented here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .cache import RawCache
from .client import CHClient

log = logging.getLogger(__name__)

PROFILE = "profile"
INSOLVENCY = "insolvency"
OFFICERS = "officers"
PSC = "psc"
PSC_STATEMENTS = "psc_statements"

_PATHS = {
    PROFILE: "/company/{number}",
    INSOLVENCY: "/company/{number}/insolvency",
    OFFICERS: "/company/{number}/officers",
    PSC: "/company/{number}/persons-with-significant-control",
    PSC_STATEMENTS: "/company/{number}/persons-with-significant-control-statements",
}

# CH caps items_per_page at 100 on the list endpoints (officers, PSC, ...).
PAGE_SIZE = 100


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


def _fetch_paginated(
    client: CHClient, cache: RawCache, number: str, endpoint: str, max_age_days: float
) -> tuple[bool, dict | None]:
    """Fetch a paginated list resource, merged into ONE cache entry.

    The list endpoints paginate (items_per_page capped at 100). An old PLC can
    carry well over 100 officer appointments, and the truncation failure mode
    the plan warns about is stopping after page one. We page on start_index
    until every item is collected, then store all pages merged under a single
    envelope for `endpoint`: the full list under data["items"], with
    data["total_results"] preserved so downstream code can detect an incomplete
    merge.

    start_index advances by the number of items actually collected so far (not
    a fixed page stride), so a short page cannot leave a gap; a page that comes
    back empty stops the loop even if total_results is overstated.

    A 404 is a legitimate result for several of these resources (many companies
    file no PSC information at all) and is cached, never treated as an error.
    """
    if cache.is_fresh(number, endpoint, max_age_days):
        cached = cache.read(number, endpoint)
        assert cached is not None
        return False, cached.data

    path = _PATHS[endpoint].format(number=number)
    first = client.get(path, params={"items_per_page": PAGE_SIZE, "start_index": 0})
    if first.not_found:
        cache.write(number, endpoint, 404, first.url, None)
        return True, None

    data = dict(first.json or {})
    items = list(data.get("items") or [])
    total = data.get("total_results")
    if total is None:
        total = len(items)

    while len(items) < total:
        resp = client.get(path, params={"items_per_page": PAGE_SIZE, "start_index": len(items)})
        page_items = (resp.json or {}).get("items") or []
        if not page_items:
            break  # total_results overstated or API inconsistency - stop, don't spin
        items.extend(page_items)

    data["items"] = items
    data["total_results"] = total
    cache.write(number, endpoint, first.status_code, first.url, data, etag=first.etag)
    return True, data


def _fetch_officers(
    client: CHClient, cache: RawCache, number: str, max_age_days: float
) -> tuple[bool, dict | None]:
    return _fetch_paginated(client, cache, number, OFFICERS, max_age_days)


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
            for endpoint in (OFFICERS, PSC, PSC_STATEMENTS):
                was_fetch_p, _ = _fetch_paginated(client, cache, number, endpoint, max_age_days)
                stats.fetched += int(was_fetch_p)
                stats.from_cache += int(not was_fetch_p)
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
