"""Reconcile accounts features with the aligned Companies House register snapshot."""

from __future__ import annotations

import glob
import json
from pathlib import Path

from ukcompany.psc.loader import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal


def reconcile_accounts_register(
    features_path: str | Path,
    register_glob: str,
    *,
    t_yyyymm: int,
    register_snapshot_date: str,
    output_path: str | Path | None = None,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict:
    """Compare latest account period ends with register ``Accounts.LastMadeUpDate``."""
    register_paths = sorted(glob.glob(register_glob))
    if not register_paths:
        raise FileNotFoundError(f"no register parts matched {register_glob}")
    register_list = "[" + ", ".join(_sql_literal(path) for path in register_paths) + "]"
    register_sql = f"read_csv({register_list}, header=true, all_varchar=true, ignore_errors=true)"
    features_sql = f"read_parquet({_sql_literal(str(features_path))})"

    connection = _connect(memory_limit_gb, spill_dir)
    try:
        names = {
            row[0].strip(): row[0]
            for row in connection.sql(f"DESCRIBE SELECT * FROM {register_sql}").fetchall()
        }
        company_column = '"' + names.get("CompanyNumber", "CompanyNumber").replace('"', '""') + '"'
        last_made_up_column = (
            '"'
            + names.get("Accounts.LastMadeUpDate", "Accounts.LastMadeUpDate").replace('"', '""')
            + '"'
        )
        connection.execute(
            f"""
            CREATE TEMP TABLE register AS
            SELECT upper(trim({company_column})) AS company_number,
                   try_strptime(trim({last_made_up_column}), '%d/%m/%Y')::DATE
                       AS register_last_made_up_date
            FROM {register_sql}
            WHERE trim({company_column}) <> ''
            """
        )
        register_rows, register_companies = connection.execute(
            "SELECT count(*), count(DISTINCT company_number) FROM register"
        ).fetchone()
        if register_rows != register_companies:
            raise RuntimeError(
                "register snapshot is not one row per company: "
                f"rows={register_rows}, distinct={register_companies}"
            )
        feature_rows = connection.execute(f"SELECT count(*) FROM {features_sql}").fetchone()[0]
        outside_register = connection.execute(
            f"""
            SELECT count(*)
            FROM {features_sql} features
            ANTI JOIN register USING (company_number)
            """
        ).fetchone()[0]
        row = connection.execute(
            f"""
            SELECT
                count(*) FILTER (
                    WHERE features.latest_period_end = register.register_last_made_up_date
                ) AS exact,
                count(*) FILTER (
                    WHERE features.latest_period_end IS NULL
                      AND register.register_last_made_up_date IS NULL
                ) AS both_absent,
                count(*) FILTER (
                    WHERE features.latest_period_end IS NULL
                      AND register.register_last_made_up_date IS NOT NULL
                ) AS no_accounts_feature,
                count(*) FILTER (
                    WHERE features.latest_period_end < register.register_last_made_up_date
                ) AS register_newer,
                count(*) FILTER (
                    WHERE features.latest_period_end > register.register_last_made_up_date
                ) AS accounts_newer,
                count(*) FILTER (
                    WHERE features.latest_period_end IS NOT NULL
                      AND register.register_last_made_up_date IS NULL
                ) AS register_date_absent
            FROM register
            LEFT JOIN {features_sql} features USING (company_number)
            """
        ).fetchone()
    finally:
        connection.close()

    labels = (
        "exact",
        "both_absent",
        "no_accounts_feature",
        "register_newer",
        "accounts_newer",
        "register_date_absent",
    )
    buckets = dict(zip(labels, row, strict=True))
    both_present = buckets["exact"] + buckets["register_newer"] + buckets["accounts_newer"]
    report = {
        "reference_month_T": t_yyyymm,
        "register_snapshot_date": register_snapshot_date,
        "features_path": str(features_path),
        "register_glob": register_glob,
        "register_rows": register_rows,
        "feature_rows": feature_rows,
        "feature_companies_outside_register": outside_register,
        "buckets": buckets,
        "both_present": both_present,
        "exact_match_rate_both_present": buckets["exact"] / both_present if both_present else None,
    }
    if sum(buckets.values()) != register_rows:
        raise RuntimeError(
            f"reconciliation buckets do not close: {sum(buckets.values())} != {register_rows}"
        )
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
