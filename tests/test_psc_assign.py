"""As-of PSC snapshot assignment for observation rows."""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from ukcompany.psc.assign import assign_psc_features


def _snapshot(path, companies, counts, states):
    pl.DataFrame(
        {
            "company_number": companies,
            "psc_n_records": counts,
            "psc_information_state": states,
        }
    ).write_parquet(path)


def test_psc_assignment_selects_snapshot_before_company_join(tmp_path):
    january = tmp_path / "psc-2024-01.parquet"
    march = tmp_path / "psc-2024-03.parquet"
    _snapshot(
        january,
        ["00000001", "00000002"],
        [1, 2],
        ["identified", "identified"],
    )
    _snapshot(march, ["00000001"], [3], ["statement_only"])
    observations = pd.DataFrame(
        {
            "company": ["00000001", "00000001", "00000002", "00000001"],
            "event_date": ["2023-12-31", "2024-02-01", "2024-04-01", "2024-04-01"],
            "label": [0, 1, 0, 1],
        },
        index=pd.Index([8, 8, 9, 10], name="sample"),
    )

    result = assign_psc_features(
        observations,
        {"2024-01-01": january, "2024-03-01": march},
        company_number_column="company",
        date_column="event_date",
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )

    assert result.index.equals(observations.index)
    assert result["label"].tolist() == observations["label"].tolist()
    assert result["has_psc_snapshot"].tolist() == [False, True, True, True]
    assert result["has_psc"].tolist() == [False, True, False, True]
    assert pd.isna(result["psc_n_records"].iloc[0])
    assert result["psc_n_records"].iloc[1] == 1
    # Company 2 existed in January but is absent from the selected March snapshot. It must
    # not be incorrectly backfilled from the older snapshot.
    assert pd.isna(result["psc_n_records"].iloc[2])
    assert result["psc_n_records"].iloc[3] == 3
    assert [
        None if pd.isna(value) else str(value)[:10]
        for value in result["psc_snapshot_date_used"]
    ] == [None, "2024-01-01", "2024-03-01", "2024-03-01"]
    assert result["psc_snapshot_age_days"].iloc[1] == 31
    assert result["psc_snapshot_age_days"].iloc[3] == 31


def test_psc_assignment_requires_matching_snapshot_schemas(tmp_path):
    january = tmp_path / "psc-2024-01.parquet"
    march = tmp_path / "psc-2024-03.parquet"
    _snapshot(january, ["00000001"], [1], ["identified"])
    pl.DataFrame({"company_number": ["00000001"], "different": [1]}).write_parquet(march)
    observations = pd.DataFrame(
        {"company_number": ["00000001"], "date": ["2024-04-01"]}
    )

    with pytest.raises(ValueError, match="schemas differ"):
        assign_psc_features(
            observations,
            {"2024-01-01": january, "2024-03-01": march},
            memory_limit_gb=1,
            spill_dir=tmp_path / "spill",
        )
