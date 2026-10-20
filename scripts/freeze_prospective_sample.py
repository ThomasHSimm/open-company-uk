"""Freeze the prospective-study sample from the governed join baseline.

One-off, deterministic, reproducible from the committed join plus a fixed seed.
It draws a stratified sample of companies whose later Companies House API state
(profile + /insolvency) will be fetched at the study horizons, writes the sample
to a PRIVATE, gitignored CSV (company numbers never enter the repo), and prints
the sha256 of the CSV and its sidecar for recording in docs/prospective-study-plan.md
and docs/AUDIT.md.

Design (v2 — risk-stratified for incident prediction):
  The target is *incident* adverse insolvency: a company entering liquidation
  (non-solvent) / administration / receivership / voluntary arrangement within a
  horizon, having NOT already been in such a process at baseline. So the budget is
  concentrated where incident events actually occur. Strata A (live insolvency
  process) and B (liquidation) are already-in-insolvency at baseline; they cannot
  contribute incident events and are kept only as SMALL DESCRIPTIVE samples (A: to
  describe how in-process companies progress; B: to validate the members'- vs
  creditors'-voluntary-liquidation case-type split). The rest of the budget goes
  to the at-risk active population, sub-stratified by baseline compliance markers
  whose adverse-transition rate was measured on the Aug-2026 -> Oct-2026 register
  snapshots (annualised, see RATE_ANN):

    D1  accounts overdue                              5.40 %/yr  (11x the base)
    D2  no accounts-overdue, confirmation stmt overdue 0.83 %/yr
    D3  no overdue flags, charges outstanding          0.75 %/yr
    D4  no marker (the clean-active base)              0.35 %/yr
    C   active - proposal to strike off                1.13 %/yr (also the
                                                        dissolution-outcome pool)

  High-rate small cells are sampled heavily (D1), the base cell keeps a large
  anchor sample (D4) so population-weighted metrics stay estimable, and every cell
  has a KNOWN inclusion probability so sampling_weight = population / sampled
  recovers the true population prevalence for average precision at the base rate.

Each company's row records its cell, raw status, and weight. Nothing here changes
after the freeze: same seed + same join => identical sample.

Resource note: reads the ~0.2 GB governed join parquet; peak memory well under
2 GB, runtime a few seconds. Not a heavy run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl

JOIN_PATH = "data/join/v1-internal-202609/governed/joined_company_features.parquet"
OUT_CSV = "data/prospective/study-sample.csv"
OUT_SIDECAR = "data/prospective/study-sample.strata.json"
SEED = 20260912  # baseline reference month T = 2026-09; fixed once, never changed.

# Baseline statuses that are a live insolvency process at baseline (stratum A).
LIVE_PROCESS_STATUSES = {
    "in administration",
    "in administration/administrative receiver",
    "in administration/receiver manager",
    "administration order",
    "administrative receiver",
    "receivership",
    "live but receiver manager on at least one charge",
    "receiver manager / administrative receiver",
    "voluntary arrangement",
    "voluntary arrangement / receiver manager",
    "voluntary arrangement / administrative receiver",
}
LIQUIDATION_STATUS = "liquidation"
STRIKE_OFF_STATUS = "active - proposal to strike off"
ACTIVE_STATUS = "active"

# Measured annualised adverse-insolvency transition rate per cell, from the
# Aug-2026 -> Oct-2026 governed register snapshots (x6 of the two-month rate).
# Used only to report expected positives; the sampling itself does not depend on
# these numbers. A and B are prevalent-at-baseline: no incident rate.
RATE_ANN = {
    "A_live_process": None,
    "B_liquidation": None,
    "C_strike_off_proposal": 0.01129,
    "D1_accounts_overdue": 0.05403,
    "D2_cs_overdue": 0.00827,
    "D3_charges": 0.00750,
    "D4_base": 0.00345,
}

# Target sampled counts per cell (None = take all). Chosen to maximise expected
# incident positives within ~115k companies while keeping the base cell (D4) and
# the mid cells estimable. See docs/prospective-study-plan.md for the rationale.
DEFAULT_TARGETS = {
    "A_live_process": 2_000,
    "B_liquidation": 2_000,
    "C_strike_off_proposal": 20_000,
    "D1_accounts_overdue": 38_000,
    "D2_cs_overdue": 10_000,
    "D3_charges": 10_000,
    "D4_base": 33_000,
}
CELL_ORDER = list(DEFAULT_TARGETS)


def assign_cells(frame: pl.DataFrame) -> pl.DataFrame:
    """Add a disjoint `cell` column. Order of tests defines precedence."""
    status = pl.col("reg_company_status").str.strip_chars().str.to_lowercase()
    acc_od = pl.col("reg_accounts_overdue").fill_null(False)
    cs_od = pl.col("reg_confirmation_statement_overdue").fill_null(False)
    charges = pl.col("reg_n_charges_outstanding").fill_null(0) > 0
    return frame.with_columns(
        pl.when(status.is_in(sorted(LIVE_PROCESS_STATUSES)))
        .then(pl.lit("A_live_process"))
        .when(status == LIQUIDATION_STATUS)
        .then(pl.lit("B_liquidation"))
        .when(status == STRIKE_OFF_STATUS)
        .then(pl.lit("C_strike_off_proposal"))
        .when((status == ACTIVE_STATUS) & acc_od)
        .then(pl.lit("D1_accounts_overdue"))
        .when((status == ACTIVE_STATUS) & cs_od)
        .then(pl.lit("D2_cs_overdue"))
        .when((status == ACTIVE_STATUS) & charges)
        .then(pl.lit("D3_charges"))
        .when(status == ACTIVE_STATUS)
        .then(pl.lit("D4_base"))
        .otherwise(pl.lit("Z_other"))
        .alias("cell")
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_sample(frame: pl.DataFrame, targets: dict[str, int | None], seed: int):
    """Return (sample_df, strata_report). `frame` must already have a `cell` col."""
    parts: list[pl.DataFrame] = []
    strata: dict[str, dict] = {}
    for name in CELL_ORDER:
        pool = frame.filter(pl.col("cell") == name)
        population = pool.height
        target = targets.get(name)
        if target is None or target >= population:
            drawn, n = pool, population
        else:
            drawn, n = pool.sample(n=target, seed=seed, shuffle=True), target
        weight = population / n if n else 0.0
        rate = RATE_ANN.get(name)
        strata[name] = {
            "population": population,
            "sampled": n,
            "weight": weight,
            "annual_adverse_rate": rate,
            "expected_incident_12m": round(n * rate, 1) if rate else None,
        }
        parts.append(drawn.with_columns(pl.lit(weight).alias("sampling_weight")))
    sample = (
        pl.concat(parts)
        .select(["company_number", "cell", "reg_company_status", "sampling_weight"])
        .sort("company_number")
    )
    return sample, strata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--join", default=JOIN_PATH)
    parser.add_argument("--out", default=OUT_CSV)
    parser.add_argument("--sidecar", default=OUT_SIDECAR)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    frame = assign_cells(
        pl.scan_parquet(args.join)
        .select(
            [
                "company_number",
                "reg_company_status",
                "reg_accounts_overdue",
                "reg_confirmation_statement_overdue",
                "reg_n_charges_outstanding",
            ]
        )
        .collect()
    )

    sample, strata = build_sample(frame, DEFAULT_TARGETS, args.seed)

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    sample.write_csv(out_csv)

    expected_12m = sum(
        s["expected_incident_12m"] or 0.0 for s in strata.values()
    )
    sidecar = {
        "design_version": "v2-risk-stratified",
        "join_path": args.join,
        "join_sha256": _sha256(Path(args.join)),
        "seed": args.seed,
        "total_sampled": sample.height,
        "population_total": frame.height,
        "expected_incident_positives_12m": round(expected_12m, 1),
        "rate_source": "Aug-2026 -> Oct-2026 governed register snapshot transition, annualised",
        "strata": strata,
        "weight_semantics": "stratum_population / stratum_sampled; weighted sample reproduces "
        "population prevalence for AP at the true base rate.",
        "incident_numerator_note": "A and B are prevalent insolvency at baseline (descriptive "
        "samples only); incident positives come from C and D*.",
    }
    sidecar_path = Path(args.sidecar)
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {out_csv} ({sample.height:,} companies)")
    print(f"wrote {sidecar_path}")
    print(f"study-sample.csv sha256:          {_sha256(out_csv)}")
    print(f"study-sample.strata.json sha256:  {_sha256(sidecar_path)}")
    print(f"expected incident adverse-insolvency positives at 12m: {expected_12m:,.0f}")
    print("strata:")
    for name in CELL_ORDER:
        s = strata[name]
        exp = s["expected_incident_12m"]
        exp_s = f" exp12m={exp:,.0f}" if exp is not None else " (descriptive)"
        print(
            f"  {name:<24} pop={s['population']:>9,} sampled={s['sampled']:>7,} "
            f"w={s['weight']:>8.2f}{exp_s}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
