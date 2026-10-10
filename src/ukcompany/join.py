"""Point-in-time joined per-company feature tables.

The selected register snapshot is the base population. PSC and accounts are
left-joined by normalised company number, so companies absent from the selected
register never enter the output. This module builds attributes only: no rules
or composite scores are computed.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ukcompany.psc.loader import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal

JOIN_VERSION = "v1-internal"
OUTPUT_NAME = "joined_company_features.parquet"
MANIFEST_NAME = "join_manifest.json"
FORBIDDEN_GOVERNED_COLUMNS = frozenset(
    {
        "reg_n_companies_same_address",
        "psc_companies_per_person_band_ever",
        "psc_companies_per_person_band_active",
    }
)


@dataclass(frozen=True)
class JoinInputs:
    register_path: Path
    register_report: Path
    register_snapshot_date: str
    psc_path: Path
    psc_report: Path
    psc_snapshot_date: str
    accounts_path: Path
    accounts_report: Path
    accounts_reference_month: int
    reconciliation_report: Path | None = None


def _month_end_boundary(t_yyyymm: int) -> date:
    year, month = divmod(t_yyyymm, 100)
    if year < 1 or not 1 <= month <= 12:
        raise ValueError(f"T must be a valid YYYYMM value, got {t_yyyymm!r}")
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"required metadata file is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read valid JSON metadata from {path}: {exc}") from exc


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"required {label} input is missing: {path}")
    return path


def _validate_report(path: Path, expected: dict[str, object]) -> dict:
    report = _read_json(path)
    mismatches = {
        key: {"expected": value, "actual": report.get(key)}
        for key, value in expected.items()
        if report.get(key) != value
    }
    if mismatches:
        raise ValueError(f"metadata mismatch in {path}: {mismatches}")
    return report


def resolve_join_inputs(data_root: str | Path, t_yyyymm: int, tier: str) -> JoinInputs:
    """Resolve and validate the governed or ungoverned inputs for T.

    Register pairing is exactly the first day of T+1. PSC pairing selects the
    latest available feature snapshot on or before that date. Accounts must be
    the explicitly versioned internal feature table built at exactly T.
    """
    if tier not in {"governed", "ungoverned"}:
        raise ValueError(f"tier must be governed or ungoverned, got {tier!r}")
    root = Path(data_root)
    boundary = _month_end_boundary(t_yyyymm)
    register_date = boundary.isoformat()
    register_mode = "features-governed" if tier == "governed" else "features-ungoverned"
    register_dir = root / "snapshot" / boundary.strftime("%Y-%m") / register_mode
    register_path = _require_file(
        register_dir / "snapshot_company_features.parquet", f"{tier} register feature"
    )
    register_report = register_dir / "features_report.json"
    _validate_report(
        register_report,
        {"snapshot_date": register_date, "tier": tier, "data_governance": tier == "governed"},
    )

    psc_mode = "features-governed" if tier == "governed" else "features-private"
    psc_candidates: list[tuple[date, Path, Path]] = []
    psc_root = root / "psc"
    if psc_root.is_dir():
        for report_path in psc_root.glob(f"????-??-??/{psc_mode}/features_report.json"):
            try:
                snapshot_date = date.fromisoformat(str(_read_json(report_path)["snapshot_date"]))
            except (KeyError, TypeError, ValueError):
                continue
            if snapshot_date <= boundary:
                feature_path = report_path.parent / "psc_company_features.parquet"
                if feature_path.is_file():
                    psc_candidates.append((snapshot_date, feature_path, report_path))
    if not psc_candidates:
        raise FileNotFoundError(
            f"no complete {tier} PSC feature snapshot dated on or before {register_date} "
            f"was found under {psc_root}"
        )
    psc_date, psc_path, psc_report = max(psc_candidates, key=lambda item: item[0])
    expected_psc_tier = "governed" if tier == "governed" else "private"
    _validate_report(
        psc_report,
        {
            "snapshot_date": psc_date.isoformat(),
            "tier": expected_psc_tier,
        },
    )

    accounts_dir = root / "accounts" / f"v2-internal-{t_yyyymm}" / "features" / tier
    accounts_path = _require_file(
        accounts_dir / "accounts_company_features.parquet", f"{tier} accounts feature"
    )
    accounts_report = accounts_dir / "features_report.json"
    _validate_report(
        accounts_report,
        {
            "reference_month_T": t_yyyymm,
            "tier": tier,
            "data_governance": tier == "governed",
        },
    )
    reconciliation = (
        root
        / "accounts"
        / f"v2-internal-{t_yyyymm}"
        / "reports"
        / "accounts-register-reconciliation.json"
    )
    return JoinInputs(
        register_path=register_path,
        register_report=register_report,
        register_snapshot_date=register_date,
        psc_path=psc_path,
        psc_report=psc_report,
        psc_snapshot_date=psc_date.isoformat(),
        accounts_path=accounts_path,
        accounts_report=accounts_report,
        accounts_reference_month=t_yyyymm,
        reconciliation_report=reconciliation if reconciliation.is_file() else None,
    )


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _columns(con, path: Path) -> list[str]:
    source = f"read_parquet({_sql_literal(str(path))})"
    return [row[0] for row in con.sql(f"DESCRIBE SELECT * FROM {source}").fetchall()]


def _source_column_name(source: str, column: str) -> str:
    prefix = f"{source}_"
    return column if column.startswith(prefix) else prefix + column


def _assert_unique_keys(con, path: Path, label: str) -> dict[str, int]:
    source = f"read_parquet({_sql_literal(str(path))})"
    columns = _columns(con, path)
    if "company_number" not in columns:
        raise ValueError(f"{label} input has no company_number column: {path}")
    row = con.sql(
        f"""
        SELECT COUNT(*) AS rows,
               COUNT(*) FILTER (
                   WHERE company_number IS NULL OR trim(CAST(company_number AS VARCHAR)) = ''
               ) AS invalid_keys,
               COUNT(DISTINCT upper(trim(CAST(company_number AS VARCHAR)))) AS distinct_keys
        FROM {source}
        """
    ).fetchone()
    counts = {"rows": int(row[0]), "invalid_keys": int(row[1]), "distinct_keys": int(row[2])}
    if counts["invalid_keys"]:
        raise ValueError(f"{label} input contains {counts['invalid_keys']} null/blank company keys")
    if counts["rows"] != counts["distinct_keys"]:
        duplicates = counts["rows"] - counts["distinct_keys"]
        raise ValueError(
            f"{label} input is not unique after company-number normalisation: "
            f"rows={counts['rows']}, distinct={counts['distinct_keys']}, duplicates={duplicates}"
        )
    return counts


def _dict_rows(cursor) -> list[dict]:
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _coverage(con, joined: str) -> dict:
    totals = con.sql(
        f"""
        SELECT COUNT(*) AS register,
               COUNT(*) FILTER (WHERE has_psc) AS psc,
               COUNT(*) FILTER (WHERE has_accounts) AS accounts,
               COUNT(*) FILTER (WHERE has_psc AND has_accounts) AS all_three,
               COUNT(*) FILTER (WHERE has_psc AND NOT has_accounts) AS register_psc_only,
               COUNT(*) FILTER (WHERE NOT has_psc AND has_accounts) AS register_accounts_only,
               COUNT(*) FILTER (WHERE NOT has_psc AND NOT has_accounts) AS register_only
        FROM {joined}
        """
    ).fetchone()
    source_totals = {
        "register": int(totals[0]),
        "psc": int(totals[1]),
        "accounts": int(totals[2]),
    }
    combinations = {
        "all_three": int(totals[3]),
        "register_psc_only": int(totals[4]),
        "register_accounts_only": int(totals[5]),
        "register_only": int(totals[6]),
    }
    if sum(combinations.values()) != source_totals["register"]:
        raise RuntimeError("mutually exclusive coverage combinations do not close to register")

    def breakdown(column: str) -> list[dict]:
        quoted = _quote_identifier(column)
        cursor = con.execute(
            f"""
            SELECT COALESCE(CAST({quoted} AS VARCHAR), '<null>') AS category,
                   COUNT(*) AS register,
                   COUNT(*) FILTER (WHERE has_psc) AS psc,
                   COUNT(*) FILTER (WHERE has_accounts) AS accounts,
                   COUNT(*) FILTER (WHERE has_psc AND has_accounts) AS all_three,
                   COUNT(*) FILTER (WHERE has_psc) / COUNT(*)::DOUBLE AS psc_share,
                   COUNT(*) FILTER (WHERE has_accounts) / COUNT(*)::DOUBLE AS accounts_share,
                   COUNT(*) FILTER (WHERE has_psc AND has_accounts) / COUNT(*)::DOUBLE
                       AS all_three_share
            FROM {joined}
            GROUP BY 1
            ORDER BY register DESC, category
            """
        )
        return _dict_rows(cursor)

    return {
        "source_totals_within_register": source_totals,
        "mutually_exclusive_combinations": combinations,
        "shares_of_register": {
            key: value / source_totals["register"] for key, value in combinations.items()
        },
        "by_company_type": breakdown("reg_company_type"),
        "by_accounts_category": breakdown("reg_accounts_category"),
    }


def build_join(
    inputs: JoinInputs,
    output_dir: str | Path,
    t_yyyymm: int,
    tier: str,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Build one join tier and return its written provenance manifest."""
    if tier not in {"governed", "ungoverned"}:
        raise ValueError(f"tier must be governed or ungoverned, got {tier!r}")
    boundary = _month_end_boundary(t_yyyymm)
    if date.fromisoformat(inputs.register_snapshot_date) != boundary:
        raise ValueError(
            f"register snapshot must be {boundary.isoformat()} for T={t_yyyymm}, "
            f"got {inputs.register_snapshot_date}"
        )
    if date.fromisoformat(inputs.psc_snapshot_date) > boundary:
        raise ValueError(
            f"PSC snapshot {inputs.psc_snapshot_date} is after the T boundary {boundary}"
        )
    if inputs.accounts_reference_month != t_yyyymm:
        raise ValueError(
            f"accounts features are for T={inputs.accounts_reference_month}, expected {t_yyyymm}"
        )

    paths = {
        "register": _require_file(inputs.register_path, "register feature"),
        "psc": _require_file(inputs.psc_path, "PSC feature"),
        "accounts": _require_file(inputs.accounts_path, "accounts feature"),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_NAME
    manifest_path = output_dir / MANIFEST_NAME
    started = time.monotonic()

    con = _connect(memory_limit_gb, spill_dir)
    try:
        key_counts = {
            label: _assert_unique_keys(con, path, label) for label, path in paths.items()
        }
        columns = {label: _columns(con, path) for label, path in paths.items()}
        aliases: dict[str, list[tuple[str, str]]] = {}
        emitted = {"company_number", "has_psc", "has_accounts"}
        for label, source_prefix in (("register", "reg"), ("psc", "psc"), ("accounts", "acc")):
            aliases[label] = []
            for column in columns[label]:
                if column == "company_number":
                    continue
                output_column = _source_column_name(source_prefix, column)
                if output_column in emitted:
                    raise ValueError(f"duplicate output column after prefixing: {output_column}")
                emitted.add(output_column)
                aliases[label].append((column, output_column))

        if tier == "governed":
            leaked = sorted(FORBIDDEN_GOVERNED_COLUMNS & emitted)
            if leaked:
                raise ValueError(f"governed join input would expose forbidden columns: {leaked}")

        for label, path in paths.items():
            source = f"read_parquet({_sql_literal(str(path))})"
            con.execute(
                f"CREATE TEMP VIEW {label} AS SELECT "
                f"upper(trim(CAST(company_number AS VARCHAR))) AS company_number, "
                f"* EXCLUDE (company_number) FROM {source}"
            )

        select_columns = ["r.company_number AS company_number"]
        for label, table_alias in (("register", "r"), ("psc", "p"), ("accounts", "a")):
            select_columns.extend(
                f"{table_alias}.{_quote_identifier(source)} AS {_quote_identifier(target)}"
                for source, target in aliases[label]
            )
        select_columns.extend(
            [
                "(p.company_number IS NOT NULL) AS has_psc",
                "(a.company_number IS NOT NULL) AS has_accounts",
            ]
        )
        joined_select = (
            "SELECT\n  "
            + ",\n  ".join(select_columns)
            + "\nFROM register r\nLEFT JOIN psc p USING (company_number)\n"
            + "LEFT JOIN accounts a USING (company_number)"
        )
        con.execute(
            f"COPY ({joined_select}) TO {_sql_literal(str(output_path))} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        joined = f"read_parquet({_sql_literal(str(output_path))})"
        output_rows = int(con.sql(f"SELECT COUNT(*) FROM {joined}").fetchone()[0])
        output_distinct = int(
            con.sql(f"SELECT COUNT(DISTINCT company_number) FROM {joined}").fetchone()[0]
        )
        if output_rows != key_counts["register"]["rows"]:
            raise RuntimeError(
                f"join changed register row count: register={key_counts['register']['rows']}, "
                f"output={output_rows}"
            )
        if output_distinct != output_rows:
            raise RuntimeError(
                f"joined output key is not unique: rows={output_rows}, distinct={output_distinct}"
            )
        on_disk_columns = set(_columns(con, output_path))
        if tier == "governed":
            leaked = sorted(FORBIDDEN_GOVERNED_COLUMNS & on_disk_columns)
            if leaked:
                raise RuntimeError(f"governed joined output contains forbidden columns: {leaked}")

        coverage = _coverage(con, joined)
        matched_psc = coverage["source_totals_within_register"]["psc"]
        matched_accounts = coverage["source_totals_within_register"]["accounts"]
        excluded = {
            "label": "absent from the selected register",
            "psc": key_counts["psc"]["rows"] - matched_psc,
            "accounts": key_counts["accounts"]["rows"] - matched_accounts,
            "classification_note": (
                "Absence from this register snapshot is not, by itself, evidence that a company "
                "is dissolved; no dissolved classification is assigned without supporting status data."
            ),
        }
    finally:
        con.close()

    build_seconds = time.monotonic() - started
    input_metadata = {}
    source_dates = {
        "register": inputs.register_snapshot_date,
        "psc": inputs.psc_snapshot_date,
        "accounts": str(inputs.accounts_reference_month),
    }
    report_paths = {
        "register": inputs.register_report,
        "psc": inputs.psc_report,
        "accounts": inputs.accounts_report,
    }
    for label, path in paths.items():
        report_path = report_paths[label]
        input_metadata[label] = {
            "date": source_dates[label],
            "path": str(path),
            "sha256": sha256_file(path),
            "rows": key_counts[label]["rows"],
            "metadata_path": str(report_path),
            "metadata_sha256": sha256_file(report_path),
        }

    reconciliation_explanation = None
    if inputs.reconciliation_report is not None:
        reconciliation = _read_json(inputs.reconciliation_report)
        both_present = int(reconciliation.get("both_present", 0))
        accounts_overlap = coverage["source_totals_within_register"]["accounts"]
        register_date_absent = int(reconciliation.get("buckets", {}).get("register_date_absent", 0))
        if accounts_overlap - both_present != register_date_absent:
            raise RuntimeError(
                "accounts overlap does not reconcile to the accounts/register date comparison: "
                f"overlap={accounts_overlap}, both_present={both_present}, "
                f"register_date_absent={register_date_absent}"
            )
        reconciliation_explanation = {
            "report_path": str(inputs.reconciliation_report),
            "report_sha256": sha256_file(inputs.reconciliation_report),
            "accounts_rows_overlapping_register": accounts_overlap,
            "both_sources_with_period_dates": both_present,
            "difference": accounts_overlap - both_present,
            "explanation": (
                "These accounts feature rows overlap the register by company number but the "
                "register LastMadeUpDate is absent, so they are outside the reconciliation's "
                "both-dates-present denominator. They remain in the join with has_accounts=true."
            ),
        }

    manifest = {
        "join_version": JOIN_VERSION,
        "internal_only": True,
        "reference_month_T": t_yyyymm,
        "tier": tier,
        "generated_at": datetime.now(UTC).isoformat(),
        "pairing": {
            "register_snapshot_date": inputs.register_snapshot_date,
            "psc_snapshot_date": inputs.psc_snapshot_date,
            "accounts_reference_month": inputs.accounts_reference_month,
            "rule": (
                "Register is dated the first day of T+1; PSC is the latest available snapshot "
                "on or before that date; accounts rows were available in registration month <= T."
            ),
            "archive_timing_note": (
                "Accounts registration-month availability is distinct from monthly ZIP "
                "publication/download time; this does not claim the ZIP existed at month-end."
            ),
        },
        "inputs": input_metadata,
        "key_assertions": {
            "normalisation": "upper(trim(company_number))",
            "all_source_keys_unique": True,
            "register_rows_unchanged": True,
            "register_rows": key_counts["register"]["rows"],
            "output_rows": output_rows,
        },
        "coverage_flag_meanings": {
            "has_psc": (
                "True when a PSC feature source row matched the register company, independently "
                "of null feature values. False means absent from this PSC snapshot; this can include "
                "companies outside the PSC regime and does not mean a null-valued PSC attribute."
            ),
            "has_accounts": (
                "True when an accounts feature source row available by T matched the register "
                "company, independently of null feature values. False means no matching iXBRL-derived "
                "feature row by T; non-iXBRL filing coverage and strong company-size skew are known limits."
            ),
        },
        "coverage": coverage,
        "excluded_source_companies": excluded,
        "accounts_reconciliation": reconciliation_explanation,
        "governance": {
            "forbidden_columns": sorted(FORBIDDEN_GOVERNED_COLUMNS),
            "governed_schema_assertion_applicable": tier == "governed",
            "governed_schema_assertion_passed": (
                not (FORBIDDEN_GOVERNED_COLUMNS & on_disk_columns)
                if tier == "governed"
                else None
            ),
        },
        "output": {
            "path": str(output_path),
            "sha256": sha256_file(output_path),
            "bytes": output_path.stat().st_size,
            "rows": output_rows,
            "columns": len(on_disk_columns),
            "build_seconds": build_seconds,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_join_tiers(
    data_root: str | Path,
    output_root: str | Path,
    t_yyyymm: int,
    *,
    tiers: tuple[str, ...] = ("governed", "ungoverned"),
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Resolve and build requested tiers, then write a root manifest."""
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    tier_manifests = {}
    for tier in tiers:
        inputs = resolve_join_inputs(data_root, t_yyyymm, tier)
        tier_manifests[tier] = build_join(
            inputs,
            output_root / tier,
            t_yyyymm,
            tier,
            memory_limit_gb=memory_limit_gb,
            spill_dir=spill_dir,
        )
    root_manifest = {
        "join_version": JOIN_VERSION,
        "internal_only": True,
        "reference_month_T": t_yyyymm,
        "tiers": {
            tier: {
                "manifest_path": str(output_root / tier / MANIFEST_NAME),
                "manifest_sha256": sha256_file(output_root / tier / MANIFEST_NAME),
                "output_path": manifest["output"]["path"],
                "output_sha256": manifest["output"]["sha256"],
            }
            for tier, manifest in tier_manifests.items()
        },
    }
    (output_root / MANIFEST_NAME).write_text(
        json.dumps(root_manifest, indent=2), encoding="utf-8"
    )
    return tier_manifests
