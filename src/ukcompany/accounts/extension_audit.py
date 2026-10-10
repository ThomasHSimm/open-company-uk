"""Audit an append-only accounts WIDE extension against its baseline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import duckdb

KEY_COLUMNS = ("company", "period_end")
SUMMARY_COLUMNS = ("n_concepts_present", "n_source_filings", "row_available_yyyymm")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _schema(connection: duckdb.DuckDBPyConnection, path: str | Path) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
    ]


def compare_wide_extension(
    baseline_path: str | Path,
    candidate_path: str | Path,
    *,
    mode: str,
    output_path: str | Path | None = None,
    value_columns: Sequence[str] | None = None,
    memory_limit_gb: int = 12,
) -> dict:
    """Compare a WIDE extension and fail on first-reported value regressions."""
    if mode not in {"as_first_reported", "latest"}:
        raise ValueError(f"unsupported WIDE mode: {mode}")
    if memory_limit_gb <= 0:
        raise ValueError("memory_limit_gb must be positive")

    connection = duckdb.connect()
    try:
        connection.execute(f"SET memory_limit='{memory_limit_gb}GB'")
        connection.execute("SET preserve_insertion_order=false")
        baseline_columns = _schema(connection, baseline_path)
        candidate_columns = _schema(connection, candidate_path)
        if baseline_columns != candidate_columns:
            raise RuntimeError(
                "baseline and candidate WIDE schemas differ: "
                f"baseline={baseline_columns}, candidate={candidate_columns}"
            )
        missing_keys = sorted(set(KEY_COLUMNS) - set(baseline_columns))
        if missing_keys:
            raise RuntimeError(f"WIDE inputs are missing key columns: {missing_keys}")
        if value_columns is None:
            excluded = set(KEY_COLUMNS) | set(SUMMARY_COLUMNS)
            audited_columns = [column for column in baseline_columns if column not in excluded]
        else:
            audited_columns = list(value_columns)
            missing_values = sorted(set(audited_columns) - set(baseline_columns))
            if missing_values:
                raise RuntimeError(f"WIDE inputs are missing audited columns: {missing_values}")

        connection.execute(
            f"CREATE VIEW baseline AS SELECT * FROM read_parquet({_literal(baseline_path)})"
        )
        connection.execute(
            f"CREATE VIEW candidate AS SELECT * FROM read_parquet({_literal(candidate_path)})"
        )
        for view in ("baseline", "candidate"):
            rows, distinct_keys, null_keys = connection.execute(
                f"SELECT count(*), count(DISTINCT (company, period_end)), "
                f"count(*) FILTER (WHERE company IS NULL OR period_end IS NULL) FROM {view}"
            ).fetchone()
            if null_keys or rows != distinct_keys:
                raise RuntimeError(
                    f"{view} WIDE is not one non-null row per (company, period_end): "
                    f"rows={rows}, distinct_keys={distinct_keys}, null_keys={null_keys}"
                )
        metrics = [
            "count(*) FILTER (WHERE b.company IS NOT NULL) AS baseline_rows",
            "count(*) FILTER (WHERE n.company IS NOT NULL) AS candidate_rows",
            "count(*) FILTER (WHERE b.company IS NOT NULL AND n.company IS NOT NULL) "
            "AS matched_rows",
            "count(*) FILTER (WHERE b.company IS NULL) AS new_rows",
            "count(*) FILTER (WHERE n.company IS NULL) AS removed_rows",
        ]
        for index, column in enumerate(audited_columns):
            quoted = _quote(column)
            metrics.extend(
                [
                    f"count(*) FILTER (WHERE n.company IS NOT NULL AND n.{quoted} IS NOT NULL "
                    f"AND (b.company IS NULL OR b.{quoted} IS NULL)) AS filled_{index}",
                    f"count(*) FILTER (WHERE b.company IS NOT NULL AND n.company IS NOT NULL "
                    f"AND b.{quoted} IS NULL AND n.{quoted} IS NOT NULL) "
                    f"AS filled_existing_{index}",
                    f"count(*) FILTER (WHERE b.company IS NULL AND n.company IS NOT NULL "
                    f"AND n.{quoted} IS NOT NULL) AS filled_new_row_{index}",
                    f"count(*) FILTER (WHERE b.company IS NOT NULL AND b.{quoted} IS NOT NULL "
                    f"AND n.{quoted} IS DISTINCT FROM b.{quoted}) AS changed_{index}",
                    f"count(*) FILTER (WHERE b.company IS NOT NULL AND n.company IS NOT NULL "
                    f"AND b.{quoted} IS NOT NULL AND n.{quoted} IS NOT NULL "
                    f"AND n.{quoted} IS DISTINCT FROM b.{quoted}) AS changed_nonnull_{index}",
                    f"count(*) FILTER (WHERE b.company IS NOT NULL AND b.{quoted} IS NOT NULL "
                    f"AND (n.company IS NULL OR n.{quoted} IS NULL)) AS newly_null_{index}",
                ]
            )
        query = f"""
            SELECT {", ".join(metrics)}
            FROM baseline b
            FULL OUTER JOIN candidate n USING (company, period_end)
        """
        row = connection.execute(query).fetchone()
    finally:
        connection.close()

    report = {
        "mode": mode,
        "baseline_path": str(baseline_path),
        "candidate_path": str(candidate_path),
        "row_counts": {
            "baseline": row[0],
            "candidate": row[1],
            "matched": row[2],
            "new": row[3],
            "removed": row[4],
        },
        "by_column": {},
    }
    offset = 5
    for index, column in enumerate(audited_columns):
        start = offset + index * 6
        report["by_column"][column] = {
            "newly_filled": row[start],
            "newly_filled_existing_rows": row[start + 1],
            "filled_on_new_rows": row[start + 2],
            "previously_filled_changed": row[start + 3],
            "changed_nonnull": row[start + 4],
            "newly_null": row[start + 5],
        }
    report["totals"] = {
        "newly_filled": sum(item["newly_filled"] for item in report["by_column"].values()),
        "previously_filled_changed": sum(
            item["previously_filled_changed"] for item in report["by_column"].values()
        ),
        "changed_nonnull": sum(
            item["changed_nonnull"] for item in report["by_column"].values()
        ),
        "newly_null": sum(item["newly_null"] for item in report["by_column"].values()),
    }
    if output_path is not None:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if mode == "as_first_reported":
        changed = report["totals"]["previously_filled_changed"]
        removed = report["row_counts"]["removed"]
        if changed or removed:
            raise RuntimeError(
                "as_first_reported extension is not append-only: "
                f"{changed} previously filled cells changed and {removed} rows disappeared"
            )
    return report
