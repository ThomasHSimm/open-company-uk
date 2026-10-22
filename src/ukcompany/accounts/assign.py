"""Assign point-in-time accounts features to observation rows."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Literal

from ukcompany.assignment import (
    normalise_snapshot_sources,
    prepare_observations,
    require_snapshot_columns,
    restore_observation_index,
    snapshot_catalog_sql,
    snapshot_union_sql,
)
from ukcompany.duckdb_backend import PathInput, PathValue, duckdb_path_sql

from .features import (
    FEATURE_COLUMNS,
    PLAUSIBLE_PERIOD_START,
    _account_feature_select_sql,
)
from .ooc import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal


def _accounts_cutoff_sql(policy: str) -> str:
    reference = "__ukcompany_reference_date"
    if policy == "previous_complete_month":
        boundary = f"date_trunc('month', {reference}) - INTERVAL '1 month'"
    elif policy == "same_month":
        boundary = reference
    else:
        raise ValueError(
            "availability_policy must be 'previous_complete_month' or 'same_month'"
        )
    return f"CAST(year({boundary}) * 100 + month({boundary}) AS INTEGER)"


def assign_accounts_features(
    observations: Any,
    wide_path: PathInput,
    *,
    company_number_column: str = "company_number",
    date_column: str = "date",
    availability_policy: Literal["previous_complete_month", "same_month"] = (
        "previous_complete_month"
    ),
    register_feature_snapshots: Mapping[
        str | date | datetime, PathValue
    ] | None = None,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
    duckdb_backend: str | None = None,
    fsspec_options: Mapping[str, Mapping[str, Any]] | None = None,
):
    """Return ``observations`` with accounts features assigned as of each row's date.

    Accounts availability is month-grained.  The default uses the previous complete month,
    preventing a mid-month observation from seeing filings registered later in that month.
    ``same_month`` is suitable only when input dates represent an end-of-month boundary.

    ``register_feature_snapshots`` optionally maps snapshot dates to outputs from
    ``build_snapshot_features``.  When omitted, ``accounts_category`` and the register
    snapshot provenance column are null; a present-day category is never silently applied
    to historical rows.
    """
    output_columns = (
        "accounts_reference_yyyymm",
        "accounts_register_snapshot_date_used",
        "has_accounts",
        *FEATURE_COLUMNS[1:],
    )
    prepared, original_index = prepare_observations(
        observations,
        company_number_column=company_number_column,
        date_column=date_column,
        appended_columns=output_columns,
    )
    if prepared.empty:
        import pandas as pd

        result = observations.copy()
        for column in output_columns:
            result[column] = pd.Series(index=result.index, dtype="object")
        return result

    cutoff_sql = _accounts_cutoff_sql(availability_policy)
    register_sources = (
        normalise_snapshot_sources(
            register_feature_snapshots, label="register feature snapshots"
        )
        if register_feature_snapshots is not None
        else ()
    )
    input_paths: tuple[PathInput, ...] = (wide_path,) + tuple(
        path for _, path in register_sources
    )
    connection = _connect(
        memory_limit_gb,
        spill_dir,
        duckdb_backend=duckdb_backend,
        input_paths=input_paths,
        fsspec_options=fsspec_options,
    )
    try:
        connection.register("__ukcompany_observations", prepared)
        wide = f"read_parquet({duckdb_path_sql(wide_path)})"

        register_ctes = ""
        register_joins = ""
        accounts_category = "NULL::VARCHAR"
        register_date = "NULL::DATE"
        if register_sources:
            require_snapshot_columns(
                connection,
                register_sources,
                required=("company_number", "accounts_category"),
                label="register feature snapshot",
            )
            catalog = snapshot_catalog_sql(register_sources)
            register_union = snapshot_union_sql(
                register_sources,
                columns=("company_number", "accounts_category"),
            )
            register_ctes = f""",
            register_catalog AS (SELECT * FROM {catalog}),
            register_features AS ({register_union}),
            register_choice AS (
                SELECT o.__ukcompany_row_id,
                       max(c.snapshot_date) AS register_snapshot_date
                FROM observations o
                LEFT JOIN register_catalog c
                  ON c.snapshot_date <= o.__ukcompany_reference_date
                GROUP BY o.__ukcompany_row_id
            )
            """
            register_joins = """
            LEFT JOIN register_choice rc USING (__ukcompany_row_id)
            LEFT JOIN register_features reg
              ON reg.snapshot_date = rc.register_snapshot_date
             AND upper(trim(CAST(reg.company_number AS VARCHAR))) =
                 o.__ukcompany_company_number
            """
            accounts_category = "reg.accounts_category"
            register_date = "rc.register_snapshot_date"

        feature_projection = _account_feature_select_sql(
            latest_alias="l",
            prior_alias="p",
            reference_yyyymm="o.__ukcompany_accounts_reference_yyyymm",
            accounts_category=accounts_category,
        )
        query = f"""
            WITH observations AS (
                SELECT *, {cutoff_sql} AS __ukcompany_accounts_reference_yyyymm
                FROM __ukcompany_observations
            ),
            candidates AS (
                SELECT
                    o.__ukcompany_row_id,
                    CAST(w.period_end AS DATE) AS pe,
                    w."Equity" AS equity,
                    w."CurrentAssets" AS current_assets,
                    w.creditors_within_one_year AS creditors_within_one_year,
                    w."NetCurrentAssetsLiabilities" AS net_current_assets,
                    w."CashBankOnHand" AS cash,
                    w."AverageNumberEmployeesDuringPeriod" AS employees,
                    w.employees_unit_anomaly AS employees_unit_anomaly,
                    row_number() OVER (
                        PARTITION BY o.__ukcompany_row_id
                        ORDER BY CAST(w.period_end AS DATE) DESC
                    ) AS rn,
                    count(*) OVER (PARTITION BY o.__ukcompany_row_id) AS n_periods
                FROM observations o
                JOIN {wide} w
                  ON upper(trim(CAST(w.company AS VARCHAR))) =
                     o.__ukcompany_company_number
                 AND w.row_available_yyyymm <= o.__ukcompany_accounts_reference_yyyymm
                 AND CAST(w.period_end AS DATE) >= DATE {_sql_literal(PLAUSIBLE_PERIOD_START)}
                 AND CAST(w.period_end AS DATE) <= make_date(
                     CAST(floor(o.__ukcompany_accounts_reference_yyyymm / 100) AS INTEGER) + 1,
                     12,
                     31
                 )
            ),
            latest AS (SELECT * FROM candidates WHERE rn = 1),
            prior AS (
                SELECT __ukcompany_row_id, pe AS prior_pe, equity AS p_equity,
                       net_current_assets AS p_nca, cash AS p_cash
                FROM candidates WHERE rn = 2
            )
            {register_ctes}
            SELECT
                o.* EXCLUDE (
                    __ukcompany_row_id,
                    __ukcompany_company_number,
                    __ukcompany_reference_date,
                    __ukcompany_accounts_reference_yyyymm
                ),
                o.__ukcompany_accounts_reference_yyyymm AS accounts_reference_yyyymm,
                {register_date} AS accounts_register_snapshot_date_used,
                (l.__ukcompany_row_id IS NOT NULL) AS has_accounts,
                {feature_projection}
            FROM observations o
            LEFT JOIN latest l USING (__ukcompany_row_id)
            LEFT JOIN prior p USING (__ukcompany_row_id)
            {register_joins}
            ORDER BY o.__ukcompany_row_id
        """
        result = connection.sql(query).df()
    finally:
        connection.close()
    return restore_observation_index(result, original_index)


__all__ = ["assign_accounts_features"]
