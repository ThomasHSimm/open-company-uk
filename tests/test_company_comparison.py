from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from ukcompany.validation.company_comparison import (
    MODEL_NAMES,
    SOURCE_ADDITION_MODEL_NAMES,
    _build_pipeline,
    _feature_definition,
    _prepare_features,
    build_committed_company_comparison_aggregate,
    classify_status,
    run_company_comparison,
    run_company_comparison_source_additions,
    sampling_plan,
    sha256_file,
    split_bucket,
    study_spec_sha256,
    validate_company_comparison_report,
    validate_company_comparison_source_additions,
    validate_predictor_whitelist,
)
from ukcompany.validation.company_comparison_followup import (
    ABLATION_MODEL_NAMES,
    EXPLAINED_MODEL_NAMES,
    accounts_ablation_definition,
    permutation_blocks,
    permutation_importance,
    permute_frame_columns,
    run_company_comparison_accounts_importance,
    validate_accounts_column_groups,
    validate_accounts_importance_report,
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
            "solver": "newton-cholesky",
            "max_iter": 100,
            "tolerance": 1e-6,
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


def test_source_addition_feature_sets_separate_availability_from_content():
    spec = json.loads(Path("config/company-comparison-study.json").read_text())
    register_accounts = _feature_definition(spec, "register_accounts")
    register_accounts_availability = _feature_definition(
        spec, "register_accounts_availability"
    )
    register_psc = _feature_definition(spec, "register_psc")
    register_psc_availability = _feature_definition(spec, "register_psc_availability")

    assert "acc_equity" in register_accounts["signed_log1p"]
    assert "acc_equity" not in register_accounts_availability["signed_log1p"]
    assert "has_accounts" in register_accounts_availability["binary"]
    assert "missing__acc_equity" in register_accounts_availability["binary"]
    assert "psc_n_records" in register_psc["log1p"]
    assert "psc_n_records" not in register_psc_availability["log1p"]
    assert "has_psc" in register_psc_availability["binary"]
    assert "missing__psc_n_records" in register_psc_availability["binary"]


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
    validation = validate_company_comparison_report(report, json.loads(spec_path.read_text()))
    assert validation["status"] == "passed"
    assert validation["cross_validation_fits_checked"] == 56
    committed = build_committed_company_comparison_aggregate(
        report, validation, source_sha256="abc", minimum_count=10
    )
    assert committed["source_aggregate_sha256"] == "abc"
    assert any(
        row.get("suppressed") is True
        and row["category"] == "__SUPPRESSED_CATEGORIES__"
        for effect in committed["descriptives"]["categorical_effects"]
        for row in effect["counts"]
    )


def test_synthetic_source_additions_reproduce_baseline_and_pair_models(tmp_path: Path):
    pytest.importorskip("sklearn")
    base_spec_path, _ = _synthetic_spec(tmp_path)
    base_spec = json.loads(base_spec_path.read_text())
    baseline = run_company_comparison(
        base_spec_path, memory_limit_gb=1, spill_dir=tmp_path / "baseline-spill"
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True))

    exploratory_spec = json.loads(
        Path("config/company-comparison-source-additions.json").read_text()
    )
    exploratory_spec.update(
        {
            "base_study_spec_path": str(base_spec_path),
            "base_study_spec_sha256": study_spec_sha256(base_spec),
            "baseline_aggregate_path": str(baseline_path),
            "baseline_aggregate_sha256": sha256_file(baseline_path),
        }
    )
    exploratory_spec_path = tmp_path / "source-additions.json"
    exploratory_spec_path.write_text(json.dumps(exploratory_spec))
    report = run_company_comparison_source_additions(
        exploratory_spec_path,
        memory_limit_gb=1,
        spill_dir=tmp_path / "source-additions-spill",
    )
    validation = validate_company_comparison_source_additions(
        report, exploratory_spec, base_spec, baseline
    )

    assert validation["status"] == "passed"
    assert validation["final_fits_checked"] == 14
    assert validation["cross_validation_fits_checked"] == 28
    assert set(report["populations"]["primary"]["models"]) == set(
        SOURCE_ADDITION_MODEL_NAMES
    )
    assert (
        report["populations"]["primary"]["sampling_design_check"]["status"]
        == "passed"
    )
    assert validation["original_reservoir_sample_reused"] is False
    assert len(report["populations"]["primary"]["sample_identity_hashes"]["test"]) == 64
    assert "company_number" not in report["populations"]["primary"]


def test_accounts_followup_groups_assign_every_column_once():
    base_spec = json.loads(Path("config/company-comparison-study.json").read_text())
    followup_spec = json.loads(
        Path("config/company-comparison-accounts-importance.json").read_text()
    )
    assignment = validate_accounts_column_groups(followup_spec, base_spec)

    assert len(assignment) == 17
    assert assignment["acc_equity"] == "financial_position_scale"
    assert assignment["acc_d_cash"] == "financial_change"
    assert assignment["acc_prior_gap_months"] == "recency_history"
    assert assignment["acc_accounts_category"] == "availability_reporting_metadata"
    assert assignment["acc_employees_unit_anomaly"] == (
        "availability_reporting_metadata"
    )
    baseline = accounts_ablation_definition(
        base_spec, followup_spec, "accounts_metadata_baseline"
    )
    financial = accounts_ablation_definition(
        base_spec, followup_spec, "accounts_financial"
    )
    assert "missing__acc_equity" in baseline["binary"]
    assert "acc_equity" not in baseline["signed_log1p"]
    assert "acc_equity" in financial["signed_log1p"]
    assert "acc_accounts_category" in baseline["categorical"]
    metadata = set(followup_spec["accounts_column_groups"]["availability_reporting_metadata"])
    for model_name in ABLATION_MODEL_NAMES:
        definition = accounts_ablation_definition(base_spec, followup_spec, model_name)
        assert metadata <= set(sum(definition.values(), []))

    blocks = permutation_blocks(
        followup_spec, sum(accounts_ablation_definition(
            base_spec, followup_spec, "accounts_financial_history"
        ).values(), [])
    )
    equity_columns = blocks["logical"]["accounts_equity_position"]
    assert "acc_equity" in equity_columns
    assert "acc_negative_equity" in equity_columns
    assert "missing__acc_equity" in equity_columns
    assert "missing__acc_negative_equity" in equity_columns


def test_paired_bootstrap_reports_observed_difference_not_bootstrap_mean():
    pytest.importorskip("sklearn")
    import numpy as np

    from ukcompany.validation.company_comparison import _paired_bootstrap

    reference = {
        "outcome": np.array([0, 0, 0, 1, 1]),
        "weight": np.array([9.0, 9.0, 9.0, 1.0, 1.0]),
        "probability": np.array([0.01, 0.15, 0.30, 0.45, 0.70]),
    }
    candidate = {
        **reference,
        "probability": np.array([0.02, 0.08, 0.20, 0.60, 0.85]),
    }
    paired = _paired_bootstrap(reference, candidate, 25, 17)
    observed = paired["average_precision"]["observed_difference"]
    expected = _weighted_metrics_for_test(candidate)["average_precision"] - (
        _weighted_metrics_for_test(reference)["average_precision"]
    )

    assert observed == pytest.approx(expected)
    assert paired["average_precision"]["bootstrap_mean"] == paired[
        "average_precision"
    ]["estimate"]
    assert paired["average_precision"]["ci95"][0] <= paired[
        "average_precision"
    ]["ci95"][1]


def _weighted_metrics_for_test(predictions):
    from ukcompany.validation.company_comparison import _weighted_core_metrics

    return _weighted_core_metrics(
        predictions["outcome"], predictions["probability"], predictions["weight"]
    )


def test_grouped_permutation_preserves_rows_categories_and_weighted_baseline():
    pytest.importorskip("sklearn")
    import numpy as np

    class FrozenPipeline:
        def predict_proba(self, frame):
            values = frame["signal"].to_numpy(dtype=float)
            probability = 1 / (1 + np.exp(-values))
            return np.column_stack([1 - probability, probability])

    frame = pd.DataFrame(
        {
            "signal": [-3.0, -2.0, 1.0, 3.0],
            "derived": [0, 0, 1, 1],
            "category": pd.Series(["a", "b", "a", "c"], dtype="string"),
            "outcome": [0, 0, 1, 1],
            "sample_weight": [10.0, 10.0, 1.0, 1.0],
        }
    )
    original = frame.copy(deep=True)
    permutation = np.array([2, 3, 0, 1])
    permuted = permute_frame_columns(
        frame[["signal", "derived", "category"]],
        ["signal", "derived", "category"],
        permutation,
    )
    assert frame.equals(original)
    assert permuted["derived"].tolist() == [1, 1, 0, 0]
    assert set(permuted["category"].dropna()) == {"a", "b", "c"}

    result = permutation_importance(
        FrozenPipeline(),
        frame,
        ["signal", "derived", "category"],
        {"logical": {"signal": ["signal", "derived"]}, "broad": {}},
        replicates=4,
        seed=11,
    )
    direct = _weighted_metrics_for_test(
        {
            "outcome": np.array(frame["outcome"]),
            "probability": FrozenPipeline().predict_proba(frame)[:, 1],
            "weight": np.array(frame["sample_weight"]),
        }
    )
    assert result["baseline_metrics"]["log_loss"] == pytest.approx(direct["log_loss"])
    importance = result["levels"]["logical"][0]
    assert importance["replicates"] == 4
    assert importance["columns"] == ["signal", "derived"]
    assert importance["weighted_log_loss_increase"]["mean"] > 0


def test_synthetic_accounts_followup_preserves_source_addition_sample(tmp_path: Path):
    pytest.importorskip("sklearn")
    base_spec_path, _ = _synthetic_spec(tmp_path)
    base_spec = json.loads(base_spec_path.read_text())
    baseline = run_company_comparison(
        base_spec_path, memory_limit_gb=1, spill_dir=tmp_path / "baseline-spill"
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True))

    source_spec = json.loads(
        Path("config/company-comparison-source-additions.json").read_text()
    )
    source_spec.update(
        {
            "base_study_spec_path": str(base_spec_path),
            "base_study_spec_sha256": study_spec_sha256(base_spec),
            "baseline_aggregate_path": str(baseline_path),
            "baseline_aggregate_sha256": sha256_file(baseline_path),
        }
    )
    source_spec_path = tmp_path / "source-additions-spec.json"
    source_spec_path.write_text(json.dumps(source_spec))
    source_result = run_company_comparison_source_additions(
        source_spec_path,
        memory_limit_gb=1,
        spill_dir=tmp_path / "source-additions-spill",
    )
    source_result["source_aggregate_sha256"] = "synthetic-source-aggregate"
    source_result_path = tmp_path / "source-additions-result.json"
    source_result_path.write_text(json.dumps(source_result, sort_keys=True))

    followup_spec = json.loads(
        Path("config/company-comparison-accounts-importance.json").read_text()
    )
    followup_spec.update(
        {
            "base_study_spec_path": str(base_spec_path),
            "base_study_spec_sha256": study_spec_sha256(base_spec),
            "source_additions_result_path": str(source_result_path),
            "source_additions_result_sha256": sha256_file(source_result_path),
            "source_additions_aggregate_sha256": "synthetic-source-aggregate",
            "sample_identity_hashes": {
                population: result["sample_identity_hashes"]
                for population, result in source_result["populations"].items()
            },
        }
    )
    followup_spec["permutation"]["replicates"] = 2
    followup_spec_path = tmp_path / "accounts-followup-spec.json"
    followup_spec_path.write_text(json.dumps(followup_spec))
    report = run_company_comparison_accounts_importance(
        followup_spec_path,
        memory_limit_gb=1,
        spill_dir=tmp_path / "accounts-followup-spill",
    )
    validation = validate_accounts_importance_report(
        report, followup_spec, base_spec, source_result
    )

    assert validation["status"] == "passed"
    assert validation["final_fits_checked"] == 14
    assert validation["cross_validation_fits_checked"] == 28
    assert set(report["populations"]["primary"]["ablation_models"]) == set(
        ABLATION_MODEL_NAMES
    )
    assert set(report["populations"]["primary"]["explained_models"]) == set(
        EXPLAINED_MODEL_NAMES
    )
    assert report["populations"]["primary"]["sample_identity_hashes"] == (
        source_result["populations"]["primary"]["sample_identity_hashes"]
    )
    assert "company_number" not in json.dumps(report["populations"])
