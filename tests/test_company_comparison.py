from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from ukcompany.validation.company_comparison import (
    MODEL_NAMES,
    _build_pipeline,
    _prepare_features,
    classify_status,
    run_company_comparison,
    sampling_plan,
    sha256_file,
    split_bucket,
    validate_predictor_whitelist,
)


def _synthetic_spec(tmp_path: Path) -> tuple[Path, Path]:
    source_spec = json.loads(
        Path("config/company-comparison-study.json").read_text(encoding="utf-8")
    )
    rows = []
    statuses = (
        ["In Administration"] * 30
        + ["Active"] * 240
        + ["Active - Proposal to Strike off"] * 60
        + ["Liquidation"] * 20
    )
    all_feature_columns = []
    for family in source_spec["features"].values():
        for kind in ("log1p", "signed_log1p", "binary", "categorical"):
            all_feature_columns.extend(family.get(kind, []))
    categorical = {
        column
        for family in source_spec["features"].values()
        for column in family.get("categorical", [])
    }
    binary = {
        column
        for family in source_spec["features"].values()
        for column in family.get("binary", [])
    }
    for index, status in enumerate(statuses):
        row = {
            "company_number": f"{index:08d}",
            "reg_company_status": status,
            "reg_company_type": (
                "Private Limited Company" if index % 7 else "Public Limited Company"
            ),
            "reg_age_months": 12 + index % 300,
            "reg_sic_sections": "J" if index % 3 else "F,J",
            "has_psc": index % 5 != 0,
            "has_accounts": index % 4 != 0,
        }
        for column in all_feature_columns:
            if column in categorical:
                row[column] = None if index % 11 == 0 else f"category-{index % 3}"
            elif column in binary:
                row[column] = None if index % 13 == 0 else index % 2 == 0
            else:
                row[column] = None if index % 17 == 0 else float(index % 23)
        rows.append(row)
    joined = tmp_path / "joined.parquet"
    pl.DataFrame(rows).write_parquet(joined)
    source_spec["input"].update(
        {
            "join_path": str(joined),
            "manifest_path": str(tmp_path / "manifest.json"),
            "join_sha256": sha256_file(joined),
            "rows": len(rows),
        }
    )
    source_spec["outcome"]["expected_counts"] = {
        "recorded_adverse": 30,
        "without_recorded_adverse": 300,
        "ambiguous_liquidation": 20,
    }
    source_spec["sampling"]["comparison_per_case"] = 2
    source_spec["modelling"].update(
        {
            "cv_folds": 2,
            "c_grid": [1.0],
            "bootstrap_replicates": 3,
            "categorical_min_frequency": 2,
            "max_iter": 100,
        }
    )
    manifest = {
        "tier": "governed",
        "generated_at": "2026-10-10T12:33:23+00:00",
        "pairing": {
            "register_snapshot_date": "2026-10-01",
            "psc_snapshot_date": "2026-09-25",
            "accounts_reference_month": 202609,
        },
        "output": {"rows": len(rows), "sha256": source_spec["input"]["join_sha256"]},
    }
    Path(source_spec["input"]["manifest_path"]).write_text(json.dumps(manifest))
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(source_spec))
    return spec_path, joined


def test_labels_exclude_ambiguous_liquidation():
    spec = json.loads(Path("config/company-comparison-study.json").read_text())
    assert classify_status("In Administration", spec) == "recorded_adverse"
    assert classify_status("Active - Proposal to Strike off", spec) == (
        "without_recorded_adverse"
    )
    assert classify_status("Liquidation", spec) == "ambiguous_liquidation"
    with pytest.raises(ValueError, match="unmapped"):
        classify_status("Dissolved", spec)


def test_uniform_sampling_weights_reconcile_exact_counts():
    plan = sampling_plan(case_count=73, comparison_count=5_589, ratio=20)
    assert plan["target_comparisons"] == 1_460
    assert 0 < plan["comparison_inclusion_probability"] < 1
    assert plan["target_comparisons"] * plan["comparison_weight"] == pytest.approx(5_589)
    assert plan["eligible_cases"] * plan["case_weight"] == 73


def test_seeded_split_is_reproducible_and_company_separated():
    first = {company: split_bucket(company, 20260901) for company in ("A", "B", "C")}
    second = {company: split_bucket(company, 20260901) for company in ("A", "B", "C")}
    assert first == second
    train = {company for company, bucket in first.items() if bucket < 800_000}
    test = set(first) - train
    assert train.isdisjoint(test)


def test_forbidden_predictors_fail_closed():
    spec = json.loads(Path("config/company-comparison-study.json").read_text())
    with pytest.raises(ValueError, match="forbidden predictor"):
        validate_predictor_whitelist(["reg_company_status"], spec)
    with pytest.raises(ValueError, match="outside frozen whitelist"):
        validate_predictor_whitelist(["invented_signal"], spec)


def test_preprocessing_statistics_are_fit_from_training_data_only(tmp_path: Path):
    pytest.importorskip("sklearn")
    spec_path, joined = _synthetic_spec(tmp_path)
    spec = json.loads(spec_path.read_text())
    frame = pl.read_parquet(joined).to_pandas()
    frame["outcome"] = [1] * 30 + [0] * 320
    frame["split"] = ["train"] * 300 + ["test"] * 50
    frame["sample_weight"] = 1.0
    frame["inclusion_probability"] = 1.0
    prepared = _prepare_features(frame, spec)
    pipeline, definition = _build_pipeline(spec, "register", 1.0)
    predictors = sum(definition.values(), [])
    train = prepared[prepared["split"] == "train"]
    pipeline.fit(
        train[predictors],
        train["outcome"],
        model__sample_weight=train["sample_weight"],
    )
    imputer = pipeline.named_steps["preprocess"].named_transformers_["log1p"].named_steps[
        "impute"
    ]
    charges_index = definition["log1p"].index("reg_n_charges")
    expected = pd.to_numeric(train["reg_n_charges"], errors="coerce").median()
    assert imputer.statistics_[charges_index] == pytest.approx(expected)


def test_synthetic_study_is_aggregate_only_and_reconciles(tmp_path: Path):
    pytest.importorskip("sklearn")
    spec_path, _ = _synthetic_spec(tmp_path)
    report = run_company_comparison(spec_path, memory_limit_gb=1, spill_dir=tmp_path / "spill")

    assert report["aggregate_only"] is True
    assert report["not_forecasting"] is True
    assert report["cohort"]["status_counts"] == {
        "recorded_adverse": 30,
        "without_recorded_adverse": 300,
        "ambiguous_liquidation": 20,
    }
    assert set(report["populations"]["primary"]["models"]) == set(MODEL_NAMES)
    for population in report["populations"].values():
        for split in population["sampling"]:
            assert split["comparison_inclusion_probability"] > 0
            assert split["weighted_comparisons"] == pytest.approx(
                split["eligible_comparisons"]
            )
    encoded = json.dumps(report)
    assert '"00000000"' not in encoded
    assert '"00000001"' not in encoded
    assert "company_number" not in report["populations"]["primary"]
