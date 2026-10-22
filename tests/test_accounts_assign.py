"""Row-level point-in-time assignment for accounts features."""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from ukcompany.accounts.assign import assign_accounts_features


def _wide(tmp_path):
    path = tmp_path / "wide.parquet"
    pl.DataFrame(
        {
            "company": ["00000001", "00000001"],
            "period_end": ["2022-12-31", "2023-12-31"],
            "row_available_yyyymm": [202303, 202406],
            "Equity": [100.0, 250.0],
            "CurrentAssets": [200.0, 500.0],
            "creditors_within_one_year": [100.0, 250.0],
            "NetCurrentAssetsLiabilities": [100.0, 250.0],
            "CashBankOnHand": [50.0, 80.0],
            "AverageNumberEmployeesDuringPeriod": [5.0, 12.0],
            "employees_unit_anomaly": [False, False],
        }
    ).write_parquet(path)
    return path


def _register_snapshot(path, category):
    pl.DataFrame(
        {"company_number": ["00000001"], "accounts_category": [category]}
    ).write_parquet(path)


def test_each_observation_gets_its_own_accounts_cutoff(tmp_path):
    observations = pd.DataFrame(
        {
            "company": ["00000001", " 00000001 ", "99999999"],
            "event_date": ["2024-01-15", "2024-07-15", "2024-07-15"],
            "outcome": [0, 1, 0],
        },
        index=pd.Index([11, 11, 30], name="case_index"),
    )

    result = assign_accounts_features(
        observations,
        _wide(tmp_path),
        company_number_column="company",
        date_column="event_date",
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )

    assert result.index.equals(observations.index)
    assert result["outcome"].tolist() == [0, 1, 0]
    assert result["accounts_reference_yyyymm"].tolist() == [202312, 202406, 202406]
    assert result["has_accounts"].tolist() == [True, True, False]
    assert result["equity"].iloc[0] == 100.0
    assert result["equity"].iloc[1] == 250.0
    assert result["n_periods_available"].iloc[0] == 1
    assert result["n_periods_available"].iloc[1] == 2
    assert result["months_since_latest_period_end"].iloc[0] == 12
    assert result["months_since_latest_period_end"].iloc[1] == 6
    assert pd.isna(result["equity"].iloc[2])
    assert result["company"].tolist() == observations["company"].tolist()


def test_same_month_policy_is_explicit(tmp_path):
    observations = pd.DataFrame(
        {"company_number": ["00000001"], "date": ["2024-06-01"]}
    )

    conservative = assign_accounts_features(
        observations,
        _wide(tmp_path),
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill-a",
    )
    same_month = assign_accounts_features(
        observations,
        _wide(tmp_path),
        availability_policy="same_month",
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill-b",
    )

    assert conservative["accounts_reference_yyyymm"].item() == 202405
    assert conservative["equity"].item() == 100.0
    assert same_month["accounts_reference_yyyymm"].item() == 202406
    assert same_month["equity"].item() == 250.0


def test_register_category_uses_latest_prior_register_snapshot(tmp_path):
    january = tmp_path / "register-2024-01.parquet"
    july = tmp_path / "register-2024-07.parquet"
    _register_snapshot(january, "SMALL")
    _register_snapshot(july, "MICRO ENTITY")
    observations = pd.DataFrame(
        {
            "company_number": ["00000001", "00000001"],
            "date": ["2024-01-15", "2024-07-15"],
        }
    )

    result = assign_accounts_features(
        observations,
        _wide(tmp_path),
        register_feature_snapshots={"2024-01-01": january, "2024-07-01": july},
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )

    assert result["accounts_category"].tolist() == ["SMALL", "MICRO ENTITY"]
    assert [str(value)[:10] for value in result["accounts_register_snapshot_date_used"]] == [
        "2024-01-01",
        "2024-07-01",
    ]


def test_assignment_rejects_output_column_collisions(tmp_path):
    observations = pd.DataFrame(
        {"company_number": ["00000001"], "date": ["2024-01-01"], "equity": [999]}
    )
    with pytest.raises(ValueError, match="already contain feature output"):
        assign_accounts_features(observations, _wide(tmp_path))
