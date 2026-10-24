"""Per-company accounts features for a reference date T (Handoff 02, Stage B).

T is an **end-of-month** boundary (a `YYYYMM` archive month). One row per company that has any
accounts filing available by T, built from the WIDE `as_first_reported` table and its point-in-time
key `row_available_yyyymm` (the archive month by which the whole row was known; see
docs/design-accounts-features.md). `accounts_category` is the only column that comes from elsewhere -
the register snapshot that the caller pairs to T. **Pairing rule:** the CH `BasicCompanyData`
snapshot is published dated `YYYY-MM-01` and reflects the register state at the *start* of that month
(i.e. end of the previous month), so the snapshot aligned to T (end of archive month M) is the one
dated `(M+1)-01` - the latest snapshot dated <= the first day of T+1. For T = 2026-07 that is the
2026-08-01 snapshot; pass its CSV parts as `register_glob`.

Design decisions (approved, Handoff 02): **row-level** point-in-time (only 0.0036% of rows have
cells spanning more than one archive month, well under the 1-2% threshold); `current_ratio` is
null on a zero or missing denominator (never +/-inf); employee bands follow the Companies Act
thresholds; period-over-period changes are null across a gap > 18 months.

Attributes only. **No feature is person-derived**, so the governed and ungoverned tiers are
identical - the `data_governance` switch is kept only for symmetry with the register/PSC tables.
"""

from __future__ import annotations

import glob as _glob
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ukcompany.duckdb_backend import (
    PathInput,
    duckdb_path_sql,
    query_one,
    require_local_path,
    select_duckdb_backend,
    uri_scheme,
)
from ukcompany.psc.loader import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal

# Filter obviously-corrupt period-end dates (iXBRL mis-tags produce years like 0001 / 3020). The
# upper bound is T's year + 1 so a legitimately recent period is never dropped.
PLAUSIBLE_PERIOD_START = "2010-01-01"
MAX_PRIOR_GAP_MONTHS = 18          # a wider gap => treat as no comparable prior period
EMPLOYEE_BANDS = ("0", "1-10", "11-50", "51-250", "251+")  # Companies Act size thresholds

# No accounts feature is person-derived, so nothing is dropped in governed mode; the tiers are
# identical. Kept as an (empty) list so the written-schema assertion mirrors the other tables.
GOVERNED_FEATURE_DROPPED: tuple[str, ...] = ()

FEATURE_COLUMNS = (
    "company_number",
    "latest_period_end",
    "prior_period_end",
    "n_periods_available",
    "months_since_latest_period_end",
    "prior_gap_months",
    "equity",
    "current_assets",
    "creditors_within_one_year",
    "net_current_assets",
    "cash",
    "negative_equity",
    "net_current_liabilities",
    "current_ratio",
    "employee_band",
    "employees_unit_anomaly",
    "d_equity",
    "d_net_current_assets",
    "d_cash",
    "accounts_category",
)


def _register_company_number_col(con, register_sql: str) -> str:
    """The register's company-number column (DuckDB strips the file's leading-space headers)."""
    names = {r[0].strip(): r[0] for r in con.sql(f"DESCRIBE SELECT * FROM {register_sql}").fetchall()}
    actual = names.get("CompanyNumber", "CompanyNumber")
    return '"' + actual.replace('"', '""') + '"'


def _month_difference_sql(
    later_year: str,
    later_month: str,
    earlier_date: str,
) -> str:
    return (
        f"(({later_year}) - year({earlier_date})) * 12 + "
        f"(({later_month}) - month({earlier_date}))"
    )


def _account_feature_select_sql(
    *,
    latest_alias: str,
    prior_alias: str,
    reference_yyyymm: str,
    accounts_category: str,
) -> str:
    """Return the shared accounts feature projection for population and row assignment."""
    latest = latest_alias
    prior = prior_alias
    reference_year = f"CAST(floor(({reference_yyyymm}) / 100) AS INTEGER)"
    reference_month = f"CAST(({reference_yyyymm}) % 100 AS INTEGER)"
    months_since = _month_difference_sql(reference_year, reference_month, f"{latest}.pe")
    prior_gap = _month_difference_sql(
        f"year({latest}.pe)", f"month({latest}.pe)", f"{prior}.prior_pe"
    )
    employee_band = (
        f"CASE WHEN {latest}.employees IS NULL THEN NULL "
        f"WHEN {latest}.employees <= 0 THEN '0' "
        f"WHEN {latest}.employees <= 10 THEN '1-10' "
        f"WHEN {latest}.employees <= 50 THEN '11-50' "
        f"WHEN {latest}.employees <= 250 THEN '51-250' ELSE '251+' END"
    )
    return f"""
        {latest}.pe AS latest_period_end,
        {prior}.prior_pe AS prior_period_end,
        {latest}.n_periods AS n_periods_available,
        CASE WHEN {latest}.pe IS NULL THEN NULL ELSE {months_since} END
            AS months_since_latest_period_end,
        CASE WHEN {prior}.prior_pe IS NULL THEN NULL ELSE {prior_gap} END AS prior_gap_months,
        {latest}.equity,
        {latest}.current_assets,
        {latest}.creditors_within_one_year,
        {latest}.net_current_assets,
        {latest}.cash,
        CASE WHEN {latest}.equity IS NULL THEN NULL ELSE {latest}.equity < 0 END
            AS negative_equity,
        CASE WHEN {latest}.net_current_assets IS NULL THEN NULL
             ELSE {latest}.net_current_assets < 0 END AS net_current_liabilities,
        CASE WHEN {latest}.creditors_within_one_year IS NULL
                  OR {latest}.creditors_within_one_year = 0
             THEN NULL ELSE {latest}.current_assets / {latest}.creditors_within_one_year
             END AS current_ratio,
        {employee_band} AS employee_band,
        {latest}.employees_unit_anomaly,
        CASE WHEN {prior}.prior_pe IS NULL OR {prior_gap} > {MAX_PRIOR_GAP_MONTHS} THEN NULL
             ELSE {latest}.equity - {prior}.p_equity END AS d_equity,
        CASE WHEN {prior}.prior_pe IS NULL OR {prior_gap} > {MAX_PRIOR_GAP_MONTHS} THEN NULL
             ELSE {latest}.net_current_assets - {prior}.p_nca END AS d_net_current_assets,
        CASE WHEN {prior}.prior_pe IS NULL OR {prior_gap} > {MAX_PRIOR_GAP_MONTHS} THEN NULL
             ELSE {latest}.cash - {prior}.p_cash END AS d_cash,
        {accounts_category} AS accounts_category
    """.strip()


def build_accounts_features(
    wide_path: PathInput,
    register_glob: PathInput,
    output_dir: str | Path,
    t_yyyymm: int,
    *,
    data_governance: bool = True,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
    duckdb_backend: str | None = None,
    fsspec_options: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict:
    """Build the per-company accounts feature table at reference month T and write it as Parquet."""
    output_dir = require_local_path(output_dir, "accounts features output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    mode = "governed" if data_governance else "ungoverned"
    features_path = output_dir / "accounts_company_features.parquet"
    report_path = output_dir / "features_report.json"
    ty = t_yyyymm // 100
    upper_period = f"{ty + 1}-12-31"

    if isinstance(register_glob, (str, Path)) and not uri_scheme(register_glob):
        reg_paths: PathInput = sorted(_glob.glob(str(register_glob)))
        if not reg_paths:
            raise FileNotFoundError(f"no register parts matched {register_glob}")
    else:
        # Remote globs and explicit lists are resolved by the selected DuckDB filesystem.
        # HTTP servers commonly cannot list wildcard paths, so callers should pass an
        # explicit URL (or URL list) for HTTP snapshots.
        reg_paths = register_glob
    register_sql = (
        f"read_csv({duckdb_path_sql(reg_paths)}, header=true, all_varchar=true, "
        "ignore_errors=true)"
    )

    selected_backend = select_duckdb_backend(duckdb_backend, (wide_path, reg_paths))
    con = _connect(
        memory_limit_gb,
        spill_dir,
        duckdb_backend=selected_backend,
        input_paths=(wide_path, reg_paths),
        fsspec_options=fsspec_options,
    )
    try:
        wide = f"read_parquet({duckdb_path_sql(wide_path)})"
        # Rank the periods available by T (row-level point-in-time), newest first.
        con.execute(
            f"""
            CREATE TEMP TABLE ranked AS
            SELECT company,
                   CAST(period_end AS DATE) AS pe,
                   "Equity" AS equity,
                   "CurrentAssets" AS current_assets,
                   "creditors_within_one_year" AS creditors_within_one_year,
                   "NetCurrentAssetsLiabilities" AS net_current_assets,
                   "CashBankOnHand" AS cash,
                   "AverageNumberEmployeesDuringPeriod" AS employees,
                   "employees_unit_anomaly" AS employees_unit_anomaly,
                   row_number() OVER (PARTITION BY company ORDER BY CAST(period_end AS DATE) DESC)
                       AS rn,
                   count(*) OVER (PARTITION BY company) AS n_periods
            FROM {wide}
            WHERE row_available_yyyymm <= {t_yyyymm}
              AND period_end >= {_sql_literal(PLAUSIBLE_PERIOD_START)}
              AND period_end <= {_sql_literal(upper_period)}
            """
        )
        con.execute("CREATE TEMP TABLE latest AS SELECT * FROM ranked WHERE rn = 1")
        con.execute(
            "CREATE TEMP TABLE prior AS SELECT company, pe AS prior_pe, equity AS p_equity, "
            "net_current_assets AS p_nca, cash AS p_cash FROM ranked WHERE rn = 2"
        )
        cn = _register_company_number_col(con, register_sql)
        # DuckDB strips the leading-space headers, so these resolve to the clean names.
        con.execute(
            f"""
            CREATE TEMP TABLE reg AS
            SELECT upper(trim({cn})) AS company, "Accounts.AccountCategory" AS accounts_category
            FROM {register_sql} WHERE trim({cn}) <> ''
            """
        )

        feature_projection = _account_feature_select_sql(
            latest_alias="l",
            prior_alias="p",
            reference_yyyymm=str(t_yyyymm),
            accounts_category="reg.accounts_category",
        )
        con.execute(
            f"""
            CREATE TEMP TABLE features AS
            SELECT
                l.company AS company_number,
                {feature_projection}
            FROM latest l
            LEFT JOIN prior p USING (company)
            LEFT JOIN reg USING (company)
            """
        )
        select_cols = ", ".join(FEATURE_COLUMNS)
        con.execute(
            f"COPY (SELECT {select_cols} FROM features) "
            f"TO {_sql_literal(str(features_path))} (FORMAT PARQUET)"
        )
        # Written-schema assertion (trivial here: nothing is person-derived, so nothing is dropped).
        on_disk = {row[0] for row in con.sql(
            f"DESCRIBE SELECT * FROM read_parquet({_sql_literal(str(features_path))})"
        ).fetchall()}
        if data_governance:
            leaked = sorted(on_disk & set(GOVERNED_FEATURE_DROPPED))
            if leaked:
                raise RuntimeError(f"governed accounts features retain dropped columns: {leaked}")

        n_companies = query_one(
            con,
            f"SELECT COUNT(*) FROM read_parquet({_sql_literal(str(features_path))})"
        )[0]
        fill = {
            c: query_one(con, f"SELECT COUNT({c}) FROM features")[0]
            for c in ("equity", "current_ratio", "cash", "employee_band",
                      "d_equity", "accounts_category")
        }
    finally:
        con.close()

    report = {
        "reference_month_T": t_yyyymm,
        "tier": mode,
        "data_governance": data_governance,
        "n_companies": n_companies,
        "fill_counts": fill,
        "wide_source": str(wide_path),
        "register_source_glob": str(register_glob),
        "duckdb_backend": selected_backend,
        "outputs": {"accounts_company_features": str(features_path)},
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
