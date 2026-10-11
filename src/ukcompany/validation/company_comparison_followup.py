"""Exploratory accounts ablation and model-importance follow-up.

This module reuses the frozen contemporaneous comparison pipeline. It explains
classification of an already-recorded registrar status; it does not forecast
future insolvency and is not production scoring code.
"""

from __future__ import annotations

import hashlib
import math
import resource
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from ukcompany.psc.loader import _connect

from .company_comparison import (
    _all_feature_columns,
    _assert_sampling_design_matches_baseline,
    _feature_definition,
    _fit_definition,
    _git_commit,
    _paired_bootstrap,
    _prepare_cohort,
    _prepare_features,
    _sample_identity_hashes,
    _sample_population,
    _weighted_core_metrics,
    load_study_spec,
    sha256_file,
    study_spec_sha256,
    validate_predictor_whitelist,
    verify_study_input,
)

ABLATION_MODEL_NAMES = (
    "accounts_metadata_baseline",
    "accounts_financial",
    "accounts_history",
    "accounts_financial_history",
)
EXPLAINED_MODEL_NAMES = (
    "register",
    "register_accounts",
    "register_psc",
    "combined",
)
ABLATION_COMPARISONS = (
    ("accounts_financial_vs_metadata", "accounts_metadata_baseline", "accounts_financial"),
    ("accounts_history_vs_metadata", "accounts_metadata_baseline", "accounts_history"),
    (
        "accounts_financial_history_vs_metadata",
        "accounts_metadata_baseline",
        "accounts_financial_history",
    ),
    (
        "accounts_history_beyond_financial",
        "accounts_financial",
        "accounts_financial_history",
    ),
    (
        "accounts_financial_beyond_history",
        "accounts_history",
        "accounts_financial_history",
    ),
)


def validate_accounts_column_groups(
    followup_spec: dict[str, Any], base_spec: dict[str, Any]
) -> dict[str, str]:
    groups = followup_spec["accounts_column_groups"]
    expected = set(_all_feature_columns(base_spec, "accounts"))
    assignment: dict[str, str] = {}
    for group_name in (
        "financial_position_scale",
        "financial_change",
        "recency_history",
    ):
        for column in groups[group_name]:
            if column in assignment:
                raise ValueError(f"duplicate accounts group assignment: {column}")
            assignment[column] = group_name
    metadata = groups["availability_reporting_metadata"]
    for column in metadata:
        if column == "has_accounts" or column.startswith("missing__"):
            continue
        if column in assignment:
            raise ValueError(f"duplicate accounts group assignment: {column}")
        assignment[column] = "availability_reporting_metadata"
    if set(assignment) != expected:
        raise ValueError(
            "accounts group mapping does not close: "
            f"missing={sorted(expected - set(assignment))}, "
            f"extra={sorted(set(assignment) - expected)}"
        )
    expected_indicators = {f"missing__{column}" for column in expected}
    observed_indicators = {column for column in metadata if column.startswith("missing__")}
    if observed_indicators != expected_indicators or "has_accounts" not in metadata:
        raise ValueError("accounts metadata baseline has incomplete presence/observation fields")
    return assignment


def _feature_kind(base_spec: dict[str, Any], family: str, column: str) -> str:
    matches = [
        kind
        for kind in ("log1p", "signed_log1p", "binary", "categorical")
        if column in base_spec["features"][family].get(kind, [])
    ]
    if len(matches) != 1:
        raise ValueError(f"{column} has {len(matches)} transformation assignments")
    return matches[0]


def accounts_ablation_definition(
    base_spec: dict[str, Any], followup_spec: dict[str, Any], model_name: str
) -> dict[str, list[str]]:
    if model_name not in ABLATION_MODEL_NAMES:
        raise ValueError(f"unknown accounts ablation model: {model_name}")
    definition = deepcopy(_feature_definition(base_spec, "register_accounts_availability"))
    groups = followup_spec["accounts_column_groups"]
    included_groups = followup_spec["ablation_models"][model_name]
    raw_columns = ["acc_accounts_category", "acc_employees_unit_anomaly"]
    for group_name in included_groups:
        raw_columns.extend(groups[group_name])
    for column in raw_columns:
        kind = _feature_kind(base_spec, "accounts", column)
        definition[kind].append(column)
    for kind in definition:
        definition[kind] = list(dict.fromkeys(definition[kind]))
    predictors = sum(definition.values(), [])
    if len(predictors) != len(set(predictors)):
        raise ValueError(f"{model_name} contains a duplicate predictor")
    validate_predictor_whitelist(predictors, base_spec)
    return definition


def _permutation_columns(
    raw_columns: list[str], predictors: set[str], *, move_owner_missingness: bool
) -> list[str]:
    columns: list[str] = []
    for column in raw_columns:
        if column in predictors:
            columns.append(column)
        missing = f"missing__{column}"
        if move_owner_missingness and missing in predictors:
            columns.append(missing)
    return list(dict.fromkeys(columns))


def permutation_blocks(
    followup_spec: dict[str, Any], predictors: list[str]
) -> dict[str, dict[str, list[str]]]:
    predictor_set = set(predictors)
    output: dict[str, dict[str, list[str]]] = {}
    for level, configured in followup_spec["importance_groups"].items():
        output[level] = {}
        for name, raw_columns in configured.items():
            move_missingness = not (level == "broad" and name == "availability_reporting")
            columns = _permutation_columns(
                raw_columns,
                predictor_set,
                move_owner_missingness=move_missingness,
            )
            if columns:
                output[level][name] = columns
    return output


def permute_frame_columns(frame, columns: list[str], permutation):
    permuted = frame.copy()
    for column in columns:
        permuted[column] = frame[column].iloc[permutation].array
    return permuted


def permutation_importance(
    pipeline,
    test_frame,
    predictors: list[str],
    blocks: dict[str, dict[str, list[str]]],
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    import numpy as np

    x_test = test_frame[predictors]
    outcome = test_frame["outcome"].astype(int).to_numpy()
    weight = test_frame["sample_weight"].astype(float).to_numpy()
    baseline_probability = pipeline.predict_proba(x_test)[:, 1]
    baseline = _weighted_core_metrics(outcome, baseline_probability, weight)
    output: dict[str, Any] = {"baseline_metrics": baseline, "levels": {}}
    for level, groups in blocks.items():
        output["levels"][level] = []
        for group_name, columns in groups.items():
            digest = hashlib.sha256(f"{seed}|{level}|{group_name}".encode()).digest()
            group_seed = int.from_bytes(digest[:8], "little")
            rng = np.random.default_rng(group_seed)
            log_loss_increase = []
            average_precision_decrease = []
            for _ in range(replicates):
                permutation = rng.permutation(len(x_test))
                permuted = permute_frame_columns(x_test, columns, permutation)
                probability = pipeline.predict_proba(permuted)[:, 1]
                metrics = _weighted_core_metrics(outcome, probability, weight)
                log_loss_increase.append(metrics["log_loss"] - baseline["log_loss"])
                average_precision_decrease.append(
                    baseline["average_precision"] - metrics["average_precision"]
                )
            output["levels"][level].append(
                {
                    "group": group_name,
                    "columns": columns,
                    "replicates": replicates,
                    "seed": group_seed,
                    "weighted_log_loss_increase": {
                        "mean": float(np.mean(log_loss_increase)),
                        "standard_deviation": float(np.std(log_loss_increase, ddof=1)),
                        "minimum": float(np.min(log_loss_increase)),
                        "maximum": float(np.max(log_loss_increase)),
                    },
                    "weighted_average_precision_decrease": {
                        "mean": float(np.mean(average_precision_decrease)),
                        "standard_deviation": float(
                            np.std(average_precision_decrease, ddof=1)
                        ),
                        "minimum": float(np.min(average_precision_decrease)),
                        "maximum": float(np.max(average_precision_decrease)),
                    },
                }
            )
        output["levels"][level].sort(
            key=lambda row: row["weighted_log_loss_increase"]["mean"], reverse=True
        )
    return output


def coefficient_table(pipeline, definition: dict[str, list[str]]) -> dict[str, Any]:
    import numpy as np

    preprocessor = pipeline.named_steps["preprocess"]
    coefficients = pipeline.named_steps["model"].coef_[0]
    rows: list[dict[str, Any]] = []
    for kind in ("log1p", "signed_log1p", "binary"):
        columns = definition[kind]
        if not columns:
            continue
        output_slice = preprocessor.output_indices_[kind]
        transformer = preprocessor.named_transformers_[kind]
        scales = transformer.named_steps["scale"].scale_
        for offset, (column, scale) in enumerate(zip(columns, scales, strict=True)):
            model_coefficient = float(coefficients[output_slice.start + offset])
            if kind == "binary":
                effect_log_odds = model_coefficient / float(scale)
                unit = "raw 0-to-1 change; model input was divided by training SD"
            else:
                effect_log_odds = model_coefficient
                transform = "log1p(max(x, 0))" if kind == "log1p" else "sign(x)*log1p(abs(x))"
                unit = f"one training-SD increase in {transform}"
            rows.append(
                {
                    "logical_feature": column,
                    "encoded_feature": f"{kind}__{column}",
                    "level": None,
                    "transformation": kind,
                    "model_coefficient": model_coefficient,
                    "effect_log_odds": float(effect_log_odds),
                    "odds_ratio": float(math.exp(np.clip(effect_log_odds, -700, 700))),
                    "unit_or_reference": unit,
                }
            )
    categorical = definition["categorical"]
    if categorical:
        output_slice = preprocessor.output_indices_["categorical"]
        encoder = preprocessor.named_transformers_["categorical"].named_steps["encode"]
        names = encoder.get_feature_names_out(categorical)
        for offset, encoded in enumerate(names):
            column = next(
                column
                for column in sorted(categorical, key=len, reverse=True)
                if encoded.startswith(f"{column}_")
            )
            level = encoded[len(column) + 1 :]
            coefficient = float(coefficients[output_slice.start + offset])
            rows.append(
                {
                    "logical_feature": column,
                    "encoded_feature": f"categorical__{encoded}",
                    "level": level,
                    "transformation": "one_hot",
                    "model_coefficient": coefficient,
                    "effect_log_odds": coefficient,
                    "odds_ratio": float(math.exp(np.clip(coefficient, -700, 700))),
                    "unit_or_reference": (
                        "category indicator versus zero contribution; no category was omitted, "
                        "so pairwise contrasts use coefficient differences"
                    ),
                }
            )
    rows.sort(key=lambda row: abs(row["effect_log_odds"]), reverse=True)
    return {
        "intercept": float(pipeline.named_steps["model"].intercept_[0]),
        "categorical_reference_policy": (
            "Full one-hot encoding with no omitted reference category under L2 regularisation."
        ),
        "numeric_scale_policy": (
            "Continuous coefficients are per training-SD transformed unit; binary odds ratios "
            "are converted back to a raw 0-to-1 change."
        ),
        "rows": rows,
    }


def _validate_frozen_inputs(
    followup_spec: dict[str, Any], base_spec: dict[str, Any], source_result: dict[str, Any]
) -> None:
    if followup_spec.get("exploratory") is not True:
        raise ValueError("accounts importance follow-up must be exploratory")
    if study_spec_sha256(base_spec) != followup_spec["base_study_spec_sha256"]:
        raise ValueError("base study spec hash differs from the follow-up freeze")
    source_path = followup_spec["source_additions_result_path"]
    if sha256_file(source_path) != followup_spec["source_additions_result_sha256"]:
        raise ValueError("source-addition result hash differs from the follow-up freeze")
    if (
        source_result["source_aggregate_sha256"]
        != followup_spec["source_additions_aggregate_sha256"]
    ):
        raise ValueError("promoted source-addition aggregate hash differs from the freeze")
    if tuple(followup_spec["populations"]) != ("primary", "complete_source"):
        raise ValueError("follow-up populations differ from the frozen design")
    if tuple(followup_spec["coefficient_models"]) != EXPLAINED_MODEL_NAMES:
        raise ValueError("explained models differ from the frozen design")
    if tuple(followup_spec["ablation_models"]) != ABLATION_MODEL_NAMES:
        raise ValueError("ablation models differ from the frozen design")
    validate_accounts_column_groups(followup_spec, base_spec)


def run_company_comparison_accounts_importance(
    followup_spec_path: str | Path,
    *,
    memory_limit_gb: int = 8,
    spill_dir: str | Path = "/tmp/ukcompany-company-comparison-accounts-importance-spill",
) -> dict[str, Any]:
    started = time.perf_counter()
    followup_spec = load_study_spec(followup_spec_path)
    base_spec = load_study_spec(followup_spec["base_study_spec_path"])
    source_result = load_study_spec(followup_spec["source_additions_result_path"])
    _validate_frozen_inputs(followup_spec, base_spec, source_result)
    inputs = verify_study_input(base_spec)
    if inputs != source_result["inputs"]:
        raise ValueError("current input provenance differs from the source-addition analysis")

    con = _connect(memory_limit_gb, str(spill_dir))
    try:
        cohort = _prepare_cohort(con, base_spec)
        if cohort != source_result["cohort"]:
            raise RuntimeError("cohort or held-out split differs from source additions")
        population_results: dict[str, Any] = {}
        for population_index, population in enumerate(followup_spec["populations"]):
            population_started = time.perf_counter()
            print(f"sampling accounts-importance population={population}", flush=True)
            sampled, sampling = _sample_population(
                con, base_spec, population, sample_method="deterministic_hash"
            )
            _assert_sampling_design_matches_baseline(
                sampling,
                source_result["populations"][population]["sampling"],
                population=population,
            )
            identity_hashes = _sample_identity_hashes(sampled)
            if identity_hashes != followup_spec["sample_identity_hashes"][population]:
                raise RuntimeError(f"{population} sample identities differ from the freeze")
            if identity_hashes != source_result["populations"][population][
                "sample_identity_hashes"
            ]:
                raise RuntimeError(f"{population} sample identities differ from source additions")
            prepared = _prepare_features(sampled, base_spec)

            ablation_results: dict[str, Any] = {}
            predictions: dict[str, Any] = {}
            fitted: dict[str, Any] = {}
            for model_name in ABLATION_MODEL_NAMES:
                model_started = time.perf_counter()
                print(
                    f"fitting accounts ablation population={population} model={model_name}",
                    flush=True,
                )
                definition = accounts_ablation_definition(
                    base_spec, followup_spec, model_name
                )
                result, model_predictions, fitted_model = _fit_definition(
                    prepared, base_spec, model_name, definition
                )
                ablation_results[model_name] = result
                predictions[model_name] = model_predictions
                fitted[model_name] = fitted_model
                print(
                    f"completed accounts ablation population={population} model={model_name} "
                    f"seconds={time.perf_counter() - model_started:.1f}",
                    flush=True,
                )

            explained_results: dict[str, Any] = {}
            explained_fitted: dict[str, Any] = {}
            explained_predictions: dict[str, Any] = {}
            for model_name in EXPLAINED_MODEL_NAMES:
                if model_name == "register_accounts":
                    result = deepcopy(ablation_results["accounts_financial_history"])
                    result["model"] = model_name
                    explained_results[model_name] = result
                    explained_fitted[model_name] = fitted["accounts_financial_history"]
                    explained_predictions[model_name] = predictions[
                        "accounts_financial_history"
                    ]
                    continue
                model_started = time.perf_counter()
                print(
                    f"fitting importance population={population} model={model_name}",
                    flush=True,
                )
                definition = _feature_definition(base_spec, model_name)
                result, model_predictions, fitted_model = _fit_definition(
                    prepared, base_spec, model_name, definition
                )
                explained_results[model_name] = result
                explained_fitted[model_name] = fitted_model
                explained_predictions[model_name] = model_predictions
                print(
                    f"completed importance population={population} model={model_name} "
                    f"seconds={time.perf_counter() - model_started:.1f}",
                    flush=True,
                )

            paired = {}
            for comparison_index, (name, reference, candidate) in enumerate(
                ABLATION_COMPARISONS
            ):
                paired[name] = _paired_bootstrap(
                    predictions[reference],
                    predictions[candidate],
                    base_spec["modelling"]["bootstrap_replicates"],
                    base_spec["modelling"]["random_seed"]
                    + 500
                    + population_index * 100
                    + comparison_index,
                    reference_name=reference,
                    candidate_name=candidate,
                )

            coefficient_results = {}
            permutation_results = {}
            for model_index, model_name in enumerate(EXPLAINED_MODEL_NAMES):
                fitted_model = explained_fitted[model_name]
                coefficient_results[model_name] = coefficient_table(
                    fitted_model["pipeline"], fitted_model["definition"]
                )
                blocks = permutation_blocks(
                    followup_spec, fitted_model["predictors"]
                )
                print(
                    f"permuting population={population} model={model_name} "
                    f"groups={sum(len(groups) for groups in blocks.values())}",
                    flush=True,
                )
                permutation_results[model_name] = permutation_importance(
                    fitted_model["pipeline"],
                    fitted_model["test_frame"],
                    fitted_model["predictors"],
                    blocks,
                    replicates=followup_spec["permutation"]["replicates"],
                    seed=(
                        followup_spec["permutation"]["seed"]
                        + population_index * 100
                        + model_index
                    ),
                )

            population_results[population] = {
                "sampling": sampling,
                "sample_identity_hashes": identity_hashes,
                "ablation_models": ablation_results,
                "paired_ablation_comparisons": paired,
                "explained_models": explained_results,
                "coefficients": coefficient_results,
                "permutation_importance": permutation_results,
            }
            print(
                f"completed accounts-importance population={population} "
                f"seconds={time.perf_counter() - population_started:.1f}",
                flush=True,
            )
    finally:
        con.close()

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if __import__("sys").platform == "darwin" else peak * 1024
    return {
        "study": "exploratory accounts content, timing and feature importance",
        "study_version": followup_spec["study_version"],
        "exploratory": True,
        "reason": followup_spec["reason"],
        "aggregate_only": True,
        "not_forecasting": True,
        "code_commit": _git_commit(),
        "followup_spec": {
            "path": str(followup_spec_path),
            "sha256": sha256_file(followup_spec_path),
            "contents": followup_spec,
        },
        "base_study_spec": {
            "path": followup_spec["base_study_spec_path"],
            "sha256": study_spec_sha256(base_spec),
        },
        "source_additions_result": {
            "path": followup_spec["source_additions_result_path"],
            "sha256": sha256_file(followup_spec["source_additions_result_path"]),
            "source_aggregate_sha256": source_result["source_aggregate_sha256"],
        },
        "inputs": inputs,
        "cohort": cohort,
        "accounts_column_assignment": validate_accounts_column_groups(
            followup_spec, base_spec
        ),
        "populations": population_results,
        "runtime": {
            "seconds": time.perf_counter() - started,
            "peak_rss_bytes": peak_bytes,
        },
    }


def validate_accounts_importance_report(
    report: dict[str, Any],
    followup_spec: dict[str, Any],
    base_spec: dict[str, Any],
    source_result: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np

    if report.get("exploratory") is not True or not report.get("aggregate_only"):
        raise ValueError("follow-up scope flags are missing")
    if report.get("not_forecasting") is not True:
        raise ValueError("follow-up is not labelled non-forecasting")
    if report["followup_spec"]["contents"] != followup_spec:
        raise ValueError("embedded follow-up spec differs from the freeze")
    if report["cohort"] != source_result["cohort"]:
        raise ValueError("cohort or split differs from source additions")
    validate_accounts_column_groups(followup_spec, base_spec)
    final_fits = 0
    cv_fits = 0
    paired = 0
    permutation_blocks_checked = 0
    coefficient_rows_checked = 0
    for population in followup_spec["populations"]:
        result = report["populations"][population]
        if result["sample_identity_hashes"] != followup_spec["sample_identity_hashes"][
            population
        ]:
            raise ValueError(f"{population} sample hash differs from the freeze")
        _assert_sampling_design_matches_baseline(
            result["sampling"],
            source_result["populations"][population]["sampling"],
            population=population,
        )
        if set(result["ablation_models"]) != set(ABLATION_MODEL_NAMES):
            raise ValueError(f"{population} ablation models differ from the freeze")
        if set(result["explained_models"]) != set(EXPLAINED_MODEL_NAMES):
            raise ValueError(f"{population} explained models differ from the freeze")
        unique_models = {
            **result["ablation_models"],
            **{
                name: value
                for name, value in result["explained_models"].items()
                if name != "register_accounts"
            },
        }
        for model_name, model in unique_models.items():
            final_fits += 1
            if model["convergence_warnings"] != 0:
                raise ValueError(f"{population}/{model_name} did not converge")
            if [row["c"] for row in model["cv"]] != [
                float(value) for value in base_spec["modelling"]["c_grid"]
            ]:
                raise ValueError(f"{population}/{model_name} CV grid is incomplete")
            if not all(np.isfinite(row["weighted_log_loss"]) for row in model["cv"]):
                raise ValueError(f"{population}/{model_name} CV metric is non-finite")
            cv_fits += len(model["cv"]) * base_spec["modelling"]["cv_folds"]
        if set(result["paired_ablation_comparisons"]) != {
            row[0] for row in ABLATION_COMPARISONS
        }:
            raise ValueError(f"{population} paired ablation contrasts are incomplete")
        for comparison_name, comparison in result[
            "paired_ablation_comparisons"
        ].items():
            paired += 1
            _, reference_name, candidate_name = next(
                row for row in ABLATION_COMPARISONS if row[0] == comparison_name
            )
            reference = result["ablation_models"][reference_name]["test_metrics"]
            candidate = result["ablation_models"][candidate_name]["test_metrics"]
            for metric_name, metric in comparison.items():
                expected = (
                    candidate[metric_name] - reference[metric_name]
                    if metric_name in {"roc_auc", "average_precision"}
                    else reference[metric_name] - candidate[metric_name]
                )
                if not math.isclose(
                    metric["observed_difference"], expected, rel_tol=1e-12, abs_tol=1e-12
                ):
                    raise ValueError(
                        f"{population}/{comparison_name}/{metric_name} difference mismatch"
                    )
                values = [
                    metric["observed_difference"],
                    metric["bootstrap_mean"],
                    *metric["ci95"],
                ]
                if not all(np.isfinite(value) for value in values):
                    raise ValueError(f"{population} paired metric is non-finite")
        for model_name in EXPLAINED_MODEL_NAMES:
            coefficients = result["coefficients"][model_name]["rows"]
            coefficient_rows_checked += len(coefficients)
            if not coefficients or not all(
                np.isfinite(row["effect_log_odds"]) and np.isfinite(row["odds_ratio"])
                for row in coefficients
            ):
                raise ValueError(f"{population}/{model_name} coefficients are incomplete")
            importance = result["permutation_importance"][model_name]
            if set(importance["levels"]) != {"logical", "broad"}:
                raise ValueError(f"{population}/{model_name} permutation levels are incomplete")
            for groups in importance["levels"].values():
                for group in groups:
                    permutation_blocks_checked += 1
                    if group["replicates"] != followup_spec["permutation"]["replicates"]:
                        raise ValueError("permutation replicate count differs from the freeze")
                    if len(group["columns"]) != len(set(group["columns"])):
                        raise ValueError("permutation block contains duplicate columns")
                    for summary in (
                        group["weighted_log_loss_increase"],
                        group["weighted_average_precision_decrease"],
                    ):
                        if not all(np.isfinite(value) for value in summary.values()):
                            raise ValueError("permutation summary is non-finite")
    return {
        "status": "passed",
        "exploratory": True,
        "unchanged_cohort_split_samples_weights_and_preprocessing": True,
        "final_fits_checked": final_fits,
        "final_convergence_warnings": 0,
        "cross_validation_fits_checked": cv_fits,
        "cross_validation_warning_gate": "passed_by_fail-fast_run_completion",
        "paired_ablation_contrasts_checked": paired,
        "coefficient_rows_checked": coefficient_rows_checked,
        "permutation_blocks_checked": permutation_blocks_checked,
    }
