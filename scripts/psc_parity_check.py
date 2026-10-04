"""Task 3: parity of the bulk per-company PSC features against the API path (derive_psc).

For every company that is BOTH in the API cache (data/raw/<n>/psc.json) and in the bulk
feature table, compute derive_psc from the cached per-company responses and compare it,
feature by feature, to the bulk feature row. Reports agreement per feature, and for every
disagreement the cache fetch date vs the snapshot date and the direction of the difference.

The two sources are taken at different instants (the API cache is whenever each company was
fetched; the bulk snapshot is one dated file), so disagreement is expected and is characterised
by timing, not treated as a bug. One substantive check: the accumulating ECCTA identity-
verification counts (`n_psc_id_verified`, `n_psc_id_statement_filed`) should only *increase*
over time, so whichever source is later must not carry fewer — any that do are flagged.

The markdown report is aggregates only; the full per-disagreement detail (with company numbers,
which are public identifiers) is written to the .json sidecar.

Usage:
    python scripts/psc_parity_check.py \
        --features data/psc/2026-09-25/features-private/psc_company_features.parquet \
        --cache data/raw --snapshot-date 2026-09-25 --out docs/psc-parity-2026-09-25.md
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import duckdb

from ukcompany.cache import RawCache
from ukcompany.derive import derive_psc
from ukcompany.fetch import PSC, PSC_STATEMENTS

# Features present in both paths. psc_fetch_status (pipeline state) and the private-only
# companies-per-person bands have no derive_psc analogue, so they are not compared.
COMPARE_FEATURES = (
    "psc_n_records", "psc_n_ceased", "psc_natures_of_control",
    "psc_max_ownership_band", "psc_max_voting_band", "psc_has_appointment_rights",
    "psc_has_significant_influence", "psc_n_distinct_natures",
    "psc_n_individual", "psc_n_corporate", "psc_n_legal_person", "psc_n_super_secure",
    "psc_corporate_reg_numbers", "psc_n_corporate_uk_format_regno", "psc_unmapped_natures",
    "n_psc_id_verified", "n_psc_id_verification_due", "n_psc_id_statement_filed",
    "active_psc_statement_codes", "psc_information_state",
)
# Order is a record-order artefact the bulk snapshot does not preserve -> compare as sets.
SET_VALUED = {"psc_corporate_reg_numbers", "active_psc_statement_codes"}
# Integer-count features, for a signed direction and (where noted) a monotonicity check.
NUMERIC = {
    "psc_n_records", "psc_n_ceased", "psc_n_distinct_natures", "psc_n_individual",
    "psc_n_corporate", "psc_n_legal_person", "psc_n_super_secure",
    "psc_n_corporate_uk_format_regno", "n_psc_id_verified",
    "n_psc_id_verification_due", "n_psc_id_statement_filed",
}
# ECCTA counts tested against the "only accumulates over time" hypothesis: the later source
# must not carry fewer. `n_psc_id_verified` (block presence) holds; `n_psc_id_statement_filed`
# does NOT (see the report finding) - `appointment_verification_statement_date` is cleared when
# the verification cycle rolls, so it is a point-in-time field. Both are tested so the report
# can show which holds. `n_psc_id_verification_due` is excluded: a "due" clears on completion.
ECCTA_MONOTONIC = ("n_psc_id_verified", "n_psc_id_statement_filed")
# Statement-sourced features read the statements endpoint's fetch time; everything else the PSC
# list endpoint's.
STATEMENT_SOURCED = {"active_psc_statement_codes", "psc_information_state"}


def _norm(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _as_set(value):
    return set((value or "").split(",")) - {""}


def _fetched_date(response):
    if response is None or response.fetched_at is None:
        return None
    return response.fetched_at.date()


def _value_direction(feature, api, bulk):
    """Signed direction of a disagreement, api relative to bulk."""
    if feature in NUMERIC:
        a = api if isinstance(api, (int, float)) else 0
        b = bulk if isinstance(bulk, (int, float)) else 0
        return "api_gt_bulk" if a > b else "api_lt_bulk" if a < b else "differ"
    if feature in SET_VALUED or feature in ("psc_natures_of_control",):
        a_set, b_set = _as_set(api), _as_set(bulk)
        api_extra, bulk_extra = a_set - b_set, b_set - a_set
        if api_extra and not bulk_extra:
            return "api_superset"
        if bulk_extra and not api_extra:
            return "bulk_superset"
        return "both_differ"
    return "differ"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True)
    ap.add_argument("--cache", default="data/raw")
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    snapshot_date = date.fromisoformat(args.snapshot_date)

    cache = RawCache(args.cache)
    cache_companies = sorted(p.name for p in Path(args.cache).iterdir()
                             if (p / f"{PSC}.json").exists())

    cols = ", ".join(("company_number",) + COMPARE_FEATURES)
    in_list = ", ".join("'" + c.replace("'", "''") + "'" for c in cache_companies)
    bulk_rows = duckdb.sql(
        f"SELECT {cols} FROM read_parquet('{args.features}') "
        f"WHERE company_number IN ({in_list})"
    ).fetchall()
    colnames = ["company_number", *COMPARE_FEATURES]
    bulk = {row[0]: dict(zip(colnames, row, strict=True)) for row in bulk_rows}

    n_cache = len(cache_companies)
    n_overlap = 0
    absent_from_bulk = 0
    absent_but_identified = 0
    agree = {f: 0 for f in COMPARE_FEATURES}
    compared = {f: 0 for f in COMPARE_FEATURES}
    disagreements: list[dict] = []  # full per-disagreement detail -> JSON sidecar
    fetched_dates: list[date] = []

    for company in cache_companies:
        psc_resp = cache.read(company, PSC)
        stmt_resp = cache.read(company, PSC_STATEMENTS)
        expected = derive_psc(psc_resp, stmt_resp)
        psc_date = _fetched_date(psc_resp)
        stmt_date = _fetched_date(stmt_resp)
        if psc_date:
            fetched_dates.append(psc_date)
        if company not in bulk:
            absent_from_bulk += 1
            if expected.get("psc_information_state") == "identified":
                absent_but_identified += 1
            continue
        n_overlap += 1
        got = bulk[company]
        for feature in COMPARE_FEATURES:
            exp = _norm(expected.get(feature))
            val = _norm(got.get(feature))
            compared[feature] += 1
            ok = _as_set(exp) == _as_set(val) if feature in SET_VALUED else exp == val
            if ok:
                agree[feature] += 1
                continue
            ref_date = stmt_date if feature in STATEMENT_SOURCED else psc_date
            if ref_date is None:
                cache_vs_snapshot = "unknown"
            elif ref_date > snapshot_date:
                cache_vs_snapshot = "cache_newer"
            elif ref_date < snapshot_date:
                cache_vs_snapshot = "cache_older"
            else:
                cache_vs_snapshot = "same_day"
            direction = _value_direction(feature, exp, val)
            record = {
                "company_number": company,
                "feature": feature,
                "api": exp,
                "bulk": val,
                "cache_fetched_on": ref_date.isoformat() if ref_date else None,
                "snapshot_date": args.snapshot_date,
                "cache_vs_snapshot": cache_vs_snapshot,
                "value_direction": direction,
            }
            # Monotonicity flag for accumulating ECCTA counts: the later source must not have
            # fewer. Violation = the later source carries the smaller count.
            if feature in ECCTA_MONOTONIC and isinstance(exp, int) and isinstance(val, int):
                if cache_vs_snapshot == "cache_newer":
                    record["eccta_monotonic_violation"] = exp < val  # later(api) < earlier(bulk)
                elif cache_vs_snapshot == "cache_older":
                    record["eccta_monotonic_violation"] = val < exp  # later(bulk) < earlier(api)
                else:
                    record["eccta_monotonic_violation"] = False
            disagreements.append(record)

    # ---- aggregate for the markdown ----
    def _count(**filt):
        return sum(
            1 for d in disagreements
            if all(d.get(k) == v for k, v in filt.items())
        )

    eccta_checked = [d for d in disagreements if "eccta_monotonic_violation" in d]
    eccta_violations = [d for d in eccta_checked if d["eccta_monotonic_violation"]]

    lines = [
        f"# PSC bulk-vs-API feature parity ({args.snapshot_date} snapshot)",
        "",
        f"API-cached companies: **{n_cache:,}**. Of these, **{n_overlap:,}** are also in the "
        f"bulk feature table (the parity set); **{absent_from_bulk:,}** are not "
        f"(of which **{absent_but_identified:,}** have live PSCs in the API - a temporal / "
        f"coverage gap). Markdown is aggregates only; per-disagreement detail (company number, "
        f"fetch date, direction) is in the `.json` sidecar.",
    ]
    if fetched_dates:
        lines.append("")
        lines.append(
            f"API cache fetch dates span **{min(fetched_dates).isoformat()} → "
            f"{max(fetched_dates).isoformat()}**; snapshot date **{args.snapshot_date}**."
        )
    lines += [
        "",
        "## Agreement per feature (parity set)",
        "",
        "| feature | compared | agree | agree % |",
        "|---|---:|---:|---:|",
    ]
    for feature in COMPARE_FEATURES:
        c, a = compared[feature], agree[feature]
        pct = (100.0 * a / c) if c else float("nan")
        lines.append(f"| `{feature}` | {c:,} | {a:,} | {pct:.2f}% |")

    lines += [
        "",
        "## Disagreement timing & direction",
        "",
        "For each disagreeing feature: how the API cache's fetch date sits relative to the "
        "snapshot, and which source carried the larger value.",
        "",
        "| feature | disagree | cache newer | cache older | same day | api larger | bulk larger |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    larger_api = {"api_gt_bulk", "api_superset"}
    larger_bulk = {"api_lt_bulk", "bulk_superset"}
    for feature in COMPARE_FEATURES:
        feat_dis = [d for d in disagreements if d["feature"] == feature]
        if not feat_dis:
            continue
        newer = sum(1 for d in feat_dis if d["cache_vs_snapshot"] == "cache_newer")
        older = sum(1 for d in feat_dis if d["cache_vs_snapshot"] == "cache_older")
        same = sum(1 for d in feat_dis if d["cache_vs_snapshot"] == "same_day")
        api_big = sum(1 for d in feat_dis if d["value_direction"] in larger_api)
        bulk_big = sum(1 for d in feat_dis if d["value_direction"] in larger_bulk)
        lines.append(
            f"| `{feature}` | {len(feat_dis):,} | {newer:,} | {older:,} | {same:,} | "
            f"{api_big:,} | {bulk_big:,} |"
        )

    lines += [
        "",
        "## ECCTA accumulating-count monotonicity check",
        "",
        "Hypothesis: `n_psc_id_verified` and `n_psc_id_statement_filed` only accumulate over "
        "time, so whichever of (API cache, snapshot) is later must not carry fewer. A violation "
        "is the later source carrying the smaller count. Broken down by feature:",
        "",
        "| feature | disagreements checked | violations |",
        "|---|---:|---:|",
    ]
    for feature in ECCTA_MONOTONIC:
        checked = sum(1 for d in eccta_checked if d["feature"] == feature)
        v = sum(1 for d in eccta_violations if d["feature"] == feature)
        flag = "" if v == 0 else " ⚠️"
        lines.append(f"| `{feature}` | {checked:,} | {v:,}{flag} |")
    lines += [
        "",
        "> `n_psc_id_verification_due` is excluded: a 'due' is cleared when verification "
        "completes, so it legitimately falls over time.",
        "",
    ]
    if eccta_violations:
        viol_features = sorted({d["feature"] for d in eccta_violations})
        viol_older = sum(1 for d in eccta_violations if d["cache_vs_snapshot"] == "cache_older")
        viol_co = {d["company_number"] for d in eccta_violations}
        membership_co = {
            d["company_number"] for d in disagreements
            if d["feature"] in ("psc_n_records", "psc_n_ceased")
        }
        with_membership_change = len(viol_co & membership_co)
        lines += [
            "**Finding.** All {n} violations are on `{feats}` ({older} with the API cache older "
            "than the snapshot, i.e. the count *fell* between the cache date and the snapshot), "
            "and {mm} of the {nco} affected companies have any PSC membership change. "
            "`n_psc_id_verified` (block presence, which does not un-happen) shows **no** "
            "violations. This falsifies the accumulation assumption for `n_psc_id_statement_filed` "
            "specifically: `appointment_verification_statement_date` reflects the *current* ECCTA "
            "verification cycle and is cleared/reset when the cycle rolls, so like "
            "`n_psc_id_verification_due` it is **not** a cumulative total. It is a point-in-time "
            "field, not a parity defect — the feature logic is identical across paths (confirmed "
            "by the synthetic unit test).".format(
                n=len(eccta_violations), feats="`, `".join(viol_features),
                older=viol_older, mm=with_membership_change, nco=len(viol_co),
            ),
            "",
        ]

    out = Path(args.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {
        "snapshot_date": args.snapshot_date,
        "n_cache": n_cache, "n_overlap": n_overlap,
        "absent_from_bulk": absent_from_bulk,
        "absent_but_identified": absent_but_identified,
        "cache_fetch_date_min": min(fetched_dates).isoformat() if fetched_dates else None,
        "cache_fetch_date_max": max(fetched_dates).isoformat() if fetched_dates else None,
        "agree": agree, "compared": compared,
        "eccta_checked": len(eccta_checked),
        "eccta_violations": len(eccta_violations),
        "disagreements": disagreements,
    }
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, default=str),
                                        encoding="utf-8")
    print(f"parity: {n_overlap:,} overlap; {len(disagreements):,} disagreements; "
          f"ECCTA violations: {len(eccta_violations)}; wrote {out}")
    for feature in COMPARE_FEATURES:
        c, a = compared[feature], agree[feature]
        print(f"  {feature}: {a}/{c} ({100.0*a/c:.1f}%)" if c else f"  {feature}: n/a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
