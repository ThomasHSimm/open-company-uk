"""Raw-response cache: the source of truth for everything downstream.

Layout:
  {cache_dir}/{company_number}/{endpoint}.json                     current response
  {cache_dir}/{company_number}/history/{endpoint}.{stamp}.json     superseded responses

Envelope metadata: fetched_at, url, HTTP status, ETag (when the API provides
one), and a sha256 content hash. Refreshes archive the previous response when
content changed (archive-on-change), so register changes remain observable and
past scoring runs stay replayable.

Each file wraps the raw API JSON in an envelope with fetch metadata, so every
derived value is traceable to a response with a timestamp, and re-scoring
after rule changes requires zero network access. 404s are cached too (a
"company not found" is a result, and re-asking the API every run wastes the
rate budget).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _content_hash(data: dict | None) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    company_number: str
    endpoint: str
    status_code: int
    fetched_at: datetime
    url: str
    data: dict | None
    etag: str | None = None
    content_hash: str | None = None

    @property
    def not_found(self) -> bool:
        return self.status_code == 404


class RawCache:
    def __init__(self, cache_dir: str | Path):
        self.root = Path(cache_dir)

    def _path(self, company_number: str, endpoint: str) -> Path:
        return self.root / company_number / f"{endpoint}.json"

    def _history_dir(self, company_number: str) -> Path:
        return self.root / company_number / "history"

    def write(
        self,
        company_number: str,
        endpoint: str,
        status_code: int,
        url: str,
        data: dict | None,
        etag: str | None = None,
    ) -> Path:
        path = self._path(company_number, endpoint)
        path.parent.mkdir(parents=True, exist_ok=True)
        new_hash = _content_hash(data)

        # Archive-on-change: refreshes must not destroy the record of what the
        # register said before. Same content -> overwrite (just a newer
        # fetched_at); changed content -> previous response moves to history/
        # named by its own fetched_at, so source changes stay observable.
        previous = self.read(company_number, endpoint)
        if previous is not None and previous.content_hash != new_hash:
            hist = self._history_dir(company_number)
            hist.mkdir(parents=True, exist_ok=True)
            stamp = previous.fetched_at.strftime("%Y%m%dT%H%M%SZ")
            path.replace(hist / f"{endpoint}.{stamp}.json")

        envelope = {
            "company_number": company_number,
            "endpoint": endpoint,
            "status_code": status_code,
            "fetched_at": datetime.now(UTC).isoformat(),
            "url": url,
            "etag": etag,
            "content_hash": new_hash,
            "data": data,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(envelope, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(path)  # atomic-ish: no half-written cache files on crash
        return path

    def _load(self, path: Path) -> CachedResponse:
        env = json.loads(path.read_text(encoding="utf-8"))
        return CachedResponse(
            company_number=env["company_number"],
            endpoint=env["endpoint"],
            status_code=env["status_code"],
            fetched_at=datetime.fromisoformat(env["fetched_at"]),
            url=env.get("url", ""),
            data=env.get("data"),
            etag=env.get("etag"),
            content_hash=env.get("content_hash", _content_hash(env.get("data"))),
        )

    def read(self, company_number: str, endpoint: str) -> CachedResponse | None:
        path = self._path(company_number, endpoint)
        if not path.exists():
            return None
        return self._load(path)

    def read_history(self, company_number: str, endpoint: str) -> list[CachedResponse]:
        """Superseded responses, oldest first."""
        hist = self._history_dir(company_number)
        if not hist.exists():
            return []
        return [self._load(p) for p in sorted(hist.glob(f"{endpoint}.*.json"))]

    def is_fresh(self, company_number: str, endpoint: str, max_age_days: float) -> bool:
        cached = self.read(company_number, endpoint)
        if cached is None:
            return False
        age = datetime.now(UTC) - cached.fetched_at
        return age <= timedelta(days=max_age_days)

    def all_cached(self, endpoint: str) -> list[CachedResponse]:
        out = []
        if not self.root.exists():
            return out
        for company_dir in sorted(self.root.iterdir()):
            if not company_dir.is_dir():
                continue
            cached = self.read(company_dir.name, endpoint)
            if cached is not None:
                out.append(cached)
        return out
