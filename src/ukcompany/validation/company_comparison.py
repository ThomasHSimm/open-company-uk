"""Aggregate-only contemporaneous company-attribute comparison study.

This module is evaluation code. It classifies registrar-recorded status at the
Handoff 10 reference date; it does not forecast future insolvency and must not
be imported by production scoring.
"""

from __future__ import annotations

import hashlib
import json
import math
import resource
import subprocess
import time
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ukcompany.psc.loader import _connect, _sql_literal

MODEL_NAMES = (
    "missingness_only",
    "structural",
    "structural_missingness",
    "register",
    "accounts",
    "psc",
    "combined",
)
POPULATION_FILTERS = {
    "primary": "TRUE",
    "complete_source": "has_psc AND has_accounts",
    "active_only": "(outcome = 1 OR company_status = 'Active')",
    "private_limited": "company_type = 'Private Limited Company'",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_study_spec(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def study_spec_sha256(spec: dict[str, Any]) -> str:
    encoded = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def classify_status(status: str | None, spec: dict[str, Any]) -> str:
    outcome = spec["outcome"]
    if status in outcome["adverse_statuses"]:
        return "recorded_adverse"
    if status in outcome["comparison_statuses"]:
        return "without_recorded_adverse"
    if status in outcome["ambiguous_statuses"]:
        return "ambiguous_liquidation"
    raise ValueError(f"missing or unmapped company status: {status!r}")


def _all_feature_columns(spec: dict[str, Any], family: str | None = None) -> list[str]:
    families = [family] if family else list(spec["features"])
    columns: list[str] = []
    for family_name in families:
        for kind in ("log1p", "signed_log1p", "binary", "categorical"):
            columns.extend(spec["features"][family_name].get(kind, []))
    return columns


def source_columns(spec: dict[str, Any]) -> list[str]:
    return sorted(
        {
            "company_number",
            "reg_company_status",
            "reg_company_type",
            "reg_age_months",
            "reg_sic_sections",
            "has_psc",
            "has_accounts",
            *_all_feature_columns(spec),
        }
    )


def validate_predictor_whitelist(predictors: Iterable[str], spec: dict[str, Any]) -> None:
    predictor_set = set(predictors)
    forbidden = set(spec["forbidden_predictors"])
    leaked = sorted(predictor_set & forbidden)
    if leaked:
        raise ValueError(f"forbidden predictor(s): {leaked}")
    allowed = set(_all_feature_columns(spec))
    allowed.update(spec["structural"]["categorical"])
    allowed.update(spec["structural"]["generated_binary"])
    allowed.update({"has_psc", "has_accounts"})
    allowed.update(f"missing__{column}" for column in _all_feature_columns(spec))
    unknown = sorted(predictor_set - allowed)
    if unknown:
        raise ValueError(f"predictor(s) outside frozen whitelist: {unknown}")


def sampling_plan(case_count: int, comparison_count: int, ratio: int) -> dict[str, Any]:
    if case_count <= 0 or comparison_count <= 0:
        raise ValueError("sampling requires positive case and comparison counts")
    target = min(comparison_count, ratio * case_count)
    probability = target / comparison_count
    return {
        "eligible_cases": case_count,
        "eligible_comparisons": comparison_count,
        "target_comparisons": target,
        "case_inclusion_probability": 1.0,
        "comparison_inclusion_probability": probability,
        "case_weight": 1.0,
        "comparison_weight": comparison_count / target,
    }


def split_bucket(company_number: str, seed: int, modulus: int = 1_000_000) -> int:
    digest = hashlib.md5(f"{company_number}|split|{seed}".encode(), usedforsecurity=False)
    return int.from_bytes(digest.digest()[8:], "little") % modulus


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def verify_study_input(spec: dict[str, Any]) -> dict[str, Any]:
    expected = spec["input"]
    join_path = Path(expected["join_path"])
    manifest_path = Path(expected["manifest_path"])
    if not join_path.is_file():
        raise FileNotFoundError(f"joined input not found: {join_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"join manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = {
        "join_sha256": (sha256_file(join_path), expected["join_sha256"]),
        "register_snapshot_date": (
            manifest["pairing"]["register_snapshot_date"],
            expected["register_snapshot_date"],
        ),
        "psc_snapshot_date": (
            manifest["pairing"]["psc_snapshot_date"],
            expected["psc_snapshot_date"],
        ),
        "accounts_reference_month": (
            manifest["pairing"]["accounts_reference_month"],
            expected["accounts_reference_month"],
        ),
        "rows": (manifest["output"]["rows"], expected["rows"]),
        "manifest_output_sha256": (
            manifest["output"]["sha256"],
            expected["join_sha256"],
        ),
        "tier": (manifest["tier"], "governed"),
    }
    failed = {name: pair for name, pair in checks.items() if pair[0] != pair[1]}
    if failed:
        raise ValueError(f"study input provenance mismatch: {failed}")
    return {
        "join": {
            "path": str(join_path),
            "bytes": join_path.stat().st_size,
            "sha256": checks["join_sha256"][0],
        },
        "manifest": {
            "path": str(manifest_path),
            "bytes": manifest_path.stat().st_size,
            "sha256": sha256_file(manifest_path),
        },
        "pairing": manifest["pairing"],
        "generated_at": manifest["generated_at"],
    }


def _status_case_sql(statuses: list[str], label: str) -> str:
    values = ", ".join(_sql_literal(status) for status in statuses)
    return f"WHEN reg_company_status IN ({values}) THEN {_sql_literal(label)}"


def _prepare_cohort(con, spec: dict[str, Any]) -> dict[str, Any]:
    path = spec["input"]["join_path"]
    required = source_columns(spec)
    actual = {
        row[0]
        for row in con.sql(
            f"DESCRIBE SELECT * FROM read_parquet({_sql_literal(path)})"
        ).fetchall()
    }
    missing = sorted(set(required) - actual)
    if missing:
        raise ValueError(f"joined input missing frozen source column(s): {missing}")
    duplicate_query = f"""
        SELECT count(*) AS rows,
               count(DISTINCT upper(trim(company_number))) AS distinct_keys,
               count(*) FILTER (
                   WHERE company_number IS NULL OR trim(company_number) = ''
               ) AS blank_keys
        FROM read_parquet({_sql_literal(path)})
    """
    rows, distinct_keys, blank_keys = con.sql(duplicate_query).fetchone()
    if rows != spec["input"]["rows"] or distinct_keys != rows or blank_keys:
        raise ValueError(
            "joined input key/row assertion failed: "
            f"rows={rows}, distinct={distinct_keys}, blanks={blank_keys}"
        )
    outcome = spec["outcome"]
    status_case = "CASE " + " ".join(
        [
            _status_case_sql(outcome["adverse_statuses"], "recorded_adverse"),
            _status_case_sql(outcome["comparison_statuses"], "without_recorded_adverse"),
            _status_case_sql(outcome["ambiguous_statuses"], "ambiguous_liquidation"),
        ]
    ) + " ELSE 'unmapped' END"
    con.execute(
        f"""
        CREATE TEMP VIEW study_source AS
        SELECT *, {status_case} AS study_group
        FROM read_parquet({_sql_literal(path)})
        """
    )
    counts = {
        group: int(count)
        for group, count in con.sql(
            "SELECT study_group, count(*) FROM study_source GROUP BY study_group"
        ).fetchall()
    }
    expected = outcome["expected_counts"]
    if counts != expected:
        raise ValueError(f"cohort closure mismatch: observed={counts}, expected={expected}")
    split_seed = spec["sampling"]["split_seed"]
    threshold = int(spec["sampling"]["train_fraction"] * 1_000_000)
    con.execute(
        f"""
        CREATE TEMP TABLE cohort_keys AS
        SELECT company_number,
               CASE WHEN study_group = 'recorded_adverse' THEN 1 ELSE 0 END AS outcome,
               reg_company_status AS company_status,
               reg_company_type AS company_type,
               has_psc,
               has_accounts,
               CASE WHEN (
                    md5_number_lower(company_number || '|split|{split_seed}') % 1000000
               ) < {threshold} THEN 'train' ELSE 'test' END AS split
        FROM study_source
        WHERE study_group IN ('recorded_adverse', 'without_recorded_adverse')
        """
    )
    split_counts = [
        {"split": split, "outcome": int(label), "companies": int(count)}
        for split, label, count in con.sql(
            """
            SELECT split, outcome, count(*)
            FROM cohort_keys GROUP BY split, outcome ORDER BY split, outcome
            """
        ).fetchall()
    ]
    return {"status_counts": counts, "split_counts": split_counts}


def _population_filter(population: str) -> str:
    try:
        return POPULATION_FILTERS[population]
    except KeyError as exc:
        raise ValueError(f"unknown study population: {population}") from exc


def _sample_population(con, spec: dict[str, Any], population: str):
    import pandas as pd

    population_filter = _population_filter(population)
    counts_rows = con.sql(
        f"""
        SELECT split, outcome, count(*) AS companies
        FROM cohort_keys
        WHERE {population_filter}
        GROUP BY split, outcome ORDER BY split, outcome
        """
    ).fetchall()
    counts = {(split, int(outcome)): int(count) for split, outcome, count in counts_rows}
    table = f"sample_{population}"
    con.execute(
        f"""
        CREATE TEMP TABLE {table} (
            company_number VARCHAR,
            outcome INTEGER,
            split VARCHAR,
            inclusion_probability DOUBLE,
            sample_weight DOUBLE
        )
        """
    )
    records = []
    ratio = int(spec["sampling"]["comparison_per_case"])
    seed_base = int(spec["sampling"]["sample_seed"])
    for split_index, split in enumerate(("train", "test")):
        plan = sampling_plan(counts[(split, 1)], counts[(split, 0)], ratio)
        con.execute(
            f"""
            INSERT INTO {table}
            SELECT company_number, outcome, split, 1.0, 1.0
            FROM cohort_keys
            WHERE {population_filter} AND split = {_sql_literal(split)} AND outcome = 1
            """
        )
        target = plan["target_comparisons"]
        seed = seed_base + list(POPULATION_FILTERS).index(population) * 10 + split_index
        con.execute(
            f"""
            INSERT INTO {table}
            SELECT company_number, outcome, split,
                   {plan['comparison_inclusion_probability']},
                   {plan['comparison_weight']}
            FROM (
                SELECT company_number, outcome, split
                FROM cohort_keys
                WHERE {population_filter}
                  AND split = {_sql_literal(split)} AND outcome = 0
            ) USING SAMPLE reservoir({target} ROWS) REPEATABLE({seed})
            """
        )
        sampled_cases, sampled_comparisons, weighted_cases, weighted_comparisons = con.sql(
            f"""
            SELECT count(*) FILTER (WHERE outcome = 1),
                   count(*) FILTER (WHERE outcome = 0),
                   sum(sample_weight) FILTER (WHERE outcome = 1),
                   sum(sample_weight) FILTER (WHERE outcome = 0)
            FROM {table} WHERE split = {_sql_literal(split)}
            """
        ).fetchone()
        if sampled_cases != plan["eligible_cases"] or sampled_comparisons != target:
            raise RuntimeError(f"{population}/{split} fixed-size sample count mismatch")
        if not math.isclose(weighted_cases, plan["eligible_cases"], abs_tol=1e-7):
            raise RuntimeError(f"{population}/{split} weighted case total does not reconcile")
        if not math.isclose(weighted_comparisons, plan["eligible_comparisons"], abs_tol=1e-5):
            raise RuntimeError(
                f"{population}/{split} weighted comparison total does not reconcile"
            )
        records.append(
            {
                "split": split,
                **plan,
                "sampled_cases": int(sampled_cases),
                "sampled_comparisons": int(sampled_comparisons),
                "weighted_cases": float(weighted_cases),
                "weighted_comparisons": float(weighted_comparisons),
                "reservoir_seed": seed,
            }
        )
    columns = source_columns(spec)
    select_columns = ", ".join(f's."{column}"' for column in columns)
    frame = con.execute(
        f"""
        SELECT k.outcome, k.split, k.inclusion_probability, k.sample_weight,
               {select_columns}
        FROM {table} k
        JOIN study_source s USING (company_number)
        ORDER BY k.split, k.outcome, k.company_number
        """
    ).fetch_df()
    if frame["company_number"].duplicated().any():
        raise RuntimeError(f"{population} sample has duplicate companies")
    if set(frame.loc[frame["split"] == "train", "company_number"]) & set(
        frame.loc[frame["split"] == "test", "company_number"]
    ):
        raise RuntimeError(f"{population} train/test company overlap")
    if (frame["inclusion_probability"] <= 0).any():
        raise RuntimeError(f"{population} contains a non-positive inclusion probability")
    return pd.DataFrame(frame), records


def _prepare_features(frame, spec: dict[str, Any]):
    import numpy as np
    import pandas as pd

    prepared = frame.copy()
    age = pd.to_numeric(prepared["reg_age_months"], errors="coerce")
    prepared["age_band"] = pd.cut(
        age,
        bins=[-np.inf, 24, 60, 120, 240, np.inf],
        right=False,
        labels=["0-23", "24-59", "60-119", "120-239", "240+"],
    ).astype("string")
    sic_values = prepared["reg_sic_sections"].fillna("unknown").astype(str)
    sic_sets = sic_values.map(lambda value: {part for part in value.split(",") if part})
    for section in "ABCDEFGHIJKLMNOPQRSTU":
        prepared[f"sic_{section}"] = sic_sets.map(
            lambda values, section=section: int(section in values)
        )
    prepared["sic_unknown"] = sic_sets.map(
        lambda values: int(not values or "unknown" in values)
    )
    prepared["sic_multiple"] = sic_sets.map(lambda values: int(len(values - {"unknown"}) > 1))
    for column in _all_feature_columns(spec):
        prepared[f"missing__{column}"] = prepared[column].isna().astype(np.int8)
    for column in (
        *spec["structural"]["generated_binary"],
        "has_psc",
        "has_accounts",
        *sum(
            (spec["features"][family].get("binary", []) for family in spec["features"]),
            [],
        ),
    ):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    return prepared


def _feature_definition(spec: dict[str, Any], model_name: str) -> dict[str, list[str]]:
    structural_categorical = list(spec["structural"]["categorical"])
    structural_binary = list(spec["structural"]["generated_binary"])
    all_missing = [f"missing__{column}" for column in _all_feature_columns(spec)]

    def family_definition(family: str) -> dict[str, list[str]]:
        definition = {
            kind: list(spec["features"][family].get(kind, []))
            for kind in ("log1p", "signed_log1p", "binary", "categorical")
        }
        definition["binary"].extend(
            f"missing__{column}" for column in _all_feature_columns(spec, family)
        )
        if family in {"accounts", "psc"}:
            definition["binary"].append(f"has_{family}")
        return definition

    definition = {
        "log1p": [],
        "signed_log1p": [],
        "binary": [],
        "categorical": [],
    }
    if model_name == "missingness_only":
        definition["binary"] = ["has_psc", "has_accounts", *all_missing]
    else:
        definition["categorical"].extend(structural_categorical)
        definition["binary"].extend(structural_binary)
        if model_name == "structural_missingness":
            definition["binary"].extend(["has_psc", "has_accounts", *all_missing])
        elif model_name in {"register", "accounts", "psc"}:
            family = family_definition(model_name)
            for kind, columns in family.items():
                definition[kind].extend(columns)
        elif model_name == "combined":
            for family_name in spec["features"]:
                family = family_definition(family_name)
                for kind, columns in family.items():
                    definition[kind].extend(columns)
        elif model_name != "structural":
            raise ValueError(f"unknown model name: {model_name}")
    for kind in definition:
        definition[kind] = list(dict.fromkeys(definition[kind]))
    predictors = sum(definition.values(), [])
    validate_predictor_whitelist(predictors, spec)
    return definition


def _build_pipeline(spec: dict[str, Any], model_name: str, c_value: float):
    import numpy as np
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

    definition = _feature_definition(spec, model_name)
    transformers = []
    if definition["log1p"]:
        transformers.append(
            (
                "log1p",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                        (
                            "transform",
                            FunctionTransformer(
                                lambda values: np.log1p(np.maximum(values, 0)),
                                feature_names_out="one-to-one",
                            ),
                        ),
                        ("scale", StandardScaler(with_mean=False)),
                    ]
                ),
                definition["log1p"],
            )
        )
    if definition["signed_log1p"]:
        transformers.append(
            (
                "signed_log1p",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                        (
                            "transform",
                            FunctionTransformer(
                                lambda values: np.sign(values) * np.log1p(np.abs(values)),
                                feature_names_out="one-to-one",
                            ),
                        ),
                        ("scale", StandardScaler(with_mean=False)),
                    ]
                ),
                definition["signed_log1p"],
            )
        )
    if definition["binary"]:
        transformers.append(
            (
                "binary",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(strategy="most_frequent", keep_empty_features=True),
                        ),
                        ("scale", StandardScaler(with_mean=False)),
                    ]
                ),
                definition["binary"],
            )
        )
    if definition["categorical"]:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="constant",
                                fill_value="__MISSING__",
                                keep_empty_features=True,
                            ),
                        ),
                        (
                            "encode",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                min_frequency=spec["modelling"]["categorical_min_frequency"],
                            ),
                        ),
                    ]
                ),
                definition["categorical"],
            )
        )
    preprocessor = ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.3)
    model = LogisticRegression(
        C=c_value,
        solver="saga",
        max_iter=spec["modelling"]["max_iter"],
        random_state=spec["modelling"]["random_seed"],
        tol=1e-4,
    )
    return Pipeline([("preprocess", preprocessor), ("model", model)]), definition


def _weighted_metrics(y_true, probability, weight) -> dict[str, float]:
    import numpy as np
    from scipy.optimize import minimize
    from sklearn.metrics import average_precision_score, log_loss, roc_auc_score

    clipped = np.clip(np.asarray(probability, dtype=float), 1e-8, 1 - 1e-8)
    labels = np.asarray(y_true, dtype=int)
    weights = np.asarray(weight, dtype=float)
    logit = np.log(clipped / (1 - clipped))

    def objective(parameters):
        calibrated = 1 / (1 + np.exp(-(parameters[0] + parameters[1] * logit)))
        return log_loss(labels, calibrated, sample_weight=weights, labels=[0, 1])

    calibration = minimize(objective, np.array([0.0, 1.0]), method="BFGS")
    return {
        "roc_auc": float(roc_auc_score(labels, clipped, sample_weight=weights)),
        "average_precision": float(
            average_precision_score(labels, clipped, sample_weight=weights)
        ),
        "log_loss": float(log_loss(labels, clipped, sample_weight=weights, labels=[0, 1])),
        "brier": float(np.average((labels - clipped) ** 2, weights=weights)),
        "calibration_intercept": float(calibration.x[0]),
        "calibration_slope": float(calibration.x[1]),
    }


def _fit_model(frame, spec: dict[str, Any], model_name: str):
    import numpy as np
    from sklearn.base import clone
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.metrics import log_loss
    from sklearn.model_selection import StratifiedKFold

    definition = _feature_definition(spec, model_name)
    predictors = sum(definition.values(), [])
    train = frame[frame["split"] == "train"].reset_index(drop=True)
    test = frame[frame["split"] == "test"].reset_index(drop=True)
    x_train = train[predictors]
    y_train = train["outcome"].astype(int).to_numpy()
    w_train = train["sample_weight"].astype(float).to_numpy()
    folds = StratifiedKFold(
        n_splits=spec["modelling"]["cv_folds"],
        shuffle=True,
        random_state=spec["modelling"]["random_seed"],
    )
    cv_rows = []
    for c_value in spec["modelling"]["c_grid"]:
        pipeline, _ = _build_pipeline(spec, model_name, c_value)
        losses = []
        for fit_index, validation_index in folds.split(x_train, y_train):
            candidate = clone(pipeline)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=ConvergenceWarning)
                candidate.fit(
                    x_train.iloc[fit_index],
                    y_train[fit_index],
                    model__sample_weight=w_train[fit_index],
                )
            probability = candidate.predict_proba(x_train.iloc[validation_index])[:, 1]
            losses.append(
                log_loss(
                    y_train[validation_index],
                    probability,
                    sample_weight=w_train[validation_index],
                    labels=[0, 1],
                )
            )
        cv_rows.append(
            {"c": float(c_value), "weighted_log_loss": float(np.mean(losses))}
        )
    selected_c = min(cv_rows, key=lambda row: (row["weighted_log_loss"], row["c"]))["c"]
    pipeline, _ = _build_pipeline(spec, model_name, selected_c)
    convergence_warnings = 0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", category=ConvergenceWarning)
        pipeline.fit(x_train, y_train, model__sample_weight=w_train)
        convergence_warnings = sum(
            issubclass(item.category, ConvergenceWarning) for item in caught
        )
    x_test = test[predictors]
    y_test = test["outcome"].astype(int).to_numpy()
    w_test = test["sample_weight"].astype(float).to_numpy()
    probability = pipeline.predict_proba(x_test)[:, 1]
    metrics = _weighted_metrics(y_test, probability, w_test)
    feature_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    coefficients = pipeline.named_steps["model"].coef_[0]
    top_coefficients = sorted(
        (
            {"feature": str(name), "coefficient": float(value)}
            for name, value in zip(feature_names, coefficients, strict=True)
        ),
        key=lambda row: abs(row["coefficient"]),
        reverse=True,
    )[:50]
    result = {
        "model": model_name,
        "predictor_count_before_encoding": len(predictors),
        "encoded_feature_count": len(feature_names),
        "selected_c": selected_c,
        "cv": cv_rows,
        "test_metrics": metrics,
        "convergence_warnings": convergence_warnings,
        "top_coefficients": top_coefficients,
    }
    predictions = {
        "outcome": y_test,
        "weight": w_test,
        "probability": probability,
    }
    return result, predictions


def _paired_bootstrap(reference, combined, replicates: int, seed: int) -> dict[str, Any]:
    import numpy as np

    outcome = reference["outcome"]
    if not np.array_equal(outcome, combined["outcome"]):
        raise RuntimeError("paired model predictions do not share held-out outcomes")
    if not np.array_equal(reference["weight"], combined["weight"]):
        raise RuntimeError("paired model predictions do not share held-out weights")
    by_label = {label: np.flatnonzero(outcome == label) for label in (0, 1)}
    rng = np.random.default_rng(seed)
    deltas = {name: [] for name in ("roc_auc", "average_precision", "log_loss", "brier")}
    for _ in range(replicates):
        indices = np.concatenate(
            [rng.choice(values, size=len(values), replace=True) for values in by_label.values()]
        )
        ref_metrics = _weighted_metrics(
            outcome[indices], reference["probability"][indices], reference["weight"][indices]
        )
        combined_metrics = _weighted_metrics(
            outcome[indices], combined["probability"][indices], combined["weight"][indices]
        )
        deltas["roc_auc"].append(combined_metrics["roc_auc"] - ref_metrics["roc_auc"])
        deltas["average_precision"].append(
            combined_metrics["average_precision"] - ref_metrics["average_precision"]
        )
        deltas["log_loss"].append(ref_metrics["log_loss"] - combined_metrics["log_loss"])
        deltas["brier"].append(ref_metrics["brier"] - combined_metrics["brier"])
    return {
        name: {
            "estimate": float(np.mean(values)),
            "ci95": [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))],
            "orientation": (
                "combined minus structural+missingness"
                if name in {"roc_auc", "average_precision"}
                else "structural+missingness minus combined; positive favours combined"
            ),
        }
        for name, values in deltas.items()
    }


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def _binary_effect(adverse_true, adverse_n, comparison_true, comparison_n):
    p1 = _safe_ratio(adverse_true, adverse_n)
    p0 = _safe_ratio(comparison_true, comparison_n)
    if p1 is None or p0 is None:
        return {}
    a = adverse_true + 0.5
    b = adverse_n - adverse_true + 0.5
    c = comparison_true + 0.5
    d = comparison_n - comparison_true + 0.5
    odds_ratio = (a * d) / (b * c)
    se_log_or = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    prevalence_ratio = a / (a + b) / (c / (c + d))
    se_log_pr = math.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    return {
        "adverse_rate": p1,
        "comparison_rate": p0,
        "percentage_point_difference": 100 * (p1 - p0),
        "prevalence_ratio": prevalence_ratio,
        "prevalence_ratio_ci95": [
            math.exp(math.log(prevalence_ratio) - 1.96 * se_log_pr),
            math.exp(math.log(prevalence_ratio) + 1.96 * se_log_pr),
        ],
        "odds_ratio": odds_ratio,
        "odds_ratio_ci95": [
            math.exp(math.log(odds_ratio) - 1.96 * se_log_or),
            math.exp(math.log(odds_ratio) + 1.96 * se_log_or),
        ],
    }


def _describe_primary(con, spec: dict[str, Any]) -> dict[str, Any]:
    feature_columns = _all_feature_columns(spec)
    binary_columns = sum(
        (spec["features"][family].get("binary", []) for family in spec["features"]), []
    )
    numeric_columns = sum(
        (
            spec["features"][family].get("log1p", [])
            + spec["features"][family].get("signed_log1p", [])
            for family in spec["features"]
        ),
        [],
    )
    categorical_columns = [
        "reg_company_type",
        "reg_sic_sections",
        *sum(
            (
                spec["features"][family].get("categorical", [])
                for family in spec["features"]
            ),
            [],
        ),
    ]
    base = "study_source WHERE study_group IN ('recorded_adverse', 'without_recorded_adverse')"
    group_rows = con.sql(
        f"""
        SELECT study_group, count(*) AS companies,
               count(*) FILTER (WHERE has_psc) AS has_psc,
               count(*) FILTER (WHERE has_accounts) AS has_accounts,
               count(*) FILTER (WHERE has_psc AND has_accounts) AS has_both
        FROM {base} GROUP BY study_group ORDER BY study_group
        """
    ).fetchall()
    groups = [
        {
            "study_group": group,
            "companies": int(companies),
            "has_psc": int(has_psc),
            "has_accounts": int(has_accounts),
            "has_both": int(has_both),
        }
        for group, companies, has_psc, has_accounts, has_both in group_rows
    ]
    observed_sql = ", ".join(
        f"count({column}) AS {_sql_literal(column)}" for column in feature_columns
    )
    observed_cursor = con.execute(
        f"SELECT study_group, {observed_sql} FROM {base} GROUP BY study_group"
    )
    observed_names = [item[0] for item in observed_cursor.description]
    observed = {
        row[0]: dict(zip(observed_names[1:], (int(value) for value in row[1:]), strict=True))
        for row in observed_cursor.fetchall()
    }
    binary_sql = ", ".join(
        f"count(*) FILTER (WHERE {column} = TRUE) AS {_sql_literal(column)}"
        for column in binary_columns
    )
    binary_cursor = con.execute(
        f"SELECT study_group, {binary_sql} FROM {base} GROUP BY study_group"
    )
    binary_names = [item[0] for item in binary_cursor.description]
    binary_true = {
        row[0]: dict(zip(binary_names[1:], (int(value) for value in row[1:]), strict=True))
        for row in binary_cursor.fetchall()
    }
    binary_effects = []
    for column in binary_columns:
        adverse_n = observed["recorded_adverse"][column]
        comparison_n = observed["without_recorded_adverse"][column]
        adverse_true = binary_true["recorded_adverse"][column]
        comparison_true = binary_true["without_recorded_adverse"][column]
        binary_effects.append(
            {
                "attribute": column,
                "adverse_observed": adverse_n,
                "adverse_true": adverse_true,
                "comparison_observed": comparison_n,
                "comparison_true": comparison_true,
                **_binary_effect(adverse_true, adverse_n, comparison_true, comparison_n),
            }
        )
    numeric_parts = []
    for column in numeric_columns:
        numeric_parts.extend(
            [
                f"count({column}) AS {_sql_literal(column + '__n')}",
                f"avg({column}) AS {_sql_literal(column + '__mean')}",
                f"stddev_samp({column}) AS {_sql_literal(column + '__sd')}",
                f"quantile_cont({column}, 0.25) AS {_sql_literal(column + '__q25')}",
                f"median({column}) AS {_sql_literal(column + '__median')}",
                f"quantile_cont({column}, 0.75) AS {_sql_literal(column + '__q75')}",
            ]
        )
    numeric_cursor = con.execute(
        f"SELECT study_group, {', '.join(numeric_parts)} FROM {base} GROUP BY study_group"
    )
    numeric_names = [item[0] for item in numeric_cursor.description]
    numeric_by_group = {
        row[0]: dict(zip(numeric_names[1:], row[1:], strict=True))
        for row in numeric_cursor.fetchall()
    }
    numeric_effects = []
    for column in numeric_columns:
        adverse = numeric_by_group["recorded_adverse"]
        comparison = numeric_by_group["without_recorded_adverse"]
        n1, n0 = adverse[f"{column}__n"], comparison[f"{column}__n"]
        mean1, mean0 = adverse[f"{column}__mean"], comparison[f"{column}__mean"]
        sd1, sd0 = adverse[f"{column}__sd"], comparison[f"{column}__sd"]
        pooled = None
        smd = None
        smd_ci = None
        if n1 > 1 and n0 > 1 and sd1 is not None and sd0 is not None:
            pooled = math.sqrt(((n1 - 1) * sd1**2 + (n0 - 1) * sd0**2) / (n1 + n0 - 2))
            if pooled:
                smd = (mean1 - mean0) / pooled
                se = math.sqrt((n1 + n0) / (n1 * n0) + smd**2 / (2 * (n1 + n0 - 2)))
                smd_ci = [smd - 1.96 * se, smd + 1.96 * se]
        numeric_effects.append(
            {
                "attribute": column,
                "adverse": {
                    "observed": int(n1),
                    "mean": mean1,
                    "sd": sd1,
                    "q25": adverse[f"{column}__q25"],
                    "median": adverse[f"{column}__median"],
                    "q75": adverse[f"{column}__q75"],
                },
                "comparison": {
                    "observed": int(n0),
                    "mean": mean0,
                    "sd": sd0,
                    "q25": comparison[f"{column}__q25"],
                    "median": comparison[f"{column}__median"],
                    "q75": comparison[f"{column}__q75"],
                },
                "mean_difference": None if mean1 is None or mean0 is None else mean1 - mean0,
                "standardised_mean_difference": smd,
                "standardised_mean_difference_ci95": smd_ci,
            }
        )
    categorical = []
    for column in categorical_columns:
        rows = con.sql(
            f"""
            SELECT study_group, coalesce(cast({column} AS VARCHAR), '__MISSING__') AS category,
                   count(*) AS companies
            FROM {base}
            GROUP BY study_group, category ORDER BY category, study_group
            """
        ).fetchall()
        counts = [
            {"study_group": group, "category": category, "companies": int(count)}
            for group, category, count in rows
        ]
        categories = sorted({row["category"] for row in counts})
        lookup = {(row["study_group"], row["category"]): row["companies"] for row in counts}
        n1 = sum(lookup.get(("recorded_adverse", category), 0) for category in categories)
        n0 = sum(
            lookup.get(("without_recorded_adverse", category), 0) for category in categories
        )
        total = n1 + n0
        chi_square = 0.0
        if total:
            for category in categories:
                column_total = lookup.get(("recorded_adverse", category), 0) + lookup.get(
                    ("without_recorded_adverse", category), 0
                )
                for group, group_total in (
                    ("recorded_adverse", n1),
                    ("without_recorded_adverse", n0),
                ):
                    expected_count = group_total * column_total / total
                    if expected_count:
                        observed_count = lookup.get((group, category), 0)
                        chi_square += (observed_count - expected_count) ** 2 / expected_count
        categorical.append(
            {
                "attribute": column,
                "cramers_v": math.sqrt(chi_square / total) if total else None,
                "counts": counts,
            }
        )
    return {
        "groups": groups,
        "observed_counts": observed,
        "binary_effects": binary_effects,
        "numeric_effects": numeric_effects,
        "categorical_effects": categorical,
    }


def _weighted_rank_effects(frame, numeric_columns: list[str]) -> dict[str, float | None]:
    import numpy as np
    import pandas as pd

    effects: dict[str, float | None] = {}
    for column in numeric_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        case_values = values[frame["outcome"] == 1].dropna().to_numpy(dtype=float)
        comparison_mask = (frame["outcome"] == 0) & values.notna()
        comparison_values = values[comparison_mask].to_numpy(dtype=float)
        comparison_weights = frame.loc[comparison_mask, "sample_weight"].to_numpy(dtype=float)
        if not len(case_values) or not len(comparison_values):
            effects[column] = None
            continue
        order = np.argsort(comparison_values)
        sorted_values = comparison_values[order]
        sorted_weights = comparison_weights[order]
        cumulative = np.concatenate(([0.0], np.cumsum(sorted_weights)))
        left = np.searchsorted(sorted_values, case_values, side="left")
        right = np.searchsorted(sorted_values, case_values, side="right")
        less = cumulative[left]
        ties = cumulative[right] - cumulative[left]
        superiority = np.mean((less + 0.5 * ties) / cumulative[-1])
        effects[column] = float(2 * superiority - 1)
    return effects


def run_company_comparison(
    spec_path: str | Path,
    *,
    memory_limit_gb: int = 8,
    spill_dir: str | Path = "/tmp/ukcompany-company-comparison-spill",
) -> dict[str, Any]:
    """Run the frozen aggregate-only contemporaneous comparison study."""
    started = time.perf_counter()
    spec = load_study_spec(spec_path)
    if tuple(spec["populations"]) != tuple(POPULATION_FILTERS):
        raise ValueError("population order/filter definitions differ from frozen implementation")
    input_records = verify_study_input(spec)
    con = _connect(memory_limit_gb, str(spill_dir))
    try:
        cohort = _prepare_cohort(con, spec)
        descriptives = _describe_primary(con, spec)
        population_results = {}
        primary_rank_effects = None
        for population in spec["populations"]:
            sampled, sampling = _sample_population(con, spec, population)
            prepared = _prepare_features(sampled, spec)
            if population == "primary":
                numeric_columns = sum(
                    (
                        spec["features"][family].get("log1p", [])
                        + spec["features"][family].get("signed_log1p", [])
                        for family in spec["features"]
                    ),
                    [],
                )
                primary_rank_effects = _weighted_rank_effects(prepared, numeric_columns)
            model_results = {}
            predictions = {}
            for model_name in MODEL_NAMES:
                model_result, model_predictions = _fit_model(prepared, spec, model_name)
                model_results[model_name] = model_result
                predictions[model_name] = model_predictions
            paired = _paired_bootstrap(
                predictions["structural_missingness"],
                predictions["combined"],
                spec["modelling"]["bootstrap_replicates"],
                spec["modelling"]["random_seed"] + list(POPULATION_FILTERS).index(population),
            )
            population_results[population] = {
                "sampling": sampling,
                "models": model_results,
                "paired_combined_vs_structural_missingness": paired,
            }
    finally:
        con.close()
    if primary_rank_effects is not None:
        for row in descriptives["numeric_effects"]:
            row["rank_biserial_effect_weighted_sample"] = primary_rank_effects[row["attribute"]]
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if __import__("sys").platform == "darwin" else peak * 1024
    return {
        "study": "contemporaneous recorded-status company-attribute comparison",
        "study_version": spec["study_version"],
        "aggregate_only": True,
        "not_forecasting": True,
        "code_commit": _git_commit(),
        "spec": {
            "path": str(spec_path),
            "sha256": study_spec_sha256(spec),
            "contents": spec,
        },
        "inputs": input_records,
        "cohort": cohort,
        "descriptives": descriptives,
        "populations": population_results,
        "runtime": {
            "seconds": time.perf_counter() - started,
            "peak_rss_bytes": peak_bytes,
        },
    }


def write_aggregate_json(report: dict[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return destination
