"""Synthetic tests for the point-in-time per-company join."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from ukcompany.accounts.features import build_accounts_features
from ukcompany.cli import main
from ukcompany.join import (
    FORBIDDEN_GOVERNED_COLUMNS,
    JoinInputs,
    build_join,
    resolve_join_inputs,
)


def _write_parquet(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(data).write_parquet(path)
    return path


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _inputs(tmp_path: Path, *, register_numbers=("A", "B", "C")) -> JoinInputs:
    register = _write_parquet(
        tmp_path / "register.parquet",
        {
            "company_number": list(register_numbers),
            "company_type": ["Private" for _ in register_numbers],
            "accounts_category": ["SMALL" for _ in register_numbers],
            "n_companies_same_postcode": [2 for _ in register_numbers],
        },
    )
    psc = _write_parquet(
        tmp_path / "psc.parquet",
        {
            "company_number": ["A", "OUTSIDE"],
            "psc_n_records": [None, 1],
            "psc_information_state": [None, "identified"],
        },
    )
    accounts = _write_parquet(
        tmp_path / "accounts.parquet",
        {
            "company_number": ["A", "B", "OUTSIDE"],
            "latest_period_end": [None, None, None],
            "equity": [None, 10.0, 20.0],
        },
    )
    return JoinInputs(
        register_path=register,
        register_report=_write_json(tmp_path / "register-report.json", {"synthetic": True}),
        register_snapshot_date="2026-10-01",
        psc_path=psc,
        psc_report=_write_json(tmp_path / "psc-report.json", {"synthetic": True}),
        psc_snapshot_date="2026-09-25",
        accounts_path=accounts,
        accounts_report=_write_json(tmp_path / "accounts-report.json", {"synthetic": True}),
        accounts_reference_month=202609,
    )


def test_join_schema_flags_and_reconciled_coverage(tmp_path: Path) -> None:
    manifest = build_join(
        _inputs(tmp_path),
        tmp_path / "output",
        202609,
        "governed",
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )
    output = pl.read_parquet(tmp_path / "output" / "joined_company_features.parquet")

    assert output.height == 3
    assert output["company_number"].sort().to_list() == ["A", "B", "C"]
    assert set(output.columns).isdisjoint(FORBIDDEN_GOVERNED_COLUMNS)
    assert all(
        column == "company_number"
        or column in {"has_psc", "has_accounts"}
        or column.startswith(("reg_", "psc_", "acc_"))
        for column in output.columns
    )
    row_a = output.filter(pl.col("company_number") == "A").row(0, named=True)
    assert row_a["has_psc"] is True
    assert row_a["psc_n_records"] is None
    assert row_a["has_accounts"] is True
    assert row_a["acc_equity"] is None
    row_c = output.filter(pl.col("company_number") == "C").row(0, named=True)
    assert row_c["has_psc"] is False and row_c["has_accounts"] is False

    coverage = manifest["coverage"]
    assert coverage["source_totals_within_register"] == {
        "register": 3,
        "psc": 1,
        "accounts": 2,
    }
    assert coverage["mutually_exclusive_combinations"] == {
        "all_three": 1,
        "register_psc_only": 0,
        "register_accounts_only": 1,
        "register_only": 1,
    }
    assert manifest["excluded_source_companies"]["psc"] == 1
    assert manifest["excluded_source_companies"]["accounts"] == 1
    meanings = manifest["coverage_flag_meanings"]
    assert "independently of null feature values" in meanings["has_psc"]
    assert "independently of null feature values" in meanings["has_accounts"]


def test_governed_join_rejects_person_linkage_or_exact_address(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    _write_parquet(
        inputs.register_path,
        {
            "company_number": ["A"],
            "company_type": ["Private"],
            "accounts_category": ["SMALL"],
            "n_companies_same_address": [2],
        },
    )
    _write_parquet(
        inputs.psc_path,
        {"company_number": ["A"], "companies_per_person_band_ever": ["2-10"]},
    )
    with pytest.raises(ValueError, match="forbidden columns"):
        build_join(
            inputs,
            tmp_path / "output",
            202609,
            "governed",
            memory_limit_gb=1,
            spill_dir=str(tmp_path / "spill"),
        )


def test_join_rejects_duplicate_normalised_source_keys(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    _write_parquet(
        inputs.psc_path,
        {"company_number": ["abc", " ABC "], "psc_n_records": [1, 2]},
    )
    with pytest.raises(ValueError, match="not unique after company-number normalisation"):
        build_join(
            inputs,
            tmp_path / "output",
            202609,
            "governed",
            memory_limit_gb=1,
            spill_dir=str(tmp_path / "spill"),
        )


def _seed_resolved_input_tree(root: Path, tier: str = "governed") -> None:
    register_mode = "features-governed" if tier == "governed" else "features-ungoverned"
    register_dir = root / "snapshot" / "2026-10" / register_mode
    _write_parquet(
        register_dir / "snapshot_company_features.parquet",
        {
            "company_number": ["A"],
            "company_type": ["Private"],
            "accounts_category": ["SMALL"],
        },
    )
    _write_json(
        register_dir / "features_report.json",
        {
            "snapshot_date": "2026-10-01",
            "tier": tier,
            "data_governance": tier == "governed",
        },
    )
    psc_mode = "features-governed" if tier == "governed" else "features-private"
    psc_tier = "governed" if tier == "governed" else "private"
    for snapshot_date in ("2026-09-25", "2026-10-02"):
        psc_dir = root / "psc" / snapshot_date / psc_mode
        _write_parquet(psc_dir / "psc_company_features.parquet", {"company_number": ["A"]})
        _write_json(
            psc_dir / "features_report.json",
            {"snapshot_date": snapshot_date, "tier": psc_tier},
        )
    accounts_dir = root / "accounts" / "v2-internal-202609" / "features" / tier
    _write_parquet(accounts_dir / "accounts_company_features.parquet", {"company_number": ["A"]})
    _write_json(
        accounts_dir / "features_report.json",
        {
            "reference_month_T": 202609,
            "tier": tier,
            "data_governance": tier == "governed",
        },
    )


def test_date_pairing_uses_next_month_register_and_no_lookahead_psc(tmp_path: Path) -> None:
    _seed_resolved_input_tree(tmp_path)
    inputs = resolve_join_inputs(tmp_path, 202609, "governed")
    assert inputs.register_snapshot_date == "2026-10-01"
    assert inputs.psc_snapshot_date == "2026-09-25"
    assert inputs.accounts_reference_month == 202609


def test_join_cli_builds_selected_tier(tmp_path: Path) -> None:
    _seed_resolved_input_tree(tmp_path)
    output = tmp_path / "joined"
    assert main(
        [
            "join",
            "--t",
            "202609",
            "--tier",
            "governed",
            "--data-root",
            str(tmp_path),
            "--output-dir",
            str(output),
            "--memory-limit-gb",
            "1",
            "--spill-dir",
            str(tmp_path / "spill"),
        ]
    ) == 0
    assert (output / "governed" / "joined_company_features.parquet").is_file()
    assert (output / "governed" / "join_manifest.json").is_file()
    assert (output / "join_manifest.json").is_file()


def test_accounts_rows_available_after_t_do_not_enter_join(tmp_path: Path) -> None:
    wide = _write_parquet(
        tmp_path / "wide.parquet",
        {
            "company": ["A", "B"],
            "period_end": ["2025-12-31", "2025-12-31"],
            "row_available_yyyymm": [202609, 202610],
            "Equity": [1.0, 2.0],
            "CurrentAssets": [1.0, 2.0],
            "creditors_within_one_year": [1.0, 1.0],
            "NetCurrentAssetsLiabilities": [1.0, 2.0],
            "CashBankOnHand": [1.0, 2.0],
            "AverageNumberEmployeesDuringPeriod": [1.0, 2.0],
            "employees_unit_anomaly": [False, False],
        },
    )
    register_csv = tmp_path / "register.csv"
    register_csv.write_text(
        "CompanyNumber,Accounts.AccountCategory\nA,SMALL\nB,SMALL\n", encoding="utf-8"
    )
    accounts_dir = tmp_path / "account-features"
    build_accounts_features(
        wide,
        str(register_csv),
        accounts_dir,
        202609,
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "accounts-spill"),
    )
    inputs = _inputs(tmp_path / "join", register_numbers=("A", "B"))
    inputs = JoinInputs(
        **{
            **inputs.__dict__,
            "accounts_path": accounts_dir / "accounts_company_features.parquet",
            "accounts_report": accounts_dir / "features_report.json",
        }
    )
    build_join(
        inputs,
        tmp_path / "output",
        202609,
        "governed",
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "join-spill"),
    )
    output = pl.read_parquet(tmp_path / "output" / "joined_company_features.parquet")
    flags = dict(zip(output["company_number"], output["has_accounts"], strict=True))
    assert flags == {"A": True, "B": False}
