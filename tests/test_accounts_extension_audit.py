"""Synthetic tests for the append-only accounts WIDE extension audit."""

import polars as pl
import pytest

from ukcompany.accounts.extension_audit import compare_wide_extension

SCHEMA = {
    "company": pl.String,
    "period_end": pl.String,
    "Equity": pl.Float64,
    "CurrentAssets": pl.Float64,
    "n_concepts_present": pl.Int64,
    "n_source_filings": pl.Int64,
    "row_available_yyyymm": pl.Int64,
}


def _write(path, rows):
    pl.DataFrame(rows, schema=SCHEMA, orient="row").write_parquet(path)


def test_first_reported_allows_new_rows_and_empty_cell_fills(tmp_path):
    baseline = tmp_path / "baseline.parquet"
    candidate = tmp_path / "candidate.parquet"
    _write(baseline, [("A", "2023-12-31", 1.0, None, 1, 1, 202401)])
    _write(
        candidate,
        [
            ("A", "2023-12-31", 1.0, 5.0, 2, 2, 202409),
            ("B", "2024-03-31", 4.0, 7.0, 2, 1, 202409),
        ],
    )

    report = compare_wide_extension(
        baseline, candidate, mode="as_first_reported", output_path=tmp_path / "report.json"
    )

    assert report["row_counts"] == {
        "baseline": 1,
        "candidate": 2,
        "matched": 1,
        "new": 1,
        "removed": 0,
    }
    assert report["by_column"]["Equity"]["newly_filled"] == 1
    assert report["by_column"]["Equity"]["newly_filled_existing_rows"] == 0
    assert report["by_column"]["Equity"]["filled_on_new_rows"] == 1
    assert report["by_column"]["CurrentAssets"]["newly_filled"] == 2
    assert report["by_column"]["CurrentAssets"]["newly_filled_existing_rows"] == 1
    assert report["by_column"]["CurrentAssets"]["filled_on_new_rows"] == 1
    assert report["totals"]["previously_filled_changed"] == 0


def test_first_reported_rejects_changed_previously_filled_cell(tmp_path):
    baseline = tmp_path / "baseline.parquet"
    candidate = tmp_path / "candidate.parquet"
    _write(baseline, [("A", "2023-12-31", 1.0, None, 1, 1, 202401)])
    _write(candidate, [("A", "2023-12-31", 2.0, None, 1, 1, 202401)])

    with pytest.raises(RuntimeError, match="1 previously filled cells changed"):
        compare_wide_extension(baseline, candidate, mode="as_first_reported")


def test_latest_reports_expected_restatement_without_failing(tmp_path):
    baseline = tmp_path / "baseline.parquet"
    candidate = tmp_path / "candidate.parquet"
    _write(baseline, [("A", "2023-12-31", 1.0, None, 1, 1, 202401)])
    _write(candidate, [("A", "2023-12-31", 2.0, None, 1, 2, 202409)])

    report = compare_wide_extension(baseline, candidate, mode="latest")

    assert report["totals"]["previously_filled_changed"] == 1
    assert report["totals"]["changed_nonnull"] == 1


def test_audit_rejects_duplicate_keys(tmp_path):
    baseline = tmp_path / "baseline.parquet"
    candidate = tmp_path / "candidate.parquet"
    _write(
        baseline,
        [
            ("A", "2023-12-31", 1.0, None, 1, 1, 202401),
            ("A", "2023-12-31", 1.0, None, 1, 1, 202401),
        ],
    )
    _write(candidate, [("A", "2023-12-31", 1.0, None, 1, 1, 202401)])

    with pytest.raises(RuntimeError, match="not one non-null row"):
        compare_wide_extension(baseline, candidate, mode="as_first_reported")
