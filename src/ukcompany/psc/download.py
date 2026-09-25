"""Discover, download, and archive Companies House PSC bulk snapshot parts.

Mirrors `ukcompany.snapshot.download`'s pattern (BasicCompanyData), adapted for a
date-keyed (not month-keyed) part set. Companies House serves only the *current* day's
PSC snapshot (confirmed live during the recon behind `docs/recon-psc.md` — a snapshot
date is no longer available the next day), so `date=None` always means "whatever date is
currently published", not a specific historical date.

Zips are the archive: this module never extracts or deletes them. `ukcompany.psc.loader`
reads directly from the `.zip` parts (or already-extracted `.txt` parts, for the case
where an operator has kept both) without a separate extraction step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from ukcompany.snapshot.download import sha256_file  # noqa: F401 (re-exported for callers)

PSC_LANDING_PAGE_URL = "https://download.companieshouse.gov.uk/en_pscdata.html"
_PART_RE = re.compile(
    r"^psc-snapshot-(?P<date>\d{4}-\d{2}-\d{2})_(?P<number>\d+)of(?P<total>\d+)\.zip$"
)


class PscDownloadError(RuntimeError):
    """The published PSC snapshot could not be discovered or downloaded completely."""


@dataclass(frozen=True)
class PscPart:
    date: str
    number: int
    total: int
    filename: str
    url: str


@dataclass(frozen=True)
class DownloadedPscSnapshot:
    date: str
    parts: tuple[PscPart, ...]
    paths: tuple[Path, ...]


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def discover_parts(
    html: str, landing_page_url: str = PSC_LANDING_PAGE_URL, date: str | None = None
) -> list[PscPart]:
    """Parse and validate a complete N-of-N part set from the landing page for one date."""
    parser = _LinkParser()
    parser.feed(html)
    by_date: dict[str, list[PscPart]] = {}
    for href in parser.hrefs:
        filename = Path(urlparse(href).path).name
        match = _PART_RE.fullmatch(filename)
        if not match:
            continue
        values = match.groupdict()
        part = PscPart(
            date=values["date"],
            number=int(values["number"]),
            total=int(values["total"]),
            filename=filename,
            url=urljoin(landing_page_url, href),
        )
        by_date.setdefault(part.date, []).append(part)

    if not by_date:
        raise PscDownloadError(
            "landing page contains no psc-snapshot-YYYY-MM-DD_KofN.zip links"
        )
    selected_date = date or max(by_date)
    if selected_date not in by_date:
        available = ", ".join(sorted(by_date))
        raise PscDownloadError(
            f"PSC snapshot date {selected_date} not found on landing page "
            f"(available: {available})"
        )
    parts = by_date[selected_date]
    totals = {part.total for part in parts}
    if len(totals) != 1:
        raise PscDownloadError(f"PSC snapshot {selected_date} has inconsistent part totals")
    total = totals.pop()
    by_number = {part.number: part for part in parts}
    if len(by_number) != len(parts) or set(by_number) != set(range(1, total + 1)):
        found = ", ".join(str(number) for number in sorted(by_number))
        raise PscDownloadError(
            f"PSC snapshot {selected_date} is incomplete: expected parts 1..{total}, "
            f"found {found}"
        )
    return [by_number[number] for number in range(1, total + 1)]


def _response_ok(response, context: str) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PscDownloadError(f"{context} failed: {exc}") from exc


def download_snapshot(
    cache_dir: str | Path,
    date: str | None = None,
    *,
    landing_page_url: str = PSC_LANDING_PAGE_URL,
    session=None,
) -> DownloadedPscSnapshot:
    """Discover and cache every published PSC part for one date. Zips are kept, never
    extracted or deleted here — that is the whole point of Task A's archive."""
    client = session or requests.Session()
    try:
        landing = client.get(landing_page_url, timeout=60)
    except requests.RequestException as exc:
        raise PscDownloadError(f"landing-page download failed: {exc}") from exc
    _response_ok(landing, "landing-page download")
    try:
        parts = discover_parts(landing.text, landing_page_url, date)
    finally:
        if hasattr(landing, "close"):
            landing.close()

    root = Path(cache_dir) / parts[0].date
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for part in parts:
        path = root / part.filename
        try:
            response = client.get(part.url, timeout=300, stream=True)
        except requests.RequestException as exc:
            raise PscDownloadError(f"download failed for {part.url}: {exc}") from exc
        try:
            _response_ok(response, f"download of {part.filename}")
            expected = response.headers.get("Content-Length")
            expected_size = int(expected) if expected and expected.isdigit() else None
            if path.exists() and expected_size is not None and path.stat().st_size == expected_size:
                paths.append(path)
                continue
            temporary = path.with_suffix(".zip.tmp")
            try:
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
                if expected_size is not None and temporary.stat().st_size != expected_size:
                    raise PscDownloadError(
                        f"size mismatch for {part.filename}: expected {expected_size}, "
                        f"got {temporary.stat().st_size}"
                    )
                temporary.replace(path)
            except requests.RequestException as exc:
                raise PscDownloadError(f"download failed for {part.url}: {exc}") from exc
            finally:
                if temporary.exists():
                    temporary.unlink()
        finally:
            if hasattr(response, "close"):
                response.close()
        paths.append(path)
        print(f"PSC snapshot part {part.number}/{part.total}: {part.filename}")
    return DownloadedPscSnapshot(parts[0].date, tuple(parts), tuple(paths))
