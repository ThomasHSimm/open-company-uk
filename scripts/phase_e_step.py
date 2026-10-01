"""Phase E LONG comparison, one step per process invocation.

Each step gets a fresh DuckDB connection in its own process, guaranteeing full OS-level
memory reclaim before the next step starts — the combined single-script version OOM-killed
after 1h38m, most likely from DuckDB state accumulating across several large sequential
queries in one long-lived connection/process rather than any single query being too large
on its own.

Usage:
    python scripts/phase_e_step.py <step>
where <step> is one of: totals, new_coverage, value_changed, value_changed_examples, v1_only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

V1_LONG = "data/accounts/long/accounts-long-*.parquet"
V2_LONG = "data/accounts/v2/long/accounts-long-*.parquet"
RESULTS_DIR = Path("data/accounts/parser-compare-results/phase_e_steps")
JOIN_KEY = "company, source_archive, source_member, concept, period_end, dimension, member"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET memory_limit='22GB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"CREATE VIEW v1 AS SELECT * FROM read_parquet('{V1_LONG}')")
    con.execute(f"CREATE VIEW v2 AS SELECT * FROM read_parquet('{V2_LONG}')")
    return con


def step_totals() -> dict:
    con = connect()
    v1_totals = con.execute(
        "SELECT source_year, count(*) AS observations, "
        "count(DISTINCT source_archive || '/' || source_member) AS filings_with_facts "
        "FROM v1 GROUP BY 1 ORDER BY 1"
    ).fetchall()
    v2_totals = con.execute(
        "SELECT source_year, count(*) AS observations, "
        "count(DISTINCT source_archive || '/' || source_member) AS filings_with_facts "
        "FROM v2 GROUP BY 1 ORDER BY 1"
    ).fetchall()
    return {
        "v1": {str(row[0]): {"observations": row[1], "filings_with_facts": row[2]} for row in v1_totals},
        "v2": {str(row[0]): {"observations": row[1], "filings_with_facts": row[2]} for row in v2_totals},
    }


def step_new_coverage() -> dict:
    con = connect()
    # Materialise the (small — at most a few hundred thousand rows) set of files that exist
    # in v2 but not v1 FIRST, as its own table, before ever touching the full-size v2 fact
    # table again — joining the two full DISTINCT-file-list subqueries against the entire
    # multi-hundred-million-row v2 table in one statement is what pushed DuckDB's planner
    # into a poor join order and exhausted the 18GB limit on the first attempt.
    con.execute(
        """
        CREATE TABLE new_files AS
        SELECT v2_files.source_archive, v2_files.source_member, v2_files.source_year,
               CASE WHEN v2_files.source_member ILIKE '%.xml' THEN 'xml'
                    ELSE 'other_new_coverage' END AS cause
        FROM (SELECT DISTINCT source_archive, source_member, source_year FROM v2) v2_files
        ANTI JOIN (SELECT DISTINCT source_archive, source_member FROM v1) v1_files
            ON v2_files.source_archive = v1_files.source_archive
            AND v2_files.source_member = v1_files.source_member
        """
    )
    n_new_files = con.execute("SELECT count(*) FROM new_files").fetchone()[0]
    rows = con.execute(
        """
        SELECT new_files.source_year, new_files.cause,
               count(DISTINCT new_files.source_archive || '/' || new_files.source_member) AS n_filings,
               count(*) AS n_observations
        FROM new_files
        JOIN v2 ON v2.source_archive = new_files.source_archive
            AND v2.source_member = new_files.source_member
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall()
    return {
        "n_new_files_total": n_new_files,
        "new_filing_coverage_by_year_and_cause": [
            {"year": row[0], "cause": row[1], "n_filings": row[2], "n_observations": row[3]}
            for row in rows
        ]
    }


def step_value_changed() -> dict:
    con = connect()
    con.execute("CREATE VIEW v1_sel AS SELECT * FROM v1 WHERE status = 'selected'")
    con.execute("CREATE VIEW v2_sel AS SELECT * FROM v2 WHERE status = 'selected'")
    # Sanity-check row counts on each side first — if this alone is enormous, the join
    # explosion theory (rather than cross-query memory accumulation) would be confirmed.
    counts = con.execute(
        "SELECT (SELECT count(*) FROM v1_sel), (SELECT count(*) FROM v2_sel)"
    ).fetchone()
    changed = con.execute(
        f"""
        SELECT v1_sel.concept, v1_sel.source_year, count(*) AS n_changed
        FROM v1_sel
        JOIN v2_sel USING ({JOIN_KEY})
        WHERE v1_sel.numeric_value IS DISTINCT FROM v2_sel.numeric_value
        GROUP BY 1, 2
        ORDER BY 3 DESC
        """
    ).fetchall()
    return {
        "v1_selected_rows": counts[0],
        "v2_selected_rows": counts[1],
        "value_changed_on_shared_keys_by_concept_year": [
            {"concept": row[0], "year": row[1], "n_changed": row[2]} for row in changed
        ],
        "value_changed_total": sum(row[2] for row in changed),
    }


def obfuscate_member(member: str) -> str:
    parts = member.split("_")
    if len(parts) >= 4:
        parts[2] = "X" * len(parts[2])
    return "_".join(parts)


def step_value_changed_examples() -> dict:
    con = connect()
    con.execute("CREATE VIEW v1_sel AS SELECT * FROM v1 WHERE status = 'selected'")
    con.execute("CREATE VIEW v2_sel AS SELECT * FROM v2 WHERE status = 'selected'")
    examples = con.execute(
        f"""
        SELECT v1_sel.concept, v1_sel.source_member, v1_sel.raw_value,
               v1_sel.numeric_value AS v1_value, v2_sel.numeric_value AS v2_value
        FROM v1_sel
        JOIN v2_sel USING ({JOIN_KEY})
        WHERE v1_sel.numeric_value IS DISTINCT FROM v2_sel.numeric_value
        LIMIT 15
        """
    ).fetchall()
    return {
        "value_changed_examples": [
            {
                "concept": row[0],
                "source_member": obfuscate_member(row[1]),
                "raw_value": row[2],
                "v1_numeric_value": row[3],
                "v2_numeric_value": row[4],
            }
            for row in examples
        ]
    }


_HASH_EXPR = (
    "hash(concat_ws('|', company, source_archive, source_member, concept, period_end, "
    "coalesce(dimension, ''), coalesce(member, '')))"
)


def step_v1_only() -> dict:
    con = connect()
    # A 7-column ANTI JOIN across ~2 billion rows on each side exhausted 22GB even with
    # preserve_insertion_order=false — DuckDB's hash-join build side for wide multi-column
    # VARCHAR keys at this row count doesn't fit. Materialising a single 8-byte hash column
    # first and joining on that alone (still exact for this purpose: a hash collision would
    # only ever make this check UNDER-report false positives, not report a false one, and a
    # 64-bit hash collision at ~2B rows is negligible) uses a small fraction of the memory.
    con.execute(f"CREATE TABLE v1_keys AS SELECT DISTINCT {_HASH_EXPR} AS k FROM v1 WHERE status = 'selected'")
    con.execute(f"CREATE TABLE v2_keys AS SELECT DISTINCT {_HASH_EXPR} AS k FROM v2 WHERE status = 'selected'")
    result = con.execute("SELECT count(*) FROM v1_keys ANTI JOIN v2_keys USING (k)").fetchone()
    return {"v1_only_selected_keys_total": result[0]}


STEPS = {
    "totals": step_totals,
    "new_coverage": step_new_coverage,
    "value_changed": step_value_changed,
    "value_changed_examples": step_value_changed_examples,
    "v1_only": step_v1_only,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in STEPS:
        print(f"usage: python {sys.argv[0]} <{'|'.join(STEPS)}>")
        return 1
    step_name = sys.argv[1]
    result = STEPS[step_name]()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{step_name}.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"written: {out_path}")
    print(json.dumps(result, indent=2, default=str)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
