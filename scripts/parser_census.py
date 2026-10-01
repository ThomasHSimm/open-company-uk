"""Phase 1 of the accounts-parser check: byte-scan census + 1% company-hash sample.

Per docs/brief's parser-check build prompt. For each monthly Accounts_Monthly_Data ZIP in
scope (2014-01 through 2026-08, 152 months — the stop-rule projection came in at ~4 hours,
under the 8-hour threshold, so full monthly coverage applies, not the quarterly fallback):

1. Download the ZIP if not already on disk (reusing ukcompany.accounts.backfill.fetch_archive
   — the same atomic, verified `.part`-file machinery the production backfill uses).
2. Byte-scan every member matching the production filename pattern (Prod<n>_<batch>_
   <company>_<date>.<ext>) — regex only, no tree parse, deliberately independent of
   core.py's IX_FACT_RE so the census isn't blind to the exact prefix bug it's measuring.
3. Extract every filing where sha256(normalised company number) % 100 == 0 into
   data/accounts/parser-sample/, keeping its original member name.
4. Delete the ZIP afterward, but only if this run downloaded it (a ZIP already on disk
   before this run started is left alone).

Resumable: a month is skipped entirely (no download, no scan) if its census Parquet already
exists at data/accounts/parser-census/<archive_name>.parquet. Re-running this script after an
interruption picks up at the first incomplete month.

Usage:
    python scripts/parser_census.py --from 2014-01 --to 2026-08 --workers 8
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import zipfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from ukcompany.accounts.backfill import (  # noqa: E402
    FetchStatus,
    archive_name,
    iter_months,
    parse_month,
)
from ukcompany.accounts.backfill import fetch_archive as _fetch_archive  # noqa: E402
from ukcompany.accounts.core import ContextKind, extract_contexts  # noqa: E402
from ukcompany.accounts.extract import MEMBER_RE, normalise_company  # noqa: E402

DEFAULT_DOWNLOADS = Path("~/Downloads").expanduser()
CENSUS_DIR = Path("data/accounts/parser-census")
SAMPLE_DIR = Path("data/accounts/parser-sample")
FORMAT_DIR = Path("data/accounts/parser-census-formats")

# Prefix-agnostic by design: the whole point of this census is to measure the prefix bug
# independently of core.py's prefix-locked IX_FACT_RE, so every regex here accepts ANY
# namespace prefix (or none), unlike the production regex it is auditing. Quote-agnostic too
# (`(['"])...\1`, matching core.py's ATTR_RE idiom) — early CH filing software (2013-14
# vintage, confirmed live) wrote `xmlns:ix='...'` with single quotes; the first version of
# this regex was double-quote-only and silently misclassified those filings as "no ix
# binding at all", overstating the bug footprint. Caught via the LONG cross-check turning
# up real rows for filings this census had called bug-affected.
IX_NS_RE = re.compile(
    rb"""xmlns:([A-Za-z][\w.-]*)\s*=\s*(['"])http://www\.xbrl\.org/\d{4}/inlineXBRL\2"""
    rb"""|xmlns\s*=\s*(['"])(http://www\.xbrl\.org/\d{4}/inlineXBRL)\3"""
)
IX_HEADER_RE = re.compile(rb"<\s*(?:[\w.-]+:)?header\b", re.I)
FACT_TAG_EVENT_RE = re.compile(
    rb"<\s*(/?)\s*(?:[\w.-]+:)?(nonFraction|nonNumeric)\b([^>]*?)(/?)\s*>", re.I
)
CONT_EXCL_TAG_RE = re.compile(
    rb"<\s*(/?)\s*(?:[\w.-]+:)?(continuation|exclude)\b([^>]*?)(/?)\s*>", re.I
)
FORMAT_RE = re.compile(rb"""\bformat\s*=\s*"([^"]*)"|\bformat\s*=\s*'([^']*)'""", re.I)


@dataclass
class FilingCensus:
    source_member: str
    company_number: str
    archive_year: int
    archive_month: int
    made_up_to_date: str
    file_extension: str
    ix_prefix: str  # "ix" | "default" | "other:<prefix>" | "none"
    has_ix_header: bool
    n_nonfraction: int
    n_nonnumeric: int
    n_continuation: int
    n_exclude: int
    n_nested_facts: int
    n_multimember_contexts: int
    n_typed_contexts: int


def detect_ix_prefix(data: bytes) -> str:
    match = IX_NS_RE.search(data)
    if not match:
        return "none"
    prefix = match.group(1)
    if prefix is not None:
        text = prefix.decode("ascii", "replace")
        return "ix" if text.lower() == "ix" else f"other:{text}"
    return "default"


def _tag_events(data: bytes, pattern: re.Pattern[bytes]) -> tuple[Counter, int]:
    """Stack-based nesting count for a 2-alternative open/close/self-close tag regex.

    Regex-only (no tree parse): tracks depth across both alternatives jointly, so a
    nonFraction nested inside a nonNumeric (or vice versa) still counts as nested — "a fact
    nested inside another fact", not "same-kind nesting only".
    """
    depth = 0
    counts: Counter = Counter()
    nested = 0
    for m in pattern.finditer(data):
        closing = m.group(1) == b"/"
        if closing:
            depth = max(depth - 1, 0)
            continue
        local = m.group(2).lower()
        self_closing = m.group(4) == b"/"
        counts[local] += 1
        if depth > 0:
            nested += 1
        if not self_closing:
            depth += 1
    return counts, nested


def format_counter(data: bytes) -> Counter:
    counter: Counter = Counter()
    for m in FORMAT_RE.finditer(data):
        value = (m.group(1) or m.group(2) or b"").decode("utf-8", "replace")
        counter[value] += 1
    return counter


def census_filing(
    data: bytes,
    *,
    source_member: str,
    company: str,
    made_up_to_date: str,
    extension: str,
    archive_year: int,
    archive_month: int,
) -> tuple[FilingCensus, Counter]:
    fact_counts, n_nested = _tag_events(data, FACT_TAG_EVENT_RE)
    ce_counts, _ = _tag_events(data, CONT_EXCL_TAG_RE)
    contexts, _invalid = extract_contexts(data)
    n_multi = sum(1 for c in contexts.values() if c.kind == ContextKind.MULTI_MEMBER)
    n_typed = sum(1 for c in contexts.values() if c.kind == ContextKind.TYPED)
    census = FilingCensus(
        source_member=source_member,
        company_number=company,
        archive_year=archive_year,
        archive_month=archive_month,
        made_up_to_date=made_up_to_date,
        file_extension=extension.lower(),
        ix_prefix=detect_ix_prefix(data),
        has_ix_header=bool(IX_HEADER_RE.search(data)),
        n_nonfraction=fact_counts.get(b"nonfraction", 0),
        n_nonnumeric=fact_counts.get(b"nonnumeric", 0),
        n_continuation=ce_counts.get(b"continuation", 0),
        n_exclude=ce_counts.get(b"exclude", 0),
        n_nested_facts=n_nested,
        n_multimember_contexts=n_multi,
        n_typed_contexts=n_typed,
    )
    return census, format_counter(data)


def in_sample(company: str) -> bool:
    """sha256(normalised company number) % 100 == 0 — about 1% of distinct companies."""
    normalised = normalise_company(company)
    digest = hashlib.sha256(normalised.encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % 100 == 0


def _worker(
    args: tuple[Path, list[str], int, int, Path],
) -> tuple[list[dict], dict[str, int], int]:
    """Runs in a worker process: scans an assigned slice of one archive's members."""
    zip_path, members, archive_year, archive_month, sample_dir = args
    rows: list[dict] = []
    formats: Counter = Counter()
    filename_exceptions = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in members:
            parsed = MEMBER_RE.fullmatch(Path(member).name)
            if not parsed:
                filename_exceptions += 1
                continue
            company, made_up_to_date, extension = parsed.groups()
            data = archive.read(member)
            census, file_formats = census_filing(
                data,
                source_member=member,
                company=company,
                made_up_to_date=made_up_to_date,
                extension=extension,
                archive_year=archive_year,
                archive_month=archive_month,
            )
            rows.append(asdict(census))
            formats.update(file_formats)
            if in_sample(company):
                target = sample_dir / Path(member).name
                if not target.exists():
                    target.write_bytes(data)
    return rows, dict(formats), filename_exceptions


def census_month(
    year: int,
    month: int,
    *,
    downloads: Path,
    workers: int,
    pre_existing: set[str],
) -> dict:
    name = archive_name(year, month)
    census_path = CENSUS_DIR / f"{name}.parquet"
    format_path = FORMAT_DIR / f"{name}.json"
    if census_path.exists() and format_path.exists():
        return {"month": f"{year:04d}-{month:02d}", "status": "already_done"}

    fetched = _fetch_archive(month, year, downloads=downloads)
    if fetched.status != FetchStatus.DOWNLOADED:
        return {
            "month": f"{year:04d}-{month:02d}",
            "status": "fetch_failed",
            "error": fetched.error,
        }
    zip_path = fetched.path
    downloaded_this_run = name not in pre_existing

    with zipfile.ZipFile(zip_path) as archive:
        members = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir() and MEMBER_RE.fullmatch(Path(info.filename).name)
        ]

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    chunk_size = max(1, -(-len(members) // workers))
    chunks = [members[i : i + chunk_size] for i in range(0, len(members), chunk_size)]
    tasks = [(zip_path, chunk, year, month, SAMPLE_DIR) for chunk in chunks]

    all_rows: list[dict] = []
    all_formats: Counter = Counter()
    total_filename_exceptions = 0
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for rows, formats, exc in pool.map(_worker, tasks):
            all_rows.extend(rows)
            all_formats.update(formats)
            total_filename_exceptions += exc
    elapsed = time.monotonic() - started

    CENSUS_DIR.mkdir(parents=True, exist_ok=True)
    FORMAT_DIR.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(all_rows)
    pq.write_table(table, census_path, compression="zstd")
    format_path.write_text(json.dumps(dict(all_formats), indent=2), encoding="utf-8")

    if downloaded_this_run:
        zip_path.unlink(missing_ok=True)

    return {
        "month": f"{year:04d}-{month:02d}",
        "status": "done",
        "members_total": len(members),
        "filename_exceptions": total_filename_exceptions,
        "elapsed_seconds": round(elapsed, 1),
        "files_per_sec": round(len(members) / elapsed, 1) if elapsed > 0 else None,
        "zip_deleted": downloaded_this_run,
        "zip_bytes": zip_path.stat().st_size if zip_path.exists() else fetched.bytes_received,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", default="2014-01")
    parser.add_argument("--to", dest="end", default="2026-08")
    parser.add_argument("--downloads", default=str(DEFAULT_DOWNLOADS))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--log", default="data/accounts/parser-census-run.log")
    args = parser.parse_args()

    downloads = Path(args.downloads).expanduser()
    pre_existing = {p.name for p in downloads.glob("Accounts_Monthly_Data-*.zip")}

    start = parse_month(args.start)
    end = parse_month(args.end)
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    for year, month in iter_months(start, end):
        result = census_month(
            year, month, downloads=downloads, workers=args.workers, pre_existing=pre_existing
        )
        line = json.dumps(result)
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if result["status"] == "fetch_failed":
            print(f"STOPPING: {result['month']} fetch failed: {result.get('error')}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
