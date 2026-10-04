"""Task 4: PSC bulk-snapshot coverage against the live register.

Joins the per-company PSC feature table to a Basic Company Data one-file register snapshot and
reports, aggregates only:
  * what share of register companies have any PSC record in the snapshot (coverage),
  * the uncovered companies broken down by company type (CompanyCategory) and status,
  * the reverse gap: snapshot companies absent from the register (dissolved / historical).

Usage:
    python scripts/psc_coverage_check.py \
        --features data/psc/2026-09-25/features-governed/psc_company_features.parquet \
        --register ~/Downloads/BasicCompanyDataAsOneFile-2026-09-01.csv \
        --register-date 2026-09-01 --snapshot-date 2026-09-25 \
        --out docs/psc-coverage-2026-09-25.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ukcompany.psc.loader import _connect, _sql_literal


def _find_column(describe_rows, *needles) -> str:
    """Return the CSV column whose normalised name contains all needles (case/space-insensitive)."""
    for row in describe_rows:
        name = row[0]
        flat = name.strip().lower().replace(" ", "")
        if all(n in flat for n in needles):
            return name
    raise KeyError(f"no register column matching {needles}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True)
    ap.add_argument("--register", required=True)
    ap.add_argument("--register-date", required=True)
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duckdb-memory-gb", type=int, default=8)
    args = ap.parse_args()

    con = _connect(args.duckdb_memory_gb)
    try:
        reg_csv = (
            f"read_csv({_sql_literal(str(Path(args.register).expanduser()))}, "
            f"header=true, all_varchar=true, ignore_errors=true)"
        )
        describe = con.sql(f"DESCRIBE SELECT * FROM {reg_csv}").fetchall()
        col_number = _find_column(describe, "companynumber")
        col_category = _find_column(describe, "companycategory")
        col_status = _find_column(describe, "companystatus")

        con.execute(
            f"""
            CREATE TEMP TABLE reg AS
            SELECT upper(trim("{col_number}")) AS company_number,
                   "{col_category}" AS category,
                   "{col_status}" AS status
            FROM {reg_csv}
            WHERE "{col_number}" IS NOT NULL AND trim("{col_number}") <> ''
            """
        )
        con.execute(
            f"CREATE TEMP TABLE feat AS SELECT DISTINCT company_number "
            f"FROM read_parquet({_sql_literal(args.features)})"
        )

        n_register = con.sql("SELECT COUNT(*) FROM reg").fetchone()[0]
        n_features = con.sql("SELECT COUNT(*) FROM feat").fetchone()[0]
        covered, uncovered = con.sql(
            "SELECT COUNT(*) FILTER (WHERE f.company_number IS NOT NULL), "
            "       COUNT(*) FILTER (WHERE f.company_number IS NULL) "
            "FROM reg LEFT JOIN feat f USING (company_number)"
        ).fetchone()
        snapshot_not_in_register = con.sql(
            "SELECT COUNT(*) FROM feat f LEFT JOIN reg USING (company_number) "
            "WHERE reg.company_number IS NULL"
        ).fetchone()[0]

        by_category = con.sql(
            """
            SELECT reg.category,
                   COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE f.company_number IS NOT NULL) AS covered,
                   COUNT(*) FILTER (WHERE f.company_number IS NULL) AS uncovered
            FROM reg LEFT JOIN feat f USING (company_number)
            GROUP BY reg.category
            ORDER BY uncovered DESC
            """
        ).fetchall()
        # Active-only view: 'Active' status is the clearest "live" subset.
        active_total, active_covered = con.sql(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE f.company_number IS NOT NULL) "
            "FROM reg LEFT JOIN feat f USING (company_number) WHERE reg.status = 'Active'"
        ).fetchone()
    finally:
        con.close()

    cov_pct = 100.0 * covered / n_register if n_register else float("nan")
    act_pct = 100.0 * active_covered / active_total if active_total else float("nan")
    lines = [
        f"# PSC bulk-snapshot coverage vs the register ({args.snapshot_date} snapshot)",
        "",
        f"PSC snapshot: **{args.snapshot_date}**. Register: Basic Company Data one-file, "
        f"**{args.register_date}**. Join key: company number. Aggregates only.",
        "",
        f"- Register companies: **{n_register:,}**",
        f"- Feature-table companies (any PSC record in the snapshot): **{n_features:,}**",
        f"- Register companies **covered** (have a PSC row): **{covered:,}** "
        f"(**{cov_pct:.2f}%**)",
        f"- Register companies **uncovered**: **{uncovered:,}**",
        f"- Register **Active**-status companies covered: **{active_covered:,} / "
        f"{active_total:,}** (**{act_pct:.2f}%**)",
        f"- Snapshot companies **absent from the register** (dissolved / historical): "
        f"**{snapshot_not_in_register:,}**",
        "",
        "## Uncovered register companies by company type",
        "",
        "| CompanyCategory | register | covered | uncovered | uncovered % |",
        "|---|---:|---:|---:|---:|",
    ]
    for category, n, cov, unc in by_category:
        pct = 100.0 * unc / n if n else float("nan")
        label = category if category not in (None, "") else "(blank)"
        lines.append(f"| {label} | {n:,} | {cov:,} | {unc:,} | {pct:.1f}% |")
    lines += [
        "",
        "> **Reading this.** The register contains no dissolved companies, so the snapshot "
        "companies absent from it are dissolved / struck-off entities whose PSC records the "
        "snapshot still carries. Company types shown ~100% uncovered (Charitable Incorporated "
        "Organisations, Registered Societies, Scottish CIOs, Royal Charter companies, "
        "Investment Companies with Variable Capital, UK Economic Interest Groupings, Industrial "
        "& Provident Societies) are **outside the PSC regime** - they have no PSCs to file, so "
        "their absence is expected. PSC-regime types (private limited, LLP, PLC, CIC, guarantee "
        "companies, overseas entities) are near-fully covered. Uncovered counts are a "
        "data-completeness measure, not a compliance finding.",
        "",
    ]

    out = Path(args.out)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"coverage: {covered:,}/{n_register:,} ({cov_pct:.2f}%); "
          f"active {active_covered:,}/{active_total:,} ({act_pct:.2f}%); wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
