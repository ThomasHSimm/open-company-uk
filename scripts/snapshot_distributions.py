"""Task 4: coverage and distributions for the snapshot feature table.

Reports, aggregates only (no address-level list):
  * fill rate per feature (share of companies with a non-null value),
  * registered-office concentration as percentiles and as banded company counts,
  * the share of companies for each SIC flag and each accounts/confirmation flag.

Run against the UNGOVERNED tier so both the postcode and the exact-address concentration can be
summarised; neither address is listed, only distributions.

Usage:
    python scripts/snapshot_distributions.py \
        --features data/snapshot/2026-08/features-ungoverned/snapshot_company_features.parquet \
        --snapshot-date 2026-08-01 --out docs/snapshot-distributions-2026-08.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ukcompany.psc.loader import _connect, _sql_literal

# Concentration bands (number of companies sharing a postcode / address).
BANDS = (
    ("1", "= 1"),
    ("2-5", "BETWEEN 2 AND 5"),
    ("6-20", "BETWEEN 6 AND 20"),
    ("21-100", "BETWEEN 21 AND 100"),
    ("101-1000", "BETWEEN 101 AND 1000"),
    ("1001+", ">= 1001"),
)
FLAG_COLS = (
    "flag_dormant_sic", "flag_non_trading_sic", "flag_nec_sic",
    "accounts_overdue", "confirmation_statement_overdue", "accounts_never_filed",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--features", required=True)
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    con = _connect(8)
    feat = f"read_parquet({_sql_literal(args.features)})"
    try:
        columns = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM {feat}").fetchall()]
        total = con.sql(f"SELECT COUNT(*) FROM {feat}").fetchone()[0]

        fill = con.sql(
            "SELECT " + ", ".join(f"COUNT({c}) AS {c}" for c in columns) + f" FROM {feat}"
        ).fetchone()
        fill_rates = dict(zip(columns, fill, strict=True))

        flag_shares = con.sql(
            "SELECT " + ", ".join(
                f"COUNT(*) FILTER (WHERE {c}) AS {c}" for c in FLAG_COLS
            ) + f" FROM {feat}"
        ).fetchone()
        flag_counts = dict(zip(FLAG_COLS, flag_shares, strict=True))

        def concentration(col):
            pcts = con.sql(
                f"SELECT quantile_cont({col}, 0.5), quantile_cont({col}, 0.9), "
                f"quantile_cont({col}, 0.99), quantile_cont({col}, 0.999), max({col}) "
                f"FROM {feat} WHERE {col} > 0"
            ).fetchone()
            band_counts = []
            for label, cond in BANDS:
                n = con.sql(
                    f"SELECT COUNT(*) FROM {feat} WHERE {col} {cond}"
                ).fetchone()[0]
                band_counts.append((label, n))
            return pcts, band_counts

        pc_pcts, pc_bands = concentration("n_companies_same_postcode")
        has_addr = "n_companies_same_address" in columns
        if has_addr:
            ad_pcts, ad_bands = concentration("n_companies_same_address")
    finally:
        con.close()

    lines = [
        f"# Snapshot feature distributions ({args.snapshot_date})",
        "",
        f"Companies: **{total:,}**. Aggregates only; no address is listed.",
        "",
        "## Fill rate per feature",
        "",
        "| feature | non-null | fill % |",
        "|---|---:|---:|",
    ]
    for c in columns:
        n = fill_rates[c]
        lines.append(f"| `{c}` | {n:,} | {100.0 * n / total:.2f}% |")

    lines += ["", "## SIC and accounts/confirmation flag shares", "",
              "| flag | companies | share |", "|---|---:|---:|"]
    for c in FLAG_COLS:
        n = flag_counts[c]
        lines.append(f"| `{c}` | {n:,} | {100.0 * n / total:.2f}% |")

    def _pct_table(name, pcts):
        return [
            "", f"### {name} — percentiles (over companies with a count > 0)", "",
            "| p50 | p90 | p99 | p99.9 | max |", "|---:|---:|---:|---:|---:|",
            f"| {pcts[0]:.0f} | {pcts[1]:.0f} | {pcts[2]:.0f} | {pcts[3]:.0f} | {pcts[4]:,} |",
        ]

    def _band_table(bands):
        out = ["", "| companies sharing | count | share |", "|---|---:|---:|"]
        for label, n in bands:
            out.append(f"| {label} | {n:,} | {100.0 * n / total:.2f}% |")
        return out

    lines += [
        "", "## Registered-office concentration", "",
        "> The upper tail is company-formation agents and virtual-office providers, whose "
        "registered office hosts tens of thousands of companies; the single largest postcode "
        "alone exceeds 1% of all companies, which is why the postcode p99/p99.9/max coincide. "
        "No address is named here.",
    ]
    lines += ["", "### By postcode (governed)"]
    lines += _pct_table("Postcode", pc_pcts)
    lines += _band_table(pc_bands)
    if has_addr:
        lines += ["", "### By exact normalised address (ungoverned)"]
        lines += _pct_table("Address", ad_pcts)
        lines += _band_table(ad_bands)
    lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"distributions: {total:,} companies; wrote {args.out}")
    print(f"  postcode concentration p99/max: {pc_pcts[2]:.0f}/{pc_pcts[4]:,}")
    if has_addr:
        print(f"  address concentration p99/max: {ad_pcts[2]:.0f}/{ad_pcts[4]:,}")
    for c in FLAG_COLS:
        print(f"  {c}: {100.0 * flag_counts[c] / total:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
