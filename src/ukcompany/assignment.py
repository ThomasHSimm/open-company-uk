"""Shared helpers for assigning point-in-time features to observation rows.

The public assignment functions live beside their source-specific feature builders.  This
module only owns the small pieces that must behave identically for accounts and PSC:
DataFrame validation, stable row identity, snapshot-source normalisation, and SQL quoting.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from ukcompany.duckdb_backend import PathValue, duckdb_path_sql, sql_literal


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def prepare_observations(
    observations: Any,
    *,
    company_number_column: str,
    date_column: str,
    appended_columns: Sequence[str],
):
    """Validate and copy a pandas DataFrame, adding private query columns.

    A generated row number is deliberately used instead of the DataFrame index: duplicate
    indices are valid, and duplicate company/date rows must remain distinct.  The caller
    restores the original index after ordering the SQL result by this row number.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "row-level feature assignment requires pandas; install "
            "`open-company-uk[analysis]`"
        ) from exc

    if not isinstance(observations, pd.DataFrame):
        raise TypeError("observations must be a pandas DataFrame")
    missing = [
        column
        for column in (company_number_column, date_column)
        if column not in observations.columns
    ]
    if missing:
        raise ValueError(f"observations are missing required column(s): {missing}")
    private_columns = [column for column in observations.columns if column.startswith("__ukcompany_")]
    if private_columns:
        raise ValueError(
            "observation columns use the reserved '__ukcompany_' prefix: "
            f"{private_columns}"
        )
    collisions = sorted(set(observations.columns) & set(appended_columns))
    if collisions:
        raise ValueError(
            "observations already contain feature output column(s): "
            f"{collisions}"
        )

    prepared = observations.copy()
    companies = prepared[company_number_column].astype("string").str.strip().str.upper()
    invalid_companies = companies.isna() | companies.eq("")
    if invalid_companies.any():
        positions = invalid_companies.to_numpy().nonzero()[0][:10].tolist()
        raise ValueError(
            "company-number values must be non-empty; invalid observation position(s): "
            f"{positions}"
        )
    try:
        parsed_dates = pd.to_datetime(prepared[date_column], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{date_column!r} contains an invalid date: {exc}") from exc
    if parsed_dates.isna().any():
        positions = parsed_dates.isna().to_numpy().nonzero()[0][:10].tolist()
        raise ValueError(
            f"{date_column!r} contains missing dates at observation position(s): {positions}"
        )

    prepared["__ukcompany_row_id"] = range(len(prepared))
    prepared["__ukcompany_company_number"] = companies
    prepared["__ukcompany_reference_date"] = parsed_dates.dt.date
    return prepared, observations.index.copy()


def restore_observation_index(frame: Any, original_index: Any):
    frame.index = original_index
    frame.index.name = original_index.name
    return frame


def normalise_snapshot_sources(
    sources: Mapping[str | date | datetime, PathValue],
    *,
    label: str,
) -> tuple[tuple[date, str], ...]:
    """Return date/path pairs sorted by date, rejecting ambiguous input."""
    if not isinstance(sources, Mapping) or not sources:
        raise ValueError(f"{label} must be a non-empty mapping of snapshot date to path")
    normalised: list[tuple[date, str]] = []
    seen: set[date] = set()
    for raw_date, raw_path in sources.items():
        if isinstance(raw_date, datetime):
            snapshot_date = raw_date.date()
        elif isinstance(raw_date, date):
            snapshot_date = raw_date
        else:
            try:
                snapshot_date = date.fromisoformat(str(raw_date))
            except ValueError as exc:
                raise ValueError(f"invalid {label} date {raw_date!r}; expected YYYY-MM-DD") from exc
        if snapshot_date in seen:
            raise ValueError(f"duplicate {label} date: {snapshot_date.isoformat()}")
        path = os.fspath(raw_path)
        if not path:
            raise ValueError(f"empty path for {label} date {snapshot_date.isoformat()}")
        seen.add(snapshot_date)
        normalised.append((snapshot_date, path))
    return tuple(sorted(normalised))


def snapshot_catalog_sql(sources: Sequence[tuple[date, str]]) -> str:
    values = ", ".join(
        f"(DATE {sql_literal(snapshot_date.isoformat())})" for snapshot_date, _ in sources
    )
    return f"(VALUES {values}) AS snapshot_catalog(snapshot_date)"


def snapshot_union_sql(
    sources: Sequence[tuple[date, str]],
    *,
    columns: Sequence[str],
) -> str:
    selected = ", ".join(quote_identifier(column) for column in columns)
    return " UNION ALL ".join(
        "SELECT DATE "
        f"{sql_literal(snapshot_date.isoformat())} AS snapshot_date, {selected} "
        f"FROM read_parquet({duckdb_path_sql(path)})"
        for snapshot_date, path in sources
    )


def table_columns(connection: Any, path: PathValue) -> tuple[str, ...]:
    return tuple(
        row[0]
        for row in connection.execute(
            f"DESCRIBE SELECT * FROM read_parquet({duckdb_path_sql(path)})"
        ).fetchall()
    )


def require_snapshot_columns(
    connection: Any,
    sources: Sequence[tuple[date, str]],
    *,
    required: Sequence[str],
    label: str,
) -> None:
    for snapshot_date, path in sources:
        available = set(table_columns(connection, path))
        missing = sorted(set(required) - available)
        if missing:
            raise ValueError(
                f"{label} table for {snapshot_date.isoformat()} is missing columns "
                f"{missing}: {path}"
            )


def require_matching_snapshot_schemas(
    connection: Any,
    sources: Sequence[tuple[date, str]],
    *,
    label: str,
) -> tuple[str, ...]:
    expected = table_columns(connection, sources[0][1])
    if "company_number" not in expected:
        raise ValueError(f"{label} table is missing 'company_number': {sources[0][1]}")
    for snapshot_date, path in sources[1:]:
        actual = table_columns(connection, path)
        if actual != expected:
            raise ValueError(
                f"{label} schemas differ at {snapshot_date.isoformat()}: "
                f"expected={list(expected)}, actual={list(actual)}"
            )
    return expected
