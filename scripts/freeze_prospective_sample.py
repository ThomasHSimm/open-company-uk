"""Freeze the prospective-study sample from the governed join baseline.

One-off, deterministic, reproducible from the committed join plus a fixed seed.
It draws a stratified sample of companies whose later Companies House API state
(profile + /insolvency) will be fetched at the study horizons, writes the sample
to a PRIVATE, gitignored CSV (company numbers never enter the repo), and prints
the sha256 of the CSV and its sidecar for recording in docs/prospective-study-plan.md
and docs/AUDIT.md.

Strata (baseline register status in the governed join):
  A  live insolvency process (administration / receivership / voluntary
     arrangement, all spellings)                     -> TAKE ALL (rare, high-signal)
  B  liquidation                                      -> random n_B
  C  active - proposal to strike off                  -> random n_C
  D  active                                           -> random n_D (the bulk)

Each sampled company carries a sampling weight = stratum_population / stratum_n,
so a weighted analysis reproduces the true population prevalence (needed for
average precision at the true base rate). Nothing here changes after the freeze:
re-running with the same seed and the same join reproduces the identical sample.

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

# Baseline statuses that are a live insolvency process still capable of resolving
# within a horizon. Matched case-insensitively against reg_company_status.
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

DEFAULT_N = {"B": 15_000, "C": 30_000, "D": 48_000}


def _stratum(status: str | None) -> str:
    s = (status or "").strip().lower()
    if s in LIVE_PROCESS_STATUSES:
        return "A_live_process"
    if s == LIQUIDATION_STATUS:
        return "B_liquidation"
    if s == STRIKE_OFF_STATUS:
        return "C_strike_off_proposal"
    if s == ACTIVE_STATUS:
        return "D_active"
    return "Z_other"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--join", default=JOIN_PATH)
    parser.add_argument("--out", default=OUT_CSV)
    parser.add_argument("--sidecar", default=OUT_SIDECAR)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--n-liquidation", type=int, default=DEFAULT_N["B"])
    parser.add_argument("--n-strike-off", type=int, default=DEFAULT_N["C"])
    parser.add_argument("--n-active", type=int, default=DEFAULT_N["D"])
    args = parser.parse_args(argv)

    frame = (
        pl.scan_parquet(args.join)
        .select(["company_number", "reg_company_status"])
        .with_columns(
            pl.col("reg_company_status")
            .map_elements(_stratum, return_dtype=pl.String)
            .alias("stratum")
        )
        .collect()
    )

    targets = {
        "A_live_process": None,  # take all
        "B_liquidation": args.n_liquidation,
        "C_strike_off_proposal": args.n_strike_off,
        "D_active": args.n_active,
    }

    parts: list[pl.DataFrame] = []
    strata_report: dict[str, dict] = {}
    for name, target in targets.items():
        pool = frame.filter(pl.col("stratum") == name)
        population = pool.height
        if target is None or target >= population:
            drawn = pool
            n = population
        else:
            drawn = pool.sample(n=target, seed=args.seed, shuffle=True)
            n = target
        weight = population / n if n else 0.0
        strata_report[name] = {"population": population, "sampled": n, "weight": weight}
        parts.append(drawn.with_columns(pl.lit(weight).alias("sampling_weight")))

    sample = pl.concat(parts).select(
        ["company_number", "stratum", "reg_company_status", "sampling_weight"]
    ).sort("company_number")

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    sample.write_csv(out_csv)

    sidecar = {
        "join_path": args.join,
        "join_sha256": _sha256(Path(args.join)),
        "seed": args.seed,
        "total_sampled": sample.height,
        "population_total": frame.height,
        "strata": strata_report,
        "weight_semantics": "stratum_population / stratum_sampled; weighted sample reproduces "
        "population prevalence for AP at the true base rate.",
    }
    sidecar_path = Path(args.sidecar)
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {out_csv} ({sample.height:,} companies)")
    print(f"wrote {sidecar_path}")
    print(f"study-sample.csv sha256:          {_sha256(out_csv)}")
    print(f"study-sample.strata.json sha256:  {_sha256(sidecar_path)}")
    print("strata:")
    for name, info in strata_report.items():
        print(
            f"  {name}: population={info['population']:,} "
            f"sampled={info['sampled']:,} weight={info['weight']:.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
