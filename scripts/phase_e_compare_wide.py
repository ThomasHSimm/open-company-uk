"""Phase E: v1 -> v2 WIDE change, cell by cell, per column and year, for both pivot modes.

Categories per (row, column): newly filled (v1 null, v2 not null), value changed (both
not null, different), newly null (v1 not null, v2 null). Unchanged cells are not reported.
Example keys use obfuscated company numbers (never the real number) per the brief.

Usage:
    python scripts/phase_e_compare_wide.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

WIDE_COLUMNS = (
    "Equity",
    "NetCurrentAssetsLiabilities",
    "CurrentAssets",
    "Creditors",
    "CashBankOnHand",
    "Debtors",
    "PropertyPlantEquipment",
    "TotalAssetsLessCurrentLiabilities",
    "AverageNumberEmployeesDuringPeriod",
    "equity_share_capital",
    "equity_retained_earnings",
    "creditors_within_one_year",
    "creditors_after_one_year",
)

RESULTS_PATH = Path("data/accounts/parser-compare-results/phase_e_wide_diff.json")


def obfuscate(company: str) -> str:
    return "X" * len(company)


def compare_mode(con: duckdb.DuckDBPyConnection, mode: str) -> dict:
    v1_path = f"data/accounts/accounts-wide-{mode}.parquet"
    v2_path = f"data/accounts/v2/accounts-wide-{mode}.parquet"
    con.execute(f"CREATE OR REPLACE VIEW v1w AS SELECT * FROM read_parquet('{v1_path}')")
    con.execute(f"CREATE OR REPLACE VIEW v2w AS SELECT * FROM read_parquet('{v2_path}')")

    result: dict = {"row_counts": {}, "by_column": {}, "examples": {}}
    counts = con.execute("SELECT (SELECT count(*) FROM v1w), (SELECT count(*) FROM v2w)").fetchone()
    result["row_counts"] = {"v1": counts[0], "v2": counts[1]}

    for column in WIDE_COLUMNS:
        print(f"  [{mode}] column {column}...", flush=True)
        rows = con.execute(
            f"""
            SELECT
                substr(coalesce(v1w.period_end, v2w.period_end), 1, 4) AS year,
                sum(CASE WHEN v1w."{column}" IS NULL AND v2w."{column}" IS NOT NULL THEN 1 ELSE 0 END) AS newly_filled,
                sum(CASE WHEN v1w."{column}" IS NOT NULL AND v2w."{column}" IS NOT NULL
                         AND v1w."{column}" IS DISTINCT FROM v2w."{column}" THEN 1 ELSE 0 END) AS changed,
                sum(CASE WHEN v1w."{column}" IS NOT NULL AND v2w."{column}" IS NULL THEN 1 ELSE 0 END) AS newly_null
            FROM v1w
            FULL OUTER JOIN v2w USING (company, period_end)
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchall()
        result["by_column"][column] = [
            {"year": row[0], "newly_filled": row[1], "changed": row[2], "newly_null": row[3]}
            for row in rows
            if row[0] is not None
        ]

        examples = con.execute(
            f"""
            SELECT coalesce(v1w.company, v2w.company) AS company,
                   coalesce(v1w.period_end, v2w.period_end) AS period_end,
                   v1w."{column}" AS v1_value, v2w."{column}" AS v2_value
            FROM v1w
            FULL OUTER JOIN v2w USING (company, period_end)
            WHERE (v1w."{column}" IS NULL) != (v2w."{column}" IS NULL)
               OR v1w."{column}" IS DISTINCT FROM v2w."{column}"
            LIMIT 5
            """
        ).fetchall()
        result["examples"][column] = [
            {
                "company": obfuscate(row[0]),
                "period_end": row[1],
                "v1_value": row[2],
                "v2_value": row[3],
            }
            for row in examples
        ]

    return result


def main() -> int:
    con = duckdb.connect()
    con.execute("SET memory_limit='20GB'")
    result = {}
    for mode in ("latest", "as_first_reported"):
        print(f"=== mode: {mode} ===", flush=True)
        result[mode] = compare_mode(con, mode)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {RESULTS_PATH}")
    for mode, data in result.items():
        print(f"--- {mode} ---")
        print("row_counts:", data["row_counts"])
        for column, years in data["by_column"].items():
            total_filled = sum(y["newly_filled"] for y in years)
            total_changed = sum(y["changed"] for y in years)
            total_null = sum(y["newly_null"] for y in years)
            print(f"  {column}: filled={total_filled} changed={total_changed} newly_null={total_null}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
