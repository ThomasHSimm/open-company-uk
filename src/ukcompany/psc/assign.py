"""Assign PSC snapshot features to observation rows with an as-of join."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from ukcompany.assignment import (
    normalise_snapshot_sources,
    prepare_observations,
    quote_identifier,
    require_matching_snapshot_schemas,
    restore_observation_index,
    snapshot_catalog_sql,
    snapshot_union_sql,
)
from ukcompany.duckdb_backend import PathValue

from .loader import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect


def assign_psc_features(
    observations: Any,
    feature_snapshots: Mapping[str | date | datetime, PathValue],
    *,
    company_number_column: str = "company_number",
    date_column: str = "date",
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
    duckdb_backend: str | None = None,
    fsspec_options: Mapping[str, Mapping[str, Any]] | None = None,
):
    """Return ``observations`` with features from the latest prior PSC snapshot.

    Snapshot selection happens independently of company presence.  A company absent from the
    selected snapshot therefore remains absent; the function never reaches farther back to find
    an older company record.  Rows before the first supplied snapshot receive null features.
    """
    sources = normalise_snapshot_sources(feature_snapshots, label="PSC feature snapshots")
    input_paths = tuple(path for _, path in sources)
    connection = _connect(
        memory_limit_gb,
        spill_dir,
        duckdb_backend=duckdb_backend,
        input_paths=input_paths,
        fsspec_options=fsspec_options,
    )
    try:
        schema = require_matching_snapshot_schemas(
            connection, sources, label="PSC feature snapshot"
        )
        if "snapshot_date" in schema:
            raise ValueError(
                "PSC feature tables must not contain a 'snapshot_date' column; "
                "snapshot dates come from the feature_snapshots mapping"
            )
        feature_columns = tuple(column for column in schema if column != "company_number")
        output_columns = (
            "psc_snapshot_date_used",
            "psc_snapshot_age_days",
            "has_psc_snapshot",
            "has_psc",
            *feature_columns,
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

        connection.register("__ukcompany_observations", prepared)
        catalog = snapshot_catalog_sql(sources)
        snapshot_features = snapshot_union_sql(sources, columns=schema)
        projected_features = ",\n                ".join(
            f"f.{quote_identifier(column)} AS {quote_identifier(column)}"
            for column in feature_columns
        )
        query = f"""
            WITH observations AS (
                SELECT * FROM __ukcompany_observations
            ),
            snapshot_catalog AS (
                SELECT * FROM {catalog}
            ),
            snapshot_choice AS (
                SELECT o.__ukcompany_row_id,
                       max(c.snapshot_date) AS psc_snapshot_date
                FROM observations o
                LEFT JOIN snapshot_catalog c
                  ON c.snapshot_date <= o.__ukcompany_reference_date
                GROUP BY o.__ukcompany_row_id
            ),
            snapshot_features AS ({snapshot_features})
            SELECT
                o.* EXCLUDE (
                    __ukcompany_row_id,
                    __ukcompany_company_number,
                    __ukcompany_reference_date
                ),
                sc.psc_snapshot_date AS psc_snapshot_date_used,
                CASE WHEN sc.psc_snapshot_date IS NULL THEN NULL
                     ELSE date_diff('day', sc.psc_snapshot_date, o.__ukcompany_reference_date)
                     END AS psc_snapshot_age_days,
                (sc.psc_snapshot_date IS NOT NULL) AS has_psc_snapshot,
                (f.company_number IS NOT NULL) AS has_psc,
                {projected_features}
            FROM observations o
            LEFT JOIN snapshot_choice sc USING (__ukcompany_row_id)
            LEFT JOIN snapshot_features f
              ON f.snapshot_date = sc.psc_snapshot_date
             AND upper(trim(CAST(f.company_number AS VARCHAR))) =
                 o.__ukcompany_company_number
            ORDER BY o.__ukcompany_row_id
        """
        result = connection.sql(query).df()
    finally:
        connection.close()
    return restore_observation_index(result, original_index)
__all__ = ["assign_psc_features"]
