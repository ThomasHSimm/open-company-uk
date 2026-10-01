"""Automated staging guard for kaggle/ and kaggle-long/ — the last check before upload.

Scans every Parquet file in both folders and fails if it finds any concept on the numeric
denylist, or any non-numeric concept outside the allowlist (see
docs/accounts-public-long-concepts.md, src/ukcompany/accounts/public_long.py). This exists
to catch a personal-data leak through a stale or wrong file — it checks the ACTUAL published
bytes, not just the code path that is supposed to have filtered them, and it also
independently re-derives a person-related-name pattern rather than only re-checking the same
lists the builder used (so a mistake in the lists, not just in applying them, has a second
chance to be caught).

Usage: python scripts/kaggle_staging_guard.py [kaggle/ dir] [kaggle-long/ dir]
Exit code 0 = passed every file; 1 = at least one violation found (see printed report).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ukcompany.accounts.public_long import (  # noqa: E402
    NON_NUMERIC_ALLOWLIST,
    NUMERIC_DENYLIST,
)

# Independent of NUMERIC_DENYLIST — re-derived from the same brief, not copy-checked against
# the list the builder used, so a mistake in the list itself still has a chance of being caught.
PERSON_NAME_PATTERN = re.compile(
    r"director|officer|keymanagement|related.?party|remuneration|trustee", re.I
)
# Column names that are always safe in a WIDE file, never a concept name.
WIDE_HOUSEKEEPING_COLUMNS = frozenset(
    {"company", "period_end", "employees_unit_anomaly", "n_concepts_present",
     "n_source_filings", "row_available_yyyymm"}
)
FORBIDDEN_LONG_CONCEPTS = frozenset({"EntityCurrentLegalOrRegisteredName"})


def require_duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("the staging guard requires the duckdb package") from exc
    return duckdb


def check_long_shaped_file(connection, path: Path) -> list[str]:
    violations = []
    rows = connection.sql(
        f"SELECT DISTINCT fact_kind, concept FROM read_parquet('{path}')"
    ).fetchall()
    for fact_kind, concept in rows:
        if concept in FORBIDDEN_LONG_CONCEPTS:
            violations.append(f"{path}: forbidden concept published: {concept!r}")
        elif fact_kind == "numeric" and concept in NUMERIC_DENYLIST:
            violations.append(f"{path}: denylisted numeric concept published: {concept!r}")
        elif fact_kind == "non-numeric" and concept not in NON_NUMERIC_ALLOWLIST:
            violations.append(
                f"{path}: non-numeric concept not in allowlist published: {concept!r}"
            )
    return violations


def check_wide_shaped_file(connection, path: Path) -> list[str]:
    violations = []
    columns = [
        row[0]
        for row in connection.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
    ]
    for column in columns:
        if column in WIDE_HOUSEKEEPING_COLUMNS:
            continue
        if column in NUMERIC_DENYLIST:
            violations.append(f"{path}: denylisted concept published as WIDE column: {column!r}")
        if PERSON_NAME_PATTERN.search(column):
            violations.append(
                f"{path}: WIDE column name matches person-related pattern: {column!r}"
            )
    return violations


def scan_directory(connection, directory: Path) -> list[str]:
    violations = []
    paths = sorted(directory.glob("*.parquet"))
    if not paths:
        violations.append(f"{directory}: no Parquet files found")
        return violations
    for path in paths:
        columns = {
            row[0]
            for row in connection.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
        }
        if {"concept", "fact_kind"} <= columns:
            violations.extend(check_long_shaped_file(connection, path))
        else:
            violations.extend(check_wide_shaped_file(connection, path))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="*", default=["kaggle", "kaggle-long"], type=Path)
    args = parser.parse_args()

    duckdb = require_duckdb()
    connection = duckdb.connect(":memory:")
    all_violations = []
    for directory in args.directories:
        all_violations.extend(scan_directory(connection, directory))
    connection.close()

    if all_violations:
        print(f"STAGING GUARD FAILED — {len(all_violations)} violation(s):")
        for violation in all_violations:
            print(f"  - {violation}")
        return 1
    print(f"Staging guard passed: {', '.join(str(d) for d in args.directories)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
