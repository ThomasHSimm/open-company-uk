"""Synthetic tests for accounts-to-register reconciliation."""

import polars as pl

from ukcompany.accounts.reconciliation import reconcile_accounts_register


def test_reconciliation_buckets_and_exact_rate(tmp_path):
    features = tmp_path / "features.parquet"
    pl.DataFrame(
        {
            "company_number": ["A", "B", "D", "OUTSIDE"],
            "latest_period_end": ["2023-12-31", "2022-12-31", "2024-03-31", "2024-01-31"],
        }
    ).with_columns(pl.col("latest_period_end").str.to_date()).write_parquet(features)
    register = tmp_path / "BasicCompanyData.csv"
    register.write_text(
        "CompanyNumber,Accounts.LastMadeUpDate\n"
        "A,31/12/2023\n"
        "B,31/12/2023\n"
        "C,\n"
        "D,\n"
        "E,31/03/2024\n",
        encoding="utf-8",
    )

    report = reconcile_accounts_register(
        features,
        str(register),
        t_yyyymm=202409,
        register_snapshot_date="2026-10-01",
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )

    assert report["register_rows"] == 5
    assert report["feature_companies_outside_register"] == 1
    assert report["buckets"] == {
        "exact": 1,
        "both_absent": 1,
        "no_accounts_feature": 1,
        "register_newer": 1,
        "accounts_newer": 0,
        "register_date_absent": 1,
    }
    assert report["exact_match_rate_both_present"] == 0.5
