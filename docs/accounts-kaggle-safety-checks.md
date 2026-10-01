# Kaggle staging safety checks (Task 6)

Run before printing the upload commands. All checks passed.

## WIDE schema — personal data confirmation

Full schema of `accounts-wide-as_first_reported.parquet` (identical column set to
`accounts-wide-latest.parquet`):

`company` (string), `period_end` (string), `Equity`, `NetCurrentAssetsLiabilities`,
`CurrentAssets`, `Creditors`, `CashBankOnHand`, `Debtors`, `PropertyPlantEquipment`,
`TotalAssetsLessCurrentLiabilities`, `AverageNumberEmployeesDuringPeriod` (all `DOUBLE`),
`equity_share_capital`, `equity_retained_earnings`, `creditors_within_one_year`,
`creditors_after_one_year` (all `DOUBLE`), `employees_unit_anomaly` (`INTEGER`),
`n_concepts_present`, `n_source_filings`, `row_available_yyyymm` (all `BIGINT`).

19 columns total: company number, two dates, nine financial totals plus four dimensional
members, one QA flag, and three row-summary counters. No name, address, or free-text field
of any kind. Confirms Task 6's requirement directly from the schema, not by inference.

## Automated staging guard

`scripts/kaggle_staging_guard.py kaggle kaggle-long` — scans every Parquet file in both
folders. For LONG-shaped files (have `concept`/`fact_kind` columns): fails on any numeric
fact whose concept is in the 95-concept denylist, or any non-numeric fact whose concept is
outside the 17-concept allowlist. For WIDE-shaped files (no `concept` column): fails if any
column name is itself a denylisted concept, or matches an independently-derived
person-related name pattern (`director|officer|keymanagement|related.?party|remuneration|
trustee`) not already accounted for as one of the known WIDE housekeeping columns — this
check is deliberately independent of the denylist itself, so a mistake in the list, not just
in applying it, still has a chance of being caught. Regression-tested
(`tests/test_kaggle_staging_guard.py`, 7 tests) against both a clean case and six synthetic
violation cases, so the guard is proven to actually fail on real violations, not just to
trivially pass.

**Result: passed for both `kaggle/` and `kaggle-long/` as staged.**

## Stale files

The prior-chapter `data/accounts/accounts-wide.parquet` and
`accounts-wide-provenance.parquet` (2026-09-21, before the Creditors maturity columns and
employee cut-off existed) were moved to `data/accounts/_stale/` before this chapter's rebuild
and were never staged into `kaggle/`. `kaggle/`'s WIDE and provenance files were copied
directly from the freshly rebuilt `data/accounts/accounts-wide-{mode}.parquet` outputs
(see `docs/accounts-wide-rebuild-verification.md`), so there is no path by which a stale file
could have been staged.

## Private/public LONG split

Documented in `docs/accounts-limitations.md` (this chapter's update) and in
`kaggle-long/README.md`: the local full LONG archive (`data/accounts/long/`) contains
personal data from the all-fact capture — names, the signing director, addresses, director
loans and remuneration — and is kept private, never published. `kaggle-long/` applies the
maintainer-approved allowlist/denylist (`docs/accounts-public-long-concepts.md`) as a
**filter**, not an in-place redaction, over the same source Parquets. The Open Government
Licence does not cover personal data, which is part of why this split exists rather than
publishing the all-fact capture directly.
