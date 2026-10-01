"""Discover, download, and verify monthly Companies House snapshot archives."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

LANDING_PAGE_URL = "http://download.companieshouse.gov.uk/en_output.html"
_PART_RE = re.compile(
    r"^BasicCompanyData-(?P<month>\d{4}-\d{2})-01-part(?P<number>\d+)_(?P<total>\d+)\.zip$"
)


class SnapshotDownloadError(RuntimeError):
    """The published snapshot could not be discovered or downloaded completely."""


@dataclass(frozen=True)
class SnapshotPart:
    month: str
    number: int
    total: int
    filename: str
    url: str


@dataclass(frozen=True)
class DownloadedSnapshot:
    month: str
    parts: tuple[SnapshotPart, ...]
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
    html: str, landing_page_url: str = LANDING_PAGE_URL, month: str | None = None
) -> list[SnapshotPart]:
    """Parse and validate a complete N-of-M part set from the landing page."""
    parser = _LinkParser()
    parser.feed(html)
    by_month: dict[str, list[SnapshotPart]] = {}
    for href in parser.hrefs:
        filename = Path(urlparse(href).path).name
        match = _PART_RE.fullmatch(filename)
        if not match:
            continue
        values = match.groupdict()
        part = SnapshotPart(
            month=values["month"],
            number=int(values["number"]),
            total=int(values["total"]),
            filename=filename,
            url=urljoin(landing_page_url, href),
        )
        by_month.setdefault(part.month, []).append(part)

    if not by_month:
        raise SnapshotDownloadError(
            "landing page contains no BasicCompanyData-YYYY-MM-01-partN_M.zip links"
        )
    selected_month = month or max(by_month)
    if selected_month not in by_month:
        available = ", ".join(sorted(by_month))
        raise SnapshotDownloadError(
            f"snapshot month {selected_month} not found on landing page (available: {available})"
        )
    parts = by_month[selected_month]
    totals = {part.total for part in parts}
    if len(totals) != 1:
        raise SnapshotDownloadError(f"snapshot {selected_month} has inconsistent part totals")
    total = totals.pop()
    by_number = {part.number: part for part in parts}
    if len(by_number) != len(parts) or set(by_number) != set(range(1, total + 1)):
        found = ", ".join(str(number) for number in sorted(by_number))
        raise SnapshotDownloadError(
            f"snapshot {selected_month} is incomplete: expected parts 1..{total}, found {found}"
        )
    return [by_number[number] for number in range(1, total + 1)]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _response_ok(response, context: str) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SnapshotDownloadError(f"{context} failed: {exc}") from exc


def download_snapshot(
    cache_dir: str | Path,
    month: str | None = None,
    *,
    landing_page_url: str = LANDING_PAGE_URL,
    session=None,
) -> DownloadedSnapshot:
    """Discover and cache every published archive for a snapshot month."""
    client = session or requests.Session()
    try:
        landing = client.get(landing_page_url, timeout=60)
    except requests.RequestException as exc:
        raise SnapshotDownloadError(f"landing-page download failed: {exc}") from exc
    _response_ok(landing, "landing-page download")
    try:
        parts = discover_parts(landing.text, landing_page_url, month)
    finally:
        if hasattr(landing, "close"):
            landing.close()

    root = Path(cache_dir) / parts[0].month
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for part in parts:
        path = root / part.filename
        try:
            response = client.get(part.url, timeout=300, stream=True)
        except requests.RequestException as exc:
            raise SnapshotDownloadError(f"download failed for {part.url}: {exc}") from exc
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
                    raise SnapshotDownloadError(
                        f"size mismatch for {part.filename}: expected {expected_size}, "
                        f"got {temporary.stat().st_size}"
                    )
                temporary.replace(path)
            except requests.RequestException as exc:
                raise SnapshotDownloadError(f"download failed for {part.url}: {exc}") from exc
            finally:
                if temporary.exists():
                    temporary.unlink()
        finally:
            if hasattr(response, "close"):
                response.close()
        paths.append(path)
        print(f"snapshot part {part.number}/{part.total}: {part.filename}")
    return DownloadedSnapshot(parts[0].month, tuple(parts), tuple(paths))
