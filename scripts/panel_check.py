#!/usr/bin/env python3
"""Build a disk-backed panel/reconciliation check from monthly accounts ZIPs."""

from __future__ import annotations

import argparse
import calendar
import html
import re
import sqlite3
import sys
import time
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ARCHIVE_RE = re.compile(
    r"^\s*Accounts_Monthly_Data-([A-Za-z]+)(2022|2023)\.zip\s*$",
    re.I,
)
MEMBER_RE = re.compile(
    r"^Prod\d+_\d{4}_([^_]+)_(\d{8})\.(html|htm|xml)$",
    re.I,
)
CONTEXT_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?context\b([^>]*)>(.*?)</\s*(?:[\w.-]+:)?context\s*>",
    re.I | re.S,
)
PERIOD_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?(?:instant|endDate)\b[^>]*>(.*?)</",
    re.I | re.S,
)
IX_FACT_RE = re.compile(
    rb"<\s*ix:(?:nonFraction|nonNumeric)\b([^>]*)>(.*?)"
    rb"</\s*ix:(?:nonFraction|nonNumeric)\s*>",
    re.I | re.S,
)
ATTR_RE = re.compile(rb"([:\w.-]+)\s*=\s*(['\"])(.*?)\2", re.S)
TAG_RE = re.compile(rb"<[^>]+>")
TARGET_CONCEPTS = (
    "Equity",
    "NetCurrentAssetsLiabilities",
    "CurrentAssets",
    "Creditors",
    "CashBankOnHand",
    "Debtors",
    "PropertyPlantEquipment",
    "TotalAssetsLessCurrentLiabilities",
    "AverageNumberEmployeesDuringPeriod",
)
TARGET_SET = set(TARGET_CONCEPTS)
COMPANY_CONCEPT = "UKCompaniesHouseRegisteredNumber"


@dataclass(frozen=True)
class Fact:
    concept: str
    context_ref: str
    period_end: str
    raw_value: str
    scale: int
    numeric_value: str | None


@dataclass(frozen=True)
class ContextPeriod:
    period_end: str
    dimensional: bool


@dataclass
class Filing:
    company: str
    filing_date: str
    tagged_companies: set[str]
    facts: list[Fact]
    bad_period_refs: int
    ambiguous_facts: int


def parse_member_filename(member: str) -> tuple[str, str, str] | None:
    """Return company, filing date, and extension from a filing filename."""
    match = MEMBER_RE.fullmatch(Path(member.strip()).name)
    return match.groups() if match else None


def _attrs(raw: bytes) -> dict[str, str]:
    return {
        key.decode("utf-8", "replace").lower(): value.decode("utf-8", "replace")
        for key, _quote, value in ATTR_RE.findall(raw)
    }


def _text(raw: bytes) -> str:
    value = TAG_RE.sub(b"", raw).decode("utf-8", "replace")
    return html.unescape(value).replace("\u00a0", " ").strip()


def _valid_date(value: str) -> str | None:
    candidate = value.strip()[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def extract_context_periods(data: bytes) -> tuple[dict[str, ContextPeriod], int]:
    """Map context IDs to their instant/end date, tolerating malformed XHTML."""
    periods: dict[str, ContextPeriod] = {}
    invalid = 0
    for raw_attrs, body in CONTEXT_RE.findall(data):
        context_id = _attrs(raw_attrs).get("id")
        period_match = PERIOD_RE.search(body)
        if not context_id or not period_match:
            continue
        period = _valid_date(_text(period_match.group(1)))
        if period:
            dimensional = bool(
                re.search(rb"<\s*(?:[\w.-]+:)?(?:segment|scenario)\b", body, re.I)
            )
            periods[context_id] = ContextPeriod(period, dimensional)
        else:
            invalid += 1
    return periods, invalid


def normalise_number(raw: str, scale: int, sign: str = "") -> str | None:
    """Convert common iXBRL numeric presentations to a scaled decimal string."""
    value = raw.strip()
    if not value or value in {"-", "—", "–"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    cleaned = value.strip("()").replace(",", "").replace(" ", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if negative:
        number = -number
    if sign.strip() == "-":
        number = -abs(number)
    number *= Decimal(10) ** scale
    return format(number, "f")


def _normalise_company(value: str) -> str:
    return re.sub(r"\s+", "", value).upper().lstrip("0") or "0"


def extract_filing(data: bytes, company: str, filing_date: str) -> Filing:
    """Extract all locked concepts and attach each fact's context period."""
    periods, invalid_periods = extract_context_periods(data)
    candidates: dict[tuple[str, str], list[tuple[bool, Fact]]] = {}
    tagged_companies: set[str] = set()
    bad_period_refs = invalid_periods
    for raw_attrs, body in IX_FACT_RE.findall(data):
        attrs = _attrs(raw_attrs)
        concept = attrs.get("name", "").rsplit(":", 1)[-1]
        if concept not in TARGET_SET and concept != COMPANY_CONCEPT:
            continue
        raw_value = _text(body)
        if concept == COMPANY_CONCEPT:
            if raw_value:
                tagged_companies.add(raw_value)
            continue
        context_ref = attrs.get("contextref", "")
        context = periods.get(context_ref)
        if not context:
            bad_period_refs += 1
            continue
        try:
            scale = int(attrs.get("scale", "0") or 0)
        except ValueError:
            scale = 0
        fact = Fact(
            concept,
            context_ref,
            context.period_end,
            raw_value,
            scale,
            normalise_number(raw_value, scale, attrs.get("sign", "")),
        )
        candidates.setdefault((concept, context.period_end), []).append(
            (context.dimensional, fact)
        )
    facts: list[Fact] = []
    ambiguous_facts = 0
    for choices in candidates.values():
        best_rank = min(dimensional for dimensional, _fact in choices)
        best = [fact for dimensional, fact in choices if dimensional == best_rank]
        values = {
            ("NUM", fact.numeric_value)
            if fact.numeric_value is not None
            else ("RAW", fact.raw_value)
            for fact in best
        }
        if len(values) == 1:
            facts.append(best[0])
        else:
            # Multiple dimensional members are components, not competing totals.
            # Multiple non-dimensional values are genuinely ambiguous. Neither is
            # safe as the one company/period/concept panel value.
            ambiguous_facts += len(best)
    return Filing(
        company,
        filing_date,
        tagged_companies,
        facts,
        bad_period_refs,
        ambiguous_facts,
    )


def distinct_periods(filing: Filing) -> set[str]:
    """Return the distinct period ends supplied by one filing's target facts."""
    return {fact.period_end for fact in filing.facts}


def discover_archives(downloads: Path) -> list[tuple[Path, int, int]]:
    archives = []
    for path in downloads.iterdir():
        match = ARCHIVE_RE.fullmatch(path.name)
        if not match:
            continue
        month_name, year_text = match.groups()
        try:
            month = list(calendar.month_name).index(month_name.title())
        except ValueError:
            continue
        archives.append((path, int(year_text), month))
    return sorted(archives, key=lambda item: (item[1], item[2]))


def connect_store(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=FILE;
        CREATE TABLE IF NOT EXISTS observations (
            company TEXT NOT NULL,
            period_end TEXT NOT NULL,
            concept TEXT NOT NULL,
            source_year INTEGER NOT NULL,
            source_month INTEGER NOT NULL,
            source_member TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            raw_value TEXT NOT NULL,
            scale INTEGER NOT NULL,
            numeric_value TEXT,
            is_current INTEGER NOT NULL,
            UNIQUE(company, period_end, concept, source_year, source_month, source_member,
                   raw_value, scale)
        );
        CREATE TABLE IF NOT EXISTS filing_periods (
            company TEXT NOT NULL,
            source_year INTEGER NOT NULL,
            source_month INTEGER NOT NULL,
            source_member TEXT NOT NULL,
            period_end TEXT NOT NULL,
            is_current INTEGER NOT NULL,
            UNIQUE(company, source_year, source_month, source_member, period_end)
        );
        CREATE TABLE IF NOT EXISTS integrity (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
        """
    )
    return connection


def increment(connection: sqlite3.Connection, key: str, amount: int = 1) -> None:
    connection.execute(
        "INSERT INTO integrity(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
        (key, amount),
    )


def store_filing(
    connection: sqlite3.Connection,
    filing: Filing,
    source_year: int,
    source_month: int,
    source_member: str,
) -> None:
    periods = distinct_periods(filing)
    current_period = max(periods, default="")
    connection.executemany(
        "INSERT OR IGNORE INTO filing_periods VALUES (?, ?, ?, ?, ?, ?)",
        (
            (filing.company, source_year, source_month, source_member, period, period == current_period)
            for period in periods
        ),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                filing.company,
                fact.period_end,
                fact.concept,
                source_year,
                source_month,
                source_member,
                filing.filing_date,
                fact.raw_value,
                fact.scale,
                fact.numeric_value,
                fact.period_end == current_period,
            )
            for fact in filing.facts
        ),
    )


def process_archive(
    connection: sqlite3.Connection,
    path: Path,
    year: int,
    month: int,
    limit: int | None,
) -> int:
    processed = 0
    started = time.monotonic()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            parsed_name = parse_member_filename(info.filename)
            if not parsed_name:
                increment(connection, "filename_exceptions")
                continue
            company, filing_date, extension = parsed_name
            if extension.lower() == "xml":
                increment(connection, "xml_skipped")
                continue
            if extension.lower() not in {"html", "htm"}:
                increment(connection, "other_skipped")
                continue
            if limit is not None and processed >= limit:
                break
            try:
                data = archive.read(info)
                if not re.search(rb"<\s*(?:html|ix:header|xbrli?:xbrl)\b", data, re.I):
                    raise ValueError("no recognisable iXBRL document root")
                filing = extract_filing(data, company, filing_date)
                store_filing(connection, filing, year, month, info.filename)
                increment(connection, "bad_period_refs", filing.bad_period_refs)
                increment(connection, "ambiguous_facts", filing.ambiguous_facts)
                if filing.tagged_companies and _normalise_company(company) not in {
                    _normalise_company(value) for value in filing.tagged_companies
                }:
                    increment(connection, "company_mismatches")
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
                increment(connection, "unparseable")
            processed += 1
            if processed % 10_000 == 0:
                connection.commit()
                elapsed = time.monotonic() - started
                print(
                    f"  {processed:,} filings ({processed / elapsed:,.0f}/s)",
                    flush=True,
                )
    increment(connection, "filings_processed", processed)
    connection.commit()
    elapsed = time.monotonic() - started
    print(f"  done: {processed:,} filings in {elapsed / 60:.1f} min", flush=True)
    return processed


def scalar(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def integrity_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return dict(connection.execute("SELECT key, value FROM integrity"))


def recurrence_distribution(connection: sqlite3.Connection, current_only: bool) -> Counter[str]:
    where = "WHERE is_current = 1" if current_only else ""
    counter: Counter[str] = Counter()
    query = (
        "SELECT period_count, COUNT(*) FROM ("
        f"SELECT company, COUNT(DISTINCT period_end) period_count FROM filing_periods {where} GROUP BY company"
        ") GROUP BY period_count"
    )
    for period_count, companies in connection.execute(query):
        counter["4+" if period_count >= 4 else str(period_count)] += companies
    return counter


def reconciliation_rows(connection: sqlite3.Connection) -> list[tuple[str, int, int, int]]:
    query = """
        WITH repeated AS (
            SELECT company, period_end, concept,
                   COUNT(DISTINCT source_year || '-' || source_month || '-' || source_member) sources,
                   COUNT(DISTINCT COALESCE(numeric_value, 'RAW:' || raw_value)) variants
            FROM observations
            GROUP BY company, period_end, concept
            HAVING sources > 1
        )
        SELECT concept, COUNT(*),
               SUM(CASE WHEN variants = 1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN variants > 1 THEN 1 ELSE 0 END)
        FROM repeated GROUP BY concept ORDER BY concept
    """
    return list(connection.execute(query))


def disagreement_examples(connection: sqlite3.Connection, limit: int = 12) -> list[tuple[str, ...]]:
    query = """
        WITH disagreements AS (
            SELECT company, period_end, concept
            FROM observations
            GROUP BY company, period_end, concept
            HAVING COUNT(DISTINCT source_year || '-' || source_month || '-' || source_member) > 1
               AND COUNT(DISTINCT COALESCE(numeric_value, 'RAW:' || raw_value)) > 1
            LIMIT ?
        )
        SELECT d.company, d.period_end, d.concept,
               GROUP_CONCAT(o.raw_value || ' (scale=' || o.scale || ', filed=' ||
                            o.filing_date || ')', '; ')
        FROM disagreements d JOIN observations o USING(company, period_end, concept)
        GROUP BY d.company, d.period_end, d.concept
    """
    return list(connection.execute(query, (limit,)))


def fill_rates(connection: sqlite3.Connection) -> list[tuple[str, int, int]]:
    denominator = scalar(
        connection,
        "SELECT COUNT(*) FROM (SELECT DISTINCT company, period_end FROM observations)",
    )
    present = dict(
        connection.execute(
            "SELECT concept, COUNT(*) FROM (SELECT DISTINCT company, period_end, concept "
            "FROM observations) GROUP BY concept"
        )
    )
    return [(concept, present.get(concept, 0), denominator) for concept in TARGET_CONCEPTS]


def monthly_fill_rates(connection: sqlite3.Connection) -> dict[str, list[tuple[int, int, float]]]:
    query = """
        WITH records AS (
            SELECT DISTINCT source_year, source_month, company, period_end FROM observations
        ), facts AS (
            SELECT DISTINCT source_year, source_month, company, period_end, concept FROM observations
        ), denominators AS (
            SELECT source_year, source_month, COUNT(*) n FROM records GROUP BY 1, 2
        )
        SELECT f.concept, f.source_year, f.source_month, COUNT(*) * 1.0 / d.n
        FROM facts f JOIN denominators d USING(source_year, source_month)
        GROUP BY f.concept, f.source_year, f.source_month
    """
    result: dict[str, list[tuple[int, int, float]]] = {concept: [] for concept in TARGET_CONCEPTS}
    for concept, year, month, rate in connection.execute(query):
        result[concept].append((year, month, rate))
    return result


def export_parquet(connection: sqlite3.Connection, output: Path, batch_size: int = 250_000) -> None:
    """Stream SQLite observations through Polars batches into one Parquet file."""
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError("Parquet export requires the project's dev extra (polars)") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    parts = output.parent / ".panel-check-parts"
    parts.mkdir(exist_ok=True)
    cursor = connection.execute(
        "SELECT company, period_end, concept, source_year, source_month, source_member, "
        "filing_date, raw_value, scale, numeric_value, is_current FROM observations "
        "ORDER BY company, period_end, concept, filing_date"
    )
    names = [item[0] for item in cursor.description]
    index = 0
    while rows := cursor.fetchmany(batch_size):
        frame = pl.DataFrame(rows, schema=names, orient="row")
        frame.write_parquet(parts / f"part-{index:05d}.parquet", compression="zstd")
        index += 1
    if index:
        pl.scan_parquet(parts / "part-*.parquet").sink_parquet(output, compression="zstd")
    else:
        pl.DataFrame(schema={name: pl.String for name in names}).write_parquet(output)
    for part in parts.glob("part-*.parquet"):
        part.unlink()
    parts.rmdir()


def pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.2f}%" if denominator else "n/a"


def render_report(
    connection: sqlite3.Connection,
    archives: list[tuple[Path, int, int]],
    parquet_path: Path,
) -> str:
    integrity = integrity_counts(connection)
    current = recurrence_distribution(connection, current_only=True)
    dense = recurrence_distribution(connection, current_only=False)
    companies = scalar(connection, "SELECT COUNT(DISTINCT company) FROM filing_periods")
    records = scalar(
        connection,
        "SELECT COUNT(*) FROM (SELECT DISTINCT company, period_end FROM observations)",
    )
    observations = scalar(connection, "SELECT COUNT(*) FROM observations")
    input_size = sum(path.stat().st_size for path, _year, _month in archives)
    output_size = parquet_path.stat().st_size
    reconciliation = reconciliation_rows(connection)
    repeated = sum(row[1] for row in reconciliation)
    agreements = sum(row[2] for row in reconciliation)
    disagreements = sum(row[3] for row in reconciliation)
    monthly = monthly_fill_rates(connection)
    lines = [
        "# Accounts panel existence and reconciliation check",
        "",
        "This report covers every iXBRL filing in the 24 monthly 2022–2023 archives. XML filings were skipped and counted. ZIP members were read in memory without extraction; aggregation used a disk-backed store.",
        "",
        "## Recurrence: does a company panel exist?",
        "",
        f"Distinct companies: **{companies:,}**.",
        "",
        "| Counting method | 1 period | 2 periods | 3 periods | 4+ periods | Companies with 2+ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, distribution in (
        ("Current period from distinct filings", current),
        ("All fact periods, including comparatives", dense),
    ):
        two_plus = sum(value for key, value in distribution.items() if key != "1")
        lines.append(
            f"| {label} | {distribution['1']:,} | {distribution['2']:,} | "
            f"{distribution['3']:,} | {distribution['4+']:,} | "
            f"{two_plus:,} ({pct(two_plus, sum(distribution.values()))}) |"
        )
    dense_two_plus = sum(value for key, value in dense.items() if key != "1")
    lines.extend(
        [
            "",
            "**Panel-existence answer:** "
            + (
                "Yes. Most observed companies have at least two distinct period ends once comparative facts are included."
                if dense_two_plus > companies / 2
                else "No. Most observed companies still have only one period even after comparative facts are included."
            ),
            "",
            "## Restatement and reconciliation",
            "",
            f"Across {repeated:,} repeated company/period/concept keys, {agreements:,} ({pct(agreements, repeated)}) agree exactly after applying scale and {disagreements:,} ({pct(disagreements, repeated)}) disagree.",
            "",
            "| Concept | Repeated keys | Exact match | Disagree |",
            "|---|---:|---:|---:|",
        ]
    )
    for concept, total, agree, disagree in reconciliation:
        lines.append(f"| `{concept}` | {total:,} | {agree:,} ({pct(agree, total)}) | {disagree:,} ({pct(disagree, total)}) |")
    lines.extend(["", "Example disagreements (the most recently filed observation is the take-latest candidate):", ""])
    examples = disagreement_examples(connection)
    lines.extend(f"- `{company}` / `{period}` / `{concept}`: {values}" for company, period, concept, values in examples)
    if not examples:
        lines.append("None found.")

    lines.extend(
        [
            "",
            "## Population fill rates",
            "",
            "Denominator: distinct company/period records containing at least one locked concept.",
            "",
            "| Concept | Present records | Fill rate | Monthly range (2022–2023) |",
            "|---|---:|---:|---:|",
        ]
    )
    for concept, present, denominator in fill_rates(connection):
        rates = [item[2] for item in monthly[concept]]
        range_text = f"{min(rates):.1%}–{max(rates):.1%}" if rates else "n/a"
        flag = " ⚠" if rates and max(rates) - min(rates) >= 0.10 else ""
        lines.append(f"| `{concept}` | {present:,} | {pct(present, denominator)} | {range_text}{flag} |")
    lines.extend(
        [
            "",
            "⚠ marks a ≥10 percentage-point monthly range, a simple screen for filing-year/month-correlated missingness rather than a formal significance test. The recon sample benchmarks were approximately 96–97% for Equity and 41% (2022) to 33% (2025) for CashBankOnHand.",
            "",
            "## Size and reduction",
            "",
            f"- Filings processed: {integrity.get('filings_processed', 0):,}",
            f"- Distinct company/period records: {records:,}",
            f"- Long-format source observations: {observations:,}",
            f"- Input ZIP size: {input_size / 1024**3:.2f} GiB",
            f"- Reduced Parquet size: {output_size / 1024**3:.2f} GiB",
            f"- Reduction ratio: **{input_size / output_size:,.1f}× smaller**",
            "",
            "## Integrity",
            "",
            f"- XML filings skipped: {integrity.get('xml_skipped', 0):,}",
            f"- Other/unsupported members skipped: {integrity.get('other_skipped', 0):,}",
            f"- Filename-pattern exceptions: {integrity.get('filename_exceptions', 0):,}",
            f"- Unparseable filings: {integrity.get('unparseable', 0):,}",
            f"- Filename/tag company-number mismatches: {integrity.get('company_mismatches', 0):,}",
            f"- Target facts with missing or invalid period-end contexts: {integrity.get('bad_period_refs', 0):,}",
            f"- Facts omitted because no unique consolidated value could be selected: {integrity.get('ambiguous_facts', 0):,}",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--output", type=Path, default=Path("data/panel-check-sample.parquet"))
    parser.add_argument("--report", type=Path, default=Path("docs/panel-check.md"))
    parser.add_argument("--store", type=Path, default=Path("data/panel-check.sqlite"))
    parser.add_argument("--limit-per-zip", type=int, help="development-only filing limit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archives = discover_archives(args.downloads)
    if len(archives) != 24:
        raise SystemExit(f"expected 24 archives for 2022–2023, found {len(archives)}")
    args.store.parent.mkdir(parents=True, exist_ok=True)
    if args.store.exists():
        raise SystemExit(f"temporary store already exists: {args.store} (remove it to restart)")
    connection = connect_store(args.store)
    try:
        for index, (path, year, month) in enumerate(archives, 1):
            print(f"[{index}/24] {path.name}", flush=True)
            process_archive(connection, path, year, month, args.limit_per_zip)
        print("Exporting reduced observations to Parquet...", flush=True)
        export_parquet(connection, args.output)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_report(connection, archives, args.output), encoding="utf-8")
        integrity = integrity_counts(connection)
        dense = recurrence_distribution(connection, current_only=False)
        companies = sum(dense.values())
        two_plus = companies - dense["1"]
        reconciliation = reconciliation_rows(connection)
        repeated = sum(row[1] for row in reconciliation)
        disagreements = sum(row[3] for row in reconciliation)
        input_size = sum(path.stat().st_size for path, _year, _month in archives)
        print(
            f"Summary: {companies:,} companies; {pct(two_plus, companies)} with >=2 periods; "
            f"{pct(disagreements, repeated)} restatement disagreement; "
            f"{input_size / args.output.stat().st_size:,.1f}x reduction",
            flush=True,
        )
        print(f"Report written to {args.report}", flush=True)
        print(f"Parquet written to {args.output}", flush=True)
        print(f"Filings processed: {integrity.get('filings_processed', 0):,}", flush=True)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
