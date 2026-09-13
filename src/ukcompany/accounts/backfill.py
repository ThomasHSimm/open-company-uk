"""Bounded-disk monthly accounts download, extraction, and cleanup."""

from __future__ import annotations

import calendar
import sqlite3
import time
import zipfile
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import requests

from .extract import (
    ArchiveSpec,
    archive_recorded_complete,
    export_archive_parquet,
    parse_archive,
    process_archive,
)

DEFAULT_BASE_URL = "https://download.companieshouse.gov.uk/archive"
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class FetchStatus(StrEnum):
    DOWNLOADED = "downloaded"
    ABSENT = "absent"
    FAILED = "failed"


@dataclass(frozen=True)
class FetchResult:
    status: FetchStatus
    path: Path
    bytes_received: int = 0
    error: str | None = None
    downloaded_this_run: bool = False


class MonthStatus(StrEnum):
    SKIPPED_COMPLETE = "already complete"
    COMPLETED_DELETED = "completed; ZIP deleted"
    COMPLETED_KEPT = "completed; ZIP kept"
    PARTIAL_KEPT = "partial sample; ZIP kept"
    ABSENT = "absent"
    FAILED = "failed"


@dataclass(frozen=True)
class MonthOutcome:
    year: int
    month: int
    archive_name: str
    status: MonthStatus
    manifest_complete: bool = False
    bytes_received: int = 0
    error: str | None = None

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class BackfillSummary:
    outcomes: tuple[MonthOutcome, ...]

    @property
    def has_gaps(self) -> bool:
        return any(
            outcome.status in {MonthStatus.ABSENT, MonthStatus.FAILED}
            for outcome in self.outcomes
        )


def archive_name(year: int, month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1–12, got {month}")
    return f"Accounts_Monthly_Data-{calendar.month_name[month]}{year:04d}.zip"


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", maxsplit=1)
        year, month = int(year_text), int(month_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"month must be YYYY-MM, got {value!r}") from exc
    if len(year_text) != 4 or len(month_text) != 2 or not 1 <= month <= 12:
        raise ValueError(f"month must be YYYY-MM, got {value!r}")
    return year, month


def iter_months(start: tuple[int, int], end: tuple[int, int]) -> Iterator[tuple[int, int]]:
    if start > end:
        raise ValueError("--from must not be later than --to")
    year, month = start
    while (year, month) <= end:
        yield year, month
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1


def cleanup_stale_parts(downloads: str | Path) -> None:
    directory = Path(downloads).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    for part in directory.glob(".Accounts_Monthly_Data-*.zip.part"):
        part.unlink()


def _verified_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        archive.infolist()


def fetch_archive(
    month: int,
    year: int,
    *,
    downloads: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    chunk_size: int = 8 * 1024 * 1024,
    retries: int = 2,
    backoff: float = 5.0,
    timeout: float = 120.0,
    sleep: Callable[[float], None] = time.sleep,
    session: requests.Session | None = None,
) -> FetchResult:
    """Fetch one archive through a verified temporary file without buffering it."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if retries < 0:
        raise ValueError("retries must not be negative")
    name = archive_name(year, month)
    directory = Path(downloads).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    partial = directory / f".{name}.part"
    if partial.exists():
        partial.unlink()
    if destination.exists():
        try:
            _verified_zip(destination)
        except (OSError, zipfile.BadZipFile) as exc:
            return FetchResult(FetchStatus.FAILED, destination, error=f"staged ZIP invalid: {exc}")
        return FetchResult(
            FetchStatus.DOWNLOADED,
            destination,
            bytes_received=destination.stat().st_size,
            downloaded_this_run=False,
        )

    client = session or requests.Session()
    owns_session = session is None
    url = f"{base_url.rstrip('/')}/{name}"
    last_error: str | None = None
    try:
        for attempt in range(retries + 1):
            retryable = True
            received = 0
            try:
                with client.get(url, stream=True, timeout=timeout) as response:
                    if response.status_code == 404:
                        return FetchResult(
                            FetchStatus.ABSENT,
                            destination,
                            error=f"HTTP 404: {url}",
                        )
                    if response.status_code >= 400:
                        retryable = response.status_code in TRANSIENT_HTTP_STATUSES
                        response.raise_for_status()
                    expected_header = response.headers.get("Content-Length")
                    expected = int(expected_header) if expected_header is not None else None
                    with partial.open("wb") as output:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                output.write(chunk)
                                received += len(chunk)
                    if expected is not None and received != expected:
                        raise OSError(
                            f"short download: received {received:,} of {expected:,} bytes"
                        )
                _verified_zip(partial)
                partial.replace(destination)
                return FetchResult(
                    FetchStatus.DOWNLOADED,
                    destination,
                    bytes_received=received,
                    downloaded_this_run=True,
                )
            except (OSError, ValueError, zipfile.BadZipFile, requests.RequestException) as exc:
                last_error = str(exc)
                partial.unlink(missing_ok=True)
                if not retryable or attempt >= retries:
                    break
                sleep(backoff * (2**attempt))
    finally:
        partial.unlink(missing_ok=True)
        if owns_session:
            client.close()
    return FetchResult(FetchStatus.FAILED, destination, received, last_error)


def _write_coverage(path: str | Path | None, outcomes: list[MonthOutcome]) -> None:
    if path is None:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_coverage_report(outcomes), encoding="utf-8")


def _record(
    outcomes: list[MonthOutcome],
    outcome: MonthOutcome,
    report_output: str | Path | None,
) -> None:
    outcomes.append(outcome)
    detail = f": {outcome.error}" if outcome.error else ""
    print(f"[{outcome.label}] {outcome.status}{detail}", flush=True)
    _write_coverage(report_output, outcomes)


def run_backfill(
    connection: sqlite3.Connection,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    downloads: str | Path,
    output_dir: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    keep_zips: bool = False,
    limit_per_zip: int | None = None,
    chunk_size: int = 8 * 1024 * 1024,
    retries: int = 2,
    backoff: float = 5.0,
    timeout: float = 120.0,
    report_output: str | Path | None = None,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> BackfillSummary:
    """Serially fetch, extract, and conditionally delete an inclusive month range."""
    if limit_per_zip is not None and limit_per_zip <= 0:
        raise ValueError("limit_per_zip must be positive")
    months = tuple(iter_months(start, end))
    cleanup_stale_parts(downloads)
    outcomes: list[MonthOutcome] = []
    for year, month in months:
        name = archive_name(year, month)
        if archive_recorded_complete(connection, name, scope=scope, kinds=kinds):
            try:
                export_archive_parquet(
                    connection,
                    name,
                    output_dir,
                    overwrite=False,
                    scope=scope,
                    kinds=kinds,
                )
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
                _record(
                    outcomes,
                    MonthOutcome(
                        year,
                        month,
                        name,
                        MonthStatus.FAILED,
                        manifest_complete=True,
                        error=f"monthly export failed: {exc}",
                    ),
                    report_output,
                )
                continue
            _record(
                outcomes,
                MonthOutcome(year, month, name, MonthStatus.SKIPPED_COMPLETE, True),
                report_output,
            )
            continue
        fetched = fetch_archive(
            month,
            year,
            downloads=downloads,
            base_url=base_url,
            chunk_size=chunk_size,
            retries=retries,
            backoff=backoff,
            timeout=timeout,
        )
        if fetched.status == FetchStatus.ABSENT:
            _record(
                outcomes,
                MonthOutcome(
                    year,
                    month,
                    name,
                    MonthStatus.ABSENT,
                    bytes_received=fetched.bytes_received,
                    error=fetched.error,
                ),
                report_output,
            )
            continue
        if fetched.status == FetchStatus.FAILED:
            _record(
                outcomes,
                MonthOutcome(
                    year,
                    month,
                    name,
                    MonthStatus.FAILED,
                    bytes_received=fetched.bytes_received,
                    error=fetched.error,
                ),
                report_output,
            )
            continue

        archive: ArchiveSpec = parse_archive(fetched.path)
        try:
            process_archive(
                connection,
                archive,
                limit=limit_per_zip,
                scope=scope,
                kinds=kinds,
            )
        except AssertionError as exc:
            _record(
                outcomes,
                MonthOutcome(year, month, name, MonthStatus.FAILED, error=str(exc)),
                report_output,
            )
            raise
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, sqlite3.Error) as exc:
            _record(
                outcomes,
                MonthOutcome(year, month, name, MonthStatus.FAILED, error=str(exc)),
                report_output,
            )
            continue

        complete = archive_recorded_complete(connection, name, scope=scope, kinds=kinds)
        if limit_per_zip is not None:
            _record(
                outcomes,
                MonthOutcome(
                    year,
                    month,
                    name,
                    MonthStatus.PARTIAL_KEPT,
                    bytes_received=fetched.bytes_received,
                ),
                report_output,
            )
            continue
        if not complete:
            _record(
                outcomes,
                MonthOutcome(
                    year,
                    month,
                    name,
                    MonthStatus.FAILED,
                    error="extraction returned without a complete manifest row",
                ),
                report_output,
            )
            continue
        try:
            export_archive_parquet(
                connection,
                name,
                output_dir,
                scope=scope,
                kinds=kinds,
            )
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            _record(
                outcomes,
                MonthOutcome(
                    year,
                    month,
                    name,
                    MonthStatus.FAILED,
                    manifest_complete=True,
                    bytes_received=fetched.bytes_received,
                    error=f"monthly export failed: {exc}",
                ),
                report_output,
            )
            continue
        if fetched.downloaded_this_run and not keep_zips:
            try:
                fetched.path.unlink()
            except OSError as exc:
                _record(
                    outcomes,
                    MonthOutcome(
                        year,
                        month,
                        name,
                        MonthStatus.FAILED,
                        manifest_complete=True,
                        bytes_received=fetched.bytes_received,
                        error=f"extracted, but ZIP deletion failed: {exc}",
                    ),
                    report_output,
                )
                continue
            status = MonthStatus.COMPLETED_DELETED
        else:
            status = MonthStatus.COMPLETED_KEPT
        _record(
            outcomes,
            MonthOutcome(
                year,
                month,
                name,
                status,
                manifest_complete=complete,
                bytes_received=fetched.bytes_received,
            ),
            report_output,
        )
    _write_coverage(report_output, outcomes)
    return BackfillSummary(tuple(outcomes))


def _list_outcomes(lines: list[str], outcomes: list[MonthOutcome]) -> None:
    if not outcomes:
        lines.append("- _None._")
        return
    for outcome in outcomes:
        suffix = f" — {outcome.error}" if outcome.error else ""
        lines.append(f"- `{outcome.label}` (`{outcome.archive_name}`){suffix}")


def render_coverage_report(outcomes: list[MonthOutcome] | tuple[MonthOutcome, ...]) -> str:
    requested = list(outcomes)
    complete = [outcome for outcome in requested if outcome.manifest_complete]
    deleted = [
        outcome for outcome in requested if outcome.status == MonthStatus.COMPLETED_DELETED
    ]
    kept = [
        outcome for outcome in requested if outcome.status == MonthStatus.COMPLETED_KEPT
    ]
    skipped = [
        outcome for outcome in requested if outcome.status == MonthStatus.SKIPPED_COMPLETE
    ]
    partial = [outcome for outcome in requested if outcome.status == MonthStatus.PARTIAL_KEPT]
    absent = [outcome for outcome in requested if outcome.status == MonthStatus.ABSENT]
    failed = [outcome for outcome in requested if outcome.status == MonthStatus.FAILED]
    covered_labels = sorted(outcome.label for outcome in complete)
    covered_span = (
        f"`{covered_labels[0]}` through `{covered_labels[-1]}`"
        if covered_labels
        else "_none_"
    )
    lines = [
        "# Accounts backfill coverage",
        "",
        "Every requested month is classified explicitly. Absent and failed months are gaps, not successful coverage.",
        "",
        "## Summary",
        "",
        f"- Months requested so far: {len(requested):,}",
        f"- Present and manifest-complete: {len(complete):,}",
        f"- Completed with ZIP deleted: {len(deleted):,}",
        f"- Completed with ZIP kept: {len(kept):,}",
        f"- Previously completed and skipped: {len(skipped):,}",
        f"- Partial development samples: {len(partial):,}",
        f"- Absent: {len(absent):,}",
        f"- Failed: {len(failed):,}",
        f"- Effective covered span: {covered_span}",
        "",
        "## Present and complete",
        "",
    ]
    _list_outcomes(lines, complete)
    lines.extend(["", "## Partial development samples", ""])
    _list_outcomes(lines, partial)
    lines.extend(["", "## Absent months", ""])
    _list_outcomes(lines, absent)
    lines.extend(["", "## Failed months", ""])
    _list_outcomes(lines, failed)
    lines.extend(
        [
            "",
            "## Storage and verification limitations",
            "",
            "- The workflow bounds downloaded-ZIP storage to approximately one monthly archive, but the SQLite store and WAL grow across the run.",
            "- Each monthly Parquet export needs temporary working space in addition to its output file.",
            "- Downloads are checked against `Content-Length` when supplied and must contain a readable ZIP central directory. Companies House publishes no per-file checksum, so cryptographic source verification is unavailable.",
            "- Interrupted downloads restart from byte zero; HTTP range resume and prefetch/parallel extraction are intentionally out of scope for v1.",
            "",
        ]
    )
    return "\n".join(lines)
