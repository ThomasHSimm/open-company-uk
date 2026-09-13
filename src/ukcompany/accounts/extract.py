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
from collections.abc import Collection
from dataclasses import dataclass, fields
from pathlib import Path

from .core import (
    TARGET_CONCEPTS,
    ExtractedFiling,
    IntegrityCounts,
    extract_filing,
    normalise_scope,
)

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
    "fact_kind",
    "fact_sequence",
    "status",
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
    facts_seen: int = 0
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
        values = dict(values)
        if "facts_seen" not in values and "target_facts_seen" in values:
            values["facts_seen"] = values["target_facts_seen"]
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
        return accounted == self.facts_seen


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
            fact_kind TEXT NOT NULL,
            fact_sequence INTEGER NOT NULL,
            status TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS processed_archives (
            archive_name TEXT PRIMARY KEY,
            archive_size INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            observation_count INTEGER NOT NULL,
            complete INTEGER NOT NULL,
            integrity_json TEXT NOT NULL,
            scope_json TEXT,
            kinds TEXT,
            export_scope_json TEXT,
            export_kinds TEXT,
            export_observation_count INTEGER
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
    observation_columns = {
        item[1] for item in connection.execute("PRAGMA table_info(observations)")
    }
    if "fact_kind" not in observation_columns:
        connection.execute(
            "ALTER TABLE observations ADD COLUMN fact_kind TEXT NOT NULL DEFAULT 'numeric'"
        )
    if "fact_sequence" not in observation_columns:
        connection.execute(
            "ALTER TABLE observations ADD COLUMN fact_sequence INTEGER NOT NULL DEFAULT -1"
        )
    if "status" not in observation_columns:
        connection.execute(
            "ALTER TABLE observations ADD COLUMN status TEXT NOT NULL DEFAULT 'selected'"
        )
    manifest_columns = {
        item[1] for item in connection.execute("PRAGMA table_info(processed_archives)")
    }
    if "scope_json" not in manifest_columns:
        connection.execute("ALTER TABLE processed_archives ADD COLUMN scope_json TEXT")
    if "kinds" not in manifest_columns:
        connection.execute("ALTER TABLE processed_archives ADD COLUMN kinds TEXT")
    if "export_scope_json" not in manifest_columns:
        connection.execute("ALTER TABLE processed_archives ADD COLUMN export_scope_json TEXT")
    if "export_kinds" not in manifest_columns:
        connection.execute("ALTER TABLE processed_archives ADD COLUMN export_kinds TEXT")
    if "export_observation_count" not in manifest_columns:
        connection.execute(
            "ALTER TABLE processed_archives ADD COLUMN export_observation_count INTEGER"
        )
    identity_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'observations_identity'"
    ).fetchone()
    identity_sql = identity_sql_row[0] if identity_sql_row else ""
    if "fact_sequence" not in identity_sql:
        connection.executescript(
            """
            DROP INDEX IF EXISTS observations_identity;
            CREATE UNIQUE INDEX observations_identity ON observations (
                company, source_archive, source_member, fact_sequence, concept, period_end,
                COALESCE(dimension, ''), COALESCE(member, ''), raw_value, scale,
                COALESCE(sign, ''), COALESCE(currency, '')
            );
            """
        )
    return connection


def scope_json(scope: str | Collection[str]) -> str:
    concepts = normalise_scope(scope)
    return json.dumps("all" if concepts is None else sorted(concepts), separators=(",", ":"))


def _scope_covers(
    stored_scope_json: str | None,
    stored_kinds: str | None,
    requested_scope: str | Collection[str],
    requested_kinds: str,
) -> bool:
    if stored_scope_json is None:
        return False
    decoded = json.loads(stored_scope_json)
    stored_scope: frozenset[str] | None = (
        None if decoded == "all" else frozenset(decoded)
    )
    requested = normalise_scope(requested_scope)
    scope_covered = stored_scope is None or (
        requested is not None and stored_scope.issuperset(requested)
    )
    kinds_covered = stored_kinds == "all" or requested_kinds == "numeric-only"
    return scope_covered and kinds_covered


def _stored_archive(connection: sqlite3.Connection, archive: ArchiveSpec) -> tuple | None:
    return connection.execute(
        "SELECT archive_size, member_count, complete, scope_json, kinds "
        "FROM processed_archives "
        "WHERE archive_name = ?",
        (archive.name,),
    ).fetchone()


def archive_recorded_complete(
    connection: sqlite3.Connection,
    name: str,
    *,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> bool:
    """Check completion using only the manifest, even when the ZIP was deleted."""
    row = connection.execute(
        "SELECT scope_json, kinds FROM processed_archives "
        "WHERE archive_name = ? AND complete = 1",
        (name,),
    ).fetchone()
    return row is not None and _scope_covers(row[0], row[1], scope, kinds)


def archive_is_complete(
    connection: sqlite3.Connection,
    archive: ArchiveSpec,
    *,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> bool:
    stored = _stored_archive(connection, archive)
    if not stored or not stored[2] or not _scope_covers(stored[3], stored[4], scope, kinds):
        return False
    archive_size, member_count, _complete, _scope, _kinds = stored
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
        "INSERT OR IGNORE INTO observations ("
        + ", ".join(OBSERVATION_COLUMNS)
        + ") VALUES ("
        + ", ".join("?" for _column in OBSERVATION_COLUMNS)
        + ")",
        (
            (
                filing.company,
                fact.period_end,
                fact.concept,
                fact.fact_kind,
                fact.fact_sequence,
                fact.status,
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
    scope: str | Collection[str],
    kinds: str,
) -> None:
    observation_count = connection.execute(
        "SELECT COUNT(*) FROM observations WHERE source_archive = ?", (archive.name,)
    ).fetchone()[0]
    connection.execute(
        "INSERT INTO processed_archives "
        "(archive_name, archive_size, member_count, observation_count, complete, "
        "integrity_json, scope_json, kinds, export_scope_json, export_kinds, "
        "export_observation_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL) "
        "ON CONFLICT(archive_name) DO UPDATE SET archive_size=excluded.archive_size, "
        "member_count=excluded.member_count, observation_count=excluded.observation_count, "
        "complete=excluded.complete, integrity_json=excluded.integrity_json, "
        "scope_json=excluded.scope_json, kinds=excluded.kinds, export_scope_json=NULL, "
        "export_kinds=NULL, export_observation_count=NULL",
        (
            archive.name,
            archive.path.stat().st_size,
            member_count,
            observation_count,
            int(complete),
            json.dumps(integrity.as_dict(), sort_keys=True),
            scope_json(scope),
            kinds,
        ),
    )
    connection.commit()


def process_archive(
    connection: sqlite3.Connection,
    archive: ArchiveSpec,
    *,
    limit: int | None = None,
    progress_every: int = 10_000,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> ArchiveIntegrity | None:
    """Process or resume one ZIP; return None when a verified completed ZIP is skipped."""
    normalise_scope(scope)
    if kinds not in {"all", "numeric-only"}:
        raise ValueError("kinds must be 'all' or 'numeric-only'")
    if archive_is_complete(connection, archive, scope=scope, kinds=kinds):
        print(f"skip completed: {archive.name}", flush=True)
        return None
    stored = _stored_archive(connection, archive)
    has_legacy_rows = connection.execute(
        "SELECT 1 FROM observations WHERE source_archive = ? AND fact_sequence = -1 LIMIT 1",
        (archive.name,),
    ).fetchone()
    if stored and (
        has_legacy_rows or not _scope_covers(stored[3], stored[4], scope, kinds)
    ):
        connection.execute("DELETE FROM observations WHERE source_archive = ?", (archive.name,))
        connection.execute(
            "DELETE FROM legacy_dimensional_fallbacks WHERE source_archive = ?",
            (archive.name,),
        )
        connection.commit()
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
                filing = extract_filing(
                    data,
                    company,
                    made_up_to_date,
                    scope=scope,
                    kinds=kinds,
                )
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
        _write_manifest(connection, archive, len(infos), complete, integrity, scope, kinds)
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


def _stream_parquet_query(
    connection: sqlite3.Connection,
    output: str | Path,
    query: str,
    parameters: tuple[object, ...] = (),
    *,
    batch_size: int = 250_000,
) -> None:
    """Stream one query through bounded Polars batches to a Parquet file."""
    try:
        import polars as pl
    except ImportError as exc:
        raise RuntimeError("Parquet export requires the project's dev extra (polars)") from exc
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    parts = destination.parent / f".{destination.stem}-parts"
    if parts.exists():
        unexpected = [
            path
            for path in parts.iterdir()
            if not path.is_file() or not path.match("part-*.parquet")
        ]
        if unexpected:
            raise RuntimeError(f"temporary export directory contains unknown files: {parts}")
        for part in parts.glob("part-*.parquet"):
            part.unlink()
        parts.rmdir()
    parts.mkdir()
    cursor = connection.execute(query, parameters)
    index = 0
    string_columns = set(OBSERVATION_COLUMNS) - {
        "fact_sequence",
        "source_year",
        "source_month",
        "scale",
        "is_current",
    }
    schema = {
        column: pl.String if column in string_columns else pl.Int64
        for column in OBSERVATION_COLUMNS
    }
    try:
        while rows := cursor.fetchmany(batch_size):
            frame = pl.DataFrame(rows, schema=schema, orient="row")
            frame.write_parquet(parts / f"part-{index:05d}.parquet", compression="zstd")
            index += 1
        if index:
            pl.scan_parquet(parts / "part-*.parquet").sink_parquet(
                destination, compression="zstd"
            )
        else:
            pl.DataFrame(schema=schema).write_parquet(destination)
    finally:
        for part in parts.glob("part-*.parquet"):
            part.unlink()
        parts.rmdir()


def monthly_parquet_path(output_dir: str | Path, archive_name: str) -> Path:
    archive = parse_archive(archive_name)
    directory = Path(output_dir).expanduser()
    return directory / f"accounts-long-{archive.year:04d}-{archive.month:02d}.parquet"


def export_archive_parquet(
    connection: sqlite3.Connection,
    archive_name: str,
    output_dir: str | Path,
    *,
    batch_size: int = 250_000,
    overwrite: bool = True,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> Path:
    """Stream one manifest-complete archive to its own monthly Parquet."""
    row = connection.execute(
        "SELECT complete, scope_json, kinds, observation_count, export_scope_json, "
        "export_kinds, export_observation_count FROM processed_archives "
        "WHERE archive_name = ?",
        (archive_name,),
    ).fetchone()
    if row is None or not row[0] or not _scope_covers(row[1], row[2], scope, kinds):
        raise ValueError(f"archive is not manifest-complete: {archive_name}")
    destination = monthly_parquet_path(output_dir, archive_name)
    export_current = row[4] == row[1] and row[5] == row[2] and row[6] == row[3]
    if destination.exists() and not overwrite and export_current:
        return destination
    query = (
        "SELECT "
        + ", ".join(OBSERVATION_COLUMNS)
        + " FROM observations WHERE source_archive = ? "
        + "ORDER BY company, period_end, concept, dimension, member, fact_sequence"
    )
    _stream_parquet_query(
        connection,
        destination,
        query,
        (archive_name,),
        batch_size=batch_size,
    )
    connection.execute(
        "UPDATE processed_archives SET export_scope_json = scope_json, "
        "export_kinds = kinds, export_observation_count = observation_count "
        "WHERE archive_name = ?",
        (archive_name,),
    )
    connection.commit()
    return destination


def completed_archive_names(connection: sqlite3.Connection) -> list[str]:
    names = [
        row[0]
        for row in connection.execute(
            "SELECT archive_name FROM processed_archives WHERE complete = 1"
        )
    ]
    return sorted(
        names,
        key=lambda name: (parse_archive(name).year, parse_archive(name).month, name),
    )


def export_completed_archives(
    connection: sqlite3.Connection,
    output_dir: str | Path,
    *,
    start: tuple[int, int] | None = None,
    end: tuple[int, int] | None = None,
    batch_size: int = 250_000,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> list[Path]:
    """Rewrite per-month files for completed manifest rows, optionally within a range."""
    if start is not None and end is not None and start > end:
        raise ValueError("export start month must not be later than end month")
    outputs = []
    for name in completed_archive_names(connection):
        if not archive_recorded_complete(connection, name, scope=scope, kinds=kinds):
            continue
        archive = parse_archive(name)
        key = archive.year, archive.month
        if start is not None and key < start:
            continue
        if end is not None and key > end:
            continue
        outputs.append(
            export_archive_parquet(
                connection,
                name,
                output_dir,
                batch_size=batch_size,
                scope=scope,
                kinds=kinds,
            )
        )
    return outputs


def export_parquet(
    connection: sqlite3.Connection,
    output: str | Path,
    *,
    batch_size: int = 250_000,
) -> None:
    """Explicit opt-in monolithic export; never use as the Stage 1 default."""
    query = (
        "SELECT "
        + ", ".join(OBSERVATION_COLUMNS)
        + " FROM observations "
        + "ORDER BY company, period_end, concept, dimension, member, source_year, source_month"
    )
    _stream_parquet_query(connection, output, query, batch_size=batch_size)


def observation_counts(connection: sqlite3.Connection) -> Counter[str]:
    return Counter(dict(connection.execute("SELECT concept, COUNT(*) FROM observations GROUP BY 1")))


def render_extraction_report(connection: sqlite3.Connection) -> str:
    """Render manifest, accounting, units, and total fill-rate diagnostics."""
    integrity = manifest_integrity(connection)
    rows = manifest_rows(connection)
    observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    concepts = connection.execute("SELECT COUNT(DISTINCT concept) FROM observations").fetchone()[0]
    statuses = dict(connection.execute("SELECT status, COUNT(*) FROM observations GROUP BY 1"))
    fact_kinds = dict(
        connection.execute("SELECT fact_kind, COUNT(*) FROM observations GROUP BY 1")
    )
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
        f"- Distinct concepts: {concepts:,}",
        f"- Selected observations: {statuses.get('selected', 0):,}",
        f"- Retained non-dimensional conflict observations: "
        f"{statuses.get('conflict_nondimensional', 0):,}",
        f"- Retained member-conflict observations: {statuses.get('conflict_member', 0):,}",
        f"- Numeric observations: {fact_kinds.get('numeric', 0):,}",
        f"- Non-numeric observations: {fact_kinds.get('non-numeric', 0):,}",
        f"- Distinct company/period records: {records:,}",
        f"- Fact accounting closes: **{'yes' if integrity.closes() else 'NO'}**",
        "",
        "## Accounting invariant",
        "",
        "| Bucket | Facts |",
        "|---|---:|",
    ]
    invariant_names = (
        "facts_seen",
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
            "| Archive | Scope | Kinds | Members | Observations | Complete |",
            "|---|---|---|---:|---:|:---:|",
        ]
    )
    for row in rows:
        stored_scope = row.get("scope_json")
        decoded_scope = json.loads(str(stored_scope)) if stored_scope is not None else None
        if decoded_scope is None:
            scope_label = "legacy nine-concept"
        elif decoded_scope == "all":
            scope_label = "all"
        else:
            scope_label = ", ".join(decoded_scope)
        lines.append(
            f"| `{row['archive_name']}` | `{scope_label}` | "
            f"`{row.get('kinds') or 'all'}` | {int(row['member_count']):,} | "
            f"{int(row['observation_count']):,} | "
            f"{'yes' if row['complete'] else 'partial'} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Stage 1 now defaults to every inline-XBRL fact, including non-numeric text. Expect roughly 5–10 times the nine-concept slim-table volume; plan against per-month files, never a materialised all-history frame.",
            "- Conflict-tagged observations are retained without a preferred value. Stage 2 must choose a model-specific conflict policy and must not treat them as selected.",
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
