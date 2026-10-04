# Snapshot per-company feature table

One row per live company in the monthly Companies House basic-company bulk file, carrying
status/type/age, SIC structure and flags, previous-name count, charge counts,
accounts/confirmation-statement state, and registered-office concentration. Where a feature also
exists in `ukcompany.derive.derive_profile` the **same helper is reused** — `_months_between`
for age and `ukcompany.validation.labels.sic_section_from_code` for the SIC section — so there is
one definition, shared with the API path. Built by `ukcompany.snapshot.features`
(CLI: `ukcompany-snapshot features`).

**The reference date is the snapshot date** (month-01). Every age and "overdue" feature is
computed against it, never against today.

## How it is built

```
ukcompany-snapshot refresh  --month YYYY-MM                 # download, verify, prune, load, rows
ukcompany-snapshot features --month YYYY-MM                 # governed tier (default)
ukcompany-snapshot features --month YYYY-MM --no-data-governance   # ungoverned tier
```

The heavy grouping runs in DuckDB; the shared Python helpers are applied over the small distinct
vocabularies (incorporation dates, ~1k SIC codes) and joined back, as in the PSC feature build.
Dates in the bulk file are `DD/MM/YYYY` and are parsed as such.

## Two tiers

| Tier | Flag | Contents |
|---|---|---|
| **governed** (default) | `--data-governance` | every feature **except** `n_companies_same_address`. The written schema is asserted to not contain it. |
| **ungoverned** | `--no-data-governance` | adds `n_companies_same_address` (a per-address count; registered offices are sometimes home addresses, so it says something about a household). |

## Columns

All columns are registered in `FIELD_DOCS` (`src/ukcompany/derive.py`) and the generated
`docs/data-dictionary.md`. Shared-name attributes — `company_status`, `company_type`,
`date_of_creation`, `age_months`, `n_previous_names`, `accounts_overdue` — carry the same
definitions as the API path; only the **source** differs (the bulk file, DD/MM/YYYY dates, and
the snapshot date as the age/overdue reference). The snapshot-new attributes
(`sic_sections`, `n_sic_codes`, the three SIC flags, the four charge counts, `accounts_category`,
`confirmation_statement_overdue`, `accounts_never_filed`, `n_companies_same_postcode`,
`n_companies_same_address`) are documented in `FIELD_DOCS` directly.

### SIC flags and the n.e.c. list

Three **separate** flags, each true if any of the company's up-to-four SIC codes matches:
`flag_dormant_sic` (99999, "Dormant Company"), `flag_non_trading_sic` (74990, "Non-trading
company"), and `flag_nec_sic` ("not elsewhere classified"). The n.e.c. list is a single constant
`NEC_SIC_CODES` in `ukcompany.snapshot.features`, enumerated from the SIC-2007 condensed-list
descriptions ending "n.e.c." as published in the bulk file (the file ships the ONS descriptions
verbatim). Source: ONS UK SIC 2007 condensed list. A malformed 4-digit variant (`9305`) seen in
the 2026-08 data is excluded as not a valid 5-digit code. Share of companies (2026-08):
`flag_nec_sic` 16.79%, `flag_dormant_sic` 1.98%, `flag_non_trading_sic` 0.74%.

### Previous names

`n_previous_names` counts non-empty `PreviousName_1..10.CompanyName`. The bulk file holds **at
most 10** previous names, so a count of 10 means **"10 or more"**.

### "Never filed" accounts

`accounts_never_filed` = accounts category is `NO ACCOUNTS FILED` **and** the snapshot date is
past the first-accounts deadline (incorporation + 21 months). **The 21-month private-company
deadline is NOT VERIFIED** against current CH guidance in this build (no network) — treat it as
inferred. It does not distinguish company types with different deadlines. 3.97% of companies
(2026-08) qualify; many `NO ACCOUNTS FILED` companies are simply not yet past their first
deadline.

### Registered-office concentration and address normalisation

`n_companies_same_postcode` (governed) and `n_companies_same_address` (ungoverned) count live
companies sharing the postcode / normalised address in this snapshot. Normalisation is **one
function**, `normalise_address(postcode, line1, loose=…)`: upper-case, collapse whitespace, and
remove punctuation (common punctuation by default; all non-alphanumerics under `loose`), over
postcode + first address line. The counts are **insensitive** to it: 2,634,652 distinct addresses
under the standard rule vs 2,633,802 under loose (a 0.03% shift) in 2026-08. The upper tail is
formation agents / virtual offices (the largest postcode alone is ~1.5% of all companies); see
`docs/snapshot-distributions-2026-08.md`. No address is published.

## Validation

- **Parity vs the API path** — `scripts/snapshot_parity_check.py`,
  `docs/snapshot-parity-2026-08.md`. On the 714 companies in both the API cache and the snapshot:
  `has_charges` 100%, `date_of_creation`/`age_months` 99.3%, the rest 96–97.5%. All disagreements
  are the API cache being a few days newer than the snapshot, except the `date_of_creation`
  mismatches, which are **Charitable Incorporated Organisations** — the API omits
  `date_of_creation` for CIOs while the bulk records it (a source field-availability difference,
  not a parsing error). `company_status`/`company_type` use different vocabularies (register
  category vs API slug) and are shown as cross-tabs, not equality-compared.
- **Distributions** — `scripts/snapshot_distributions.py`,
  `docs/snapshot-distributions-2026-08.md`: fill rates, concentration percentiles + banded
  company counts, and SIC/accounts flag shares.

## Caveats

- One row is dropped by the DuckDB reader's `ignore_errors` (a malformed line); the manifest /
  `refresh` row-count uses the same Polars method as the manifest and reconciles exactly
  (5,695,466 for 2026-08).
- `company_status`/`company_type` vocabularies differ from the API (register category text vs
  API slug); the snapshot carries the register's text verbatim.
- The snapshot excludes dissolved companies (they are off the register), so this is a live-company
  table.
- Retention (`ukcompany.snapshot.archive`) keeps the first snapshot of each month plus the latest;
  at the monthly publication cadence this keeps every month (nothing to prune).
