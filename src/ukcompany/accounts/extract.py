"""Resumable bulk extraction of Companies House monthly accounts archives."""

from __future__ import annotations

import calendar
import json
import math
import re
import sqlite3
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, fields
from pathlib import Path

from .core import TARGET_CONCEPTS, ExtractedFiling, IntegrityCounts, extract_filing

ARCHIVE_RE = re.compile(
    r"^\s*Accounts_Monthly_Data-([A-Za-z]+)(\d{4})\.zip\s*$",
    re.I,
)
MEMBER_RE = re.compile(
    r"^Prod\d+_\d{4}_([^_]+)_(\d{8})\.(html|htm|xml)$",
    re.I,
)

OBSERVATION_COLUMNS = (
    "company",
    "period_end",
    "concept",
    "dimension",
    "member",
    "currency",
    "source_year",
    "source_month",
    "source_archive",
    "source_member",
    "made_up_to_date",
    "raw_value",
    "scale",
    "sign",
    "numeric_value",
    "is_current",
)


@dataclass(frozen=True)
class ArchiveSpec:
    path: Path
    year: int
    month: int

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class ArchiveIntegrity:
    filings_processed: int = 0
    xml_skipped: int = 0
    filename_exceptions: int = 0
    unparseable_filings: int = 0
    company_mismatches: int = 0
    target_facts_seen: int = 0
    kept_total: int = 0
    kept_member: int = 0
    collapsed_duplicate: int = 0
    ambiguous_nondimensional: int = 0
    member_value_conflict: int = 0
    skipped_multimember: int = 0
    skipped_typed: int = 0
    bad_period_refs: int = 0
    non_gbp_facts: int = 0
    unresolved_unit_refs: int = 0

    def add_filing(self, filing: ExtractedFiling) -> None:
        self.filings_processed += 1
        for field in fields(IntegrityCounts):
            name = field.name
            setattr(self, name, getattr(self, name) + getattr(filing.integrity, name))

    def as_dict(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, values: dict[str, int]) -> ArchiveIntegrity:
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in known})

    def __iadd__(self, other: ArchiveIntegrity) -> ArchiveIntegrity:
        for field in fields(self):
            setattr(self, field.name, getattr(self, field.name) + getattr(other, field.name))
        return self

    def closes(self) -> bool:
        accounted = (
            self.kept_total
            + self.kept_member
            + self.collapsed_duplicate
            + self.ambiguous_nondimensional
            + self.member_value_conflict
            + self.skipped_multimember
            + self.skipped_typed
            + self.bad_period_refs
        )
        return accounted == self.target_facts_seen


def parse_archive(path: str | Path) -> ArchiveSpec:
    archive_path = Path(path).expanduser()
    match = ARCHIVE_RE.fullmatch(archive_path.name)
    if not match:
        raise ValueError(f"unexpected archive filename: {archive_path.name!r}")
    month_name, year_text = match.groups()
    try:
        month = list(calendar.month_name).index(month_name.title())
    except ValueError as exc:
        raise ValueError(f"unrecognised month in archive: {archive_path.name!r}") from exc
    return ArchiveSpec(archive_path, int(year_text), month)


def discover_archives(downloads: str | Path) -> list[ArchiveSpec]:
    directory = Path(downloads).expanduser()
    archives = []
    for path in directory.iterdir():
        try:
            archives.append(parse_archive(path))
        except ValueError:
            continue
    return sorted(archives, key=lambda archive: (archive.year, archive.month, archive.name))


def parse_member_filename(member: str) -> tuple[str, str, str] | None:
    match = MEMBER_RE.fullmatch(Path(member.strip()).name)
    return match.groups() if match else None


def normalise_company(value: str) -> str:
    """Normalise only for comparison; stored company identifiers retain leading zeros."""
    return re.sub(r"\s+", "", value).upper().lstrip("0") or "0"


def connect_store(path: str | Path) -> sqlite3.Connection:
    store = Path(path)
    store.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(store)
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=FILE;
        CREATE TABLE IF NOT EXISTS observations (
            company TEXT NOT NULL,
            period_end TEXT NOT NULL,
            concept TEXT NOT NULL,
            dimension TEXT,
            member TEXT,
            currency TEXT,
            source_year INTEGER NOT NULL,
            source_month INTEGER NOT NULL,
            source_archive TEXT NOT NULL,
            source_member TEXT NOT NULL,
            made_up_to_date TEXT NOT NULL,
            raw_value TEXT NOT NULL,
            scale INTEGER NOT NULL,
            sign TEXT,
            numeric_value TEXT,
            is_current INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS observations_identity ON observations (
            company, period_end, concept, COALESCE(dimension, ''), COALESCE(member, ''),
            source_archive, source_member, raw_value, scale, COALESCE(currency, '')
        );
        CREATE TABLE IF NOT EXISTS processed_archives (
            archive_name TEXT PRIMARY KEY,
            archive_size INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            observation_count INTEGER NOT NULL,
            complete INTEGER NOT NULL,
            integrity_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS legacy_dimensional_fallbacks (
            company TEXT NOT NULL,
            period_end TEXT NOT NULL,
            concept TEXT NOT NULL,
            numeric_value TEXT,
            raw_value TEXT NOT NULL,
            scale INTEGER NOT NULL,
            sign TEXT,
            currency TEXT,
            source_archive TEXT NOT NULL,
            source_member TEXT NOT NULL,
            UNIQUE(company, period_end, concept, source_archive, source_member)
        );
        """
    )
    return connection


def _stored_archive(connection: sqlite3.Connection, archive: ArchiveSpec) -> tuple | None:
    return connection.execute(
        "SELECT archive_size, member_count, complete FROM processed_archives "
        "WHERE archive_name = ?",
        (archive.name,),
    ).fetchone()


def archive_is_complete(connection: sqlite3.Connection, archive: ArchiveSpec) -> bool:
    stored = _stored_archive(connection, archive)
    if not stored or not stored[2]:
        return False
    archive_size, member_count, _complete = stored
    with zipfile.ZipFile(archive.path) as source:
        actual_members = len(source.infolist())
    if archive_size != archive.path.stat().st_size or member_count != actual_members:
        raise RuntimeError(
            f"completed archive changed since extraction: {archive.name}; use a new store"
        )
    return True


def _store_filing(
    connection: sqlite3.Connection,
    filing: ExtractedFiling,
    archive: ArchiveSpec,
    source_member: str,
) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO observations VALUES ("
        + ", ".join("?" for _column in OBSERVATION_COLUMNS)
        + ")",
        (
            (
                filing.company,
                fact.period_end,
                fact.concept,
                fact.dimension,
                fact.member,
                fact.currency,
                archive.year,
                archive.month,
                archive.name,
                source_member,
                filing.made_up_to_date,
                fact.raw_value,
                fact.scale,
                fact.sign,
                fact.numeric_value,
                int(fact.is_current),
            )
            for fact in filing.observations
        ),
    )
    connection.executemany(
        "INSERT OR IGNORE INTO legacy_dimensional_fallbacks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                filing.company,
                fallback.period_end,
                fallback.concept,
                fallback.numeric_value,
                fallback.raw_value,
                fallback.scale,
                fallback.sign,
                fallback.currency,
                archive.name,
                source_member,
            )
            for fallback in filing.legacy_fallbacks
        ),
    )


def _write_manifest(
    connection: sqlite3.Connection,
    archive: ArchiveSpec,
    member_count: int,
    complete: bool,
    integrity: ArchiveIntegrity,
) -> None:
    observation_count = connection.execute(
        "SELECT COUNT(*) FROM observations WHERE source_archive = ?", (archive.name,)
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO processed_archives VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(archive_name) DO UPDATE SET archive_size=excluded.archive_size, "
        "member_count=excluded.member_count, observation_count=excluded.observation_count, "
        "complete=excluded.complete, integrity_json=excluded.integrity_json",
        (
            archive.name,
            archive.path.stat().st_size,
            member_count,
            observation_count,
            int(complete),
            json.dumps(integrity.as_dict(), sort_keys=True),
        ),
    )
    connection.commit()


def process_archive(
    connection: sqlite3.Connection,
    archive: ArchiveSpec,
    *,
    limit: int | None = None,
    progress_every: int = 10_000,
) -> ArchiveIntegrity | None:
    """Process or resume one ZIP; return None when a verified completed ZIP is skipped."""
    if archive_is_complete(connection, archive):
        print(f"skip completed: {archive.name}", flush=True)
        return None
    integrity = ArchiveIntegrity()
    started = time.monotonic()
    with zipfile.ZipFile(archive.path) as source:
        infos = source.infolist()
        selected_infos = infos
        if limit is not None:
            eligible = [
                info
                for info in infos
                if not info.is_dir() and parse_member_filename(info.filename) is not None
            ]
            if len(eligible) > limit:
                selected_infos = [
                    eligible[math.floor(index * len(eligible) / limit)] for index in range(limit)
                ]
            else:
                selected_infos = eligible
        for info in selected_infos:
            if info.is_dir():
                continue
            parsed = parse_member_filename(info.filename)
            if not parsed:
                integrity.filename_exceptions += 1
                continue
            company, made_up_to_date, extension = parsed
            if extension.lower() == "xml":
                integrity.xml_skipped += 1
                continue
            try:
                data = source.read(info)
                if not re.search(rb"<\s*(?:html|ix:header)\b", data, re.I):
                    raise ValueError("no recognisable iXBRL document root")
                filing = extract_filing(data, company, made_up_to_date)
                _store_filing(connection, filing, archive, info.filename)
                integrity.add_filing(filing)
                if filing.tagged_companies and normalise_company(company) not in {
                    normalise_company(value) for value in filing.tagged_companies
                }:
                    integrity.company_mismatches += 1
            except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
                integrity.unparseable_filings += 1
            if progress_every and integrity.filings_processed % progress_every == 0:
                connection.commit()
                elapsed = max(time.monotonic() - started, 0.001)
                print(
                    f"  {integrity.filings_processed:,} filings "
                    f"({integrity.filings_processed / elapsed:,.0f}/s)",
                    flush=True,
                )
        complete = limit is None
        _write_manifest(connection, archive, len(infos), complete, integrity)
    if not integrity.closes():
        raise AssertionError(f"run accounting does not close for {archive.name}")
    return integrity


def manifest_integrity(connection: sqlite3.Connection) -> ArchiveIntegrity:
    total = ArchiveIntegrity()
    for (raw,) in connection.execute("SELECT integrity_json FROM processed_archives"):
        total += ArchiveIntegrity.from_dict(json.loads(raw))
    return total


def manifest_rows(connection: sqlite3.Connection) -> list[dict[str, object]]:
    columns = [item[1] for item in connection.execute("PRAGMA table_info(processed_archives)")]
    return [
        dict(zip(columns, row, strict=True))
        for row in connection.execute("SELECT * FROM processed_archives ORDER BY archive_name")
    ]


def export_parquet(
    connection: sqlite3.Connection,
    output: str | Path,
    *,
    batch_size: int = 250_000,
) -> None:
    """Stream SQLite observations through bounded Polars batches to one Parquet file."""
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError("Parquet export requires the project's dev extra (polars)") from exc
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    parts = destination.parent / f".{destination.stem}-parts"
    if parts.exists():
        raise RuntimeError(f"temporary export directory already exists: {parts}")
    parts.mkdir()
    cursor = connection.execute(
        "SELECT " + ", ".join(OBSERVATION_COLUMNS) + " FROM observations "
        "ORDER BY company, period_end, concept, dimension, member, source_year, source_month"
    )
    index = 0
    try:
        while rows := cursor.fetchmany(batch_size):
            frame = pl.DataFrame(rows, schema=list(OBSERVATION_COLUMNS), orient="row")
            frame.write_parquet(parts / f"part-{index:05d}.parquet", compression="zstd")
            index += 1
        if index:
            pl.scan_parquet(parts / "part-*.parquet").sink_parquet(
                destination, compression="zstd"
            )
        else:
            pl.DataFrame(
                schema={column: pl.String for column in OBSERVATION_COLUMNS}
            ).write_parquet(destination)
    finally:
        for part in parts.glob("part-*.parquet"):
            part.unlink()
        parts.rmdir()


def observation_counts(connection: sqlite3.Connection) -> Counter[str]:
    return Counter(dict(connection.execute("SELECT concept, COUNT(*) FROM observations GROUP BY 1")))


def render_extraction_report(connection: sqlite3.Connection) -> str:
    """Render manifest, accounting, units, and total fill-rate diagnostics."""
    integrity = manifest_integrity(connection)
    rows = manifest_rows(connection)
    observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    records = connection.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT company, period_end FROM observations)"
    ).fetchone()[0]
    fill = dict(
        connection.execute(
            "SELECT concept, COUNT(*) FROM (SELECT DISTINCT company, period_end, concept "
            "FROM observations WHERE dimension IS NULL) GROUP BY concept"
        )
    )
    any_fill = dict(
        connection.execute(
            "SELECT concept, COUNT(*) FROM (SELECT DISTINCT company, period_end, concept "
            "FROM observations) GROUP BY concept"
        )
    )
    lines = [
        "# Accounts extraction report",
        "",
        "## Run summary",
        "",
        f"- Archives represented: {len(rows):,}",
        f"- Completed archives: {sum(int(row['complete']) for row in rows):,}",
        f"- iXBRL filings processed: {integrity.filings_processed:,}",
        f"- Long observations: {observations:,}",
        f"- Distinct company/period records: {records:,}",
        f"- Fact accounting closes: **{'yes' if integrity.closes() else 'NO'}**",
        "",
        "## Accounting invariant",
        "",
        "| Bucket | Facts |",
        "|---|---:|",
    ]
    invariant_names = (
        "target_facts_seen",
        "kept_total",
        "kept_member",
        "collapsed_duplicate",
        "ambiguous_nondimensional",
        "member_value_conflict",
        "skipped_multimember",
        "skipped_typed",
        "bad_period_refs",
    )
    for name in invariant_names:
        lines.append(f"| `{name}` | {getattr(integrity, name):,} |")
    lines.extend(
        [
            "",
            "## Other integrity signals",
            "",
            f"- XML filings skipped: {integrity.xml_skipped:,}",
            f"- Filename exceptions: {integrity.filename_exceptions:,}",
            f"- Unparseable filings: {integrity.unparseable_filings:,}",
            f"- Company-number mismatches: {integrity.company_mismatches:,}",
            f"- Non-GBP monetary facts: {integrity.non_gbp_facts:,}",
            f"- Unresolved monetary unit references: {integrity.unresolved_unit_refs:,}",
            "",
            "## Non-dimensional total fill rates",
            "",
            "| Concept | Genuine-total records | Genuine-total rate | Any-observation records | Any-observation rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for concept in TARGET_CONCEPTS:
        count = fill.get(concept, 0)
        rate = 100 * count / records if records else 0
        any_count = any_fill.get(concept, 0)
        any_rate = 100 * any_count / records if records else 0
        lines.append(
            f"| `{concept}` | {count:,} | {rate:.1f}% | {any_count:,} | {any_rate:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Archive manifest",
            "",
            "| Archive | Members | Observations | Complete |",
            "|---|---:|---:|:---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['archive_name']}` | {int(row['member_count']):,} | "
            f"{int(row['observation_count']):,} | "
            f"{'yes' if row['complete'] else 'partial'} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Archives before 2019 remain unvalidated. Do not describe this dataset as 2008–2025 until reconnaissance is run around 2010, 2013, and 2016.",
            "- XML filings are counted but not extracted; the validated 2019–2025 samples were overwhelmingly iXBRL.",
            "- Currency units are resolved in LONG. Non-GBP monetary observations are retained and flagged here; WIDE excludes them by default rather than converting currency.",
            "- Non-zero scale is handled and synthetically tested, but no scale variation appeared in the real recon samples.",
            "- Employee-count availability changes sharply from about 24% in 2019 to 33% in 2020 and 85% in 2021. Treat this as a reporting-regime break, not company signal.",
            "- Equity has a greater-than-10-percentage-point monthly fill-rate range in the panel check, so its missingness is non-random.",
            "- Creditors are dimensionally dominant: genuine non-dimensional totals were about 4% in the two-archive production sample. The panel check's roughly 52% rate includes a legacy dimensional fallback and is not a total benchmark. A null WIDE Creditors total is therefore expected; use curated member columns.",
            "- Restatements remain separate LONG observations. Predictive WIDE publication must use `as_first_reported`; `latest` contains look-ahead information.",
            "",
        ]
    )
    return "\n".join(lines)
