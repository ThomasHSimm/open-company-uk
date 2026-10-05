# Design: per-company accounts features and the join to the register (Handoff 02, Stage A)

**Status: design for review. No code yet.** This specifies a per-company **accounts feature table
for a reference date T**, built from the published WIDE accounts dataset and its provenance, so it
joins to the register features (Handoff 08) and the PSC features (Handoff 07) on the normalised
company number. Numbers below are measured on the local corpus (WIDE `as_first_reported`,
33,513,017 rows over archive months 2014-01 … 2026-08; register one-file 2026-09-01) at
**T = 2026-08** (the latest archive month), chosen so the nearest register snapshot sits just after
it. Attributes only — no rules, no composite score.

## 0. What "a reference date T" means here

Availability in this product is **month-grained**: a filing becomes public when it appears in a
monthly bulk archive, so T is an **archive-month boundary** (a `YYYYMM`, read as "end of that
month"). Everything point-in-time keys off the archive month, never a calendar day and never
`today()`.

The point-in-time key already exists in WIDE: **`row_available_yyyymm`** = `max(source_year*100 +
source_month)` over the row's cells (`pivot.py:211`), i.e. the archive month by which the whole
(company, period) row was known. In **`as_first_reported`** mode each cell is the value from the
*earliest* archive that reported it, so a row carries no look-ahead, and filtering
`row_available_yyyymm <= T` keeps only rows fully available by T. **`latest`** mode folds in later
restatements and is descriptive-only — never used for point-in-time features.

## 1. Availability

### 1.1 The archive month is recoverable for every cell — confirmed

`accounts-wide-provenance-*.parquet` holds one row per **(company, period_end, wide_column)** with
`source_year`, `source_month` (the archive month the cell's value came from), `source_member` and
`made_up_to_date`. Measured over the `as_first_reported` provenance: **195,937,522 cells, 0 with a
null archive month, 0 with a null `made_up_to_date`.** So the availability date of any WIDE cell is
recoverable exactly, and the row-level `row_available_yyyymm` in WIDE is its max.

### 1.2 A filing in archive month M was received in or before M

The source is Companies House's **"Company accounts data"** bulk product
(`http://download.companieshouse.gov.uk/en_accountsdata.html`), published as **monthly files** (and
daily files) back to 2008 — see `docs/site/guide/sources-map.qmd` ("free daily/monthly ZIPs back to
2008") and the accounts deck (`docs/source-material/companies-house-accounts-deck.md`, "152 monthly
archives"). Each month's file is the aggregation of the accounts documents accepted that month, so a
filing that appears in archive M was accepted by the end of M, and **end-of-M is a safe upper bound
on when it became publicly available.** The pipeline records exactly that archive as
`source_year`/`source_month`.

Empirical support: the lag from period end to archive month is never negative for a valid period
end — the only negatives (1,642 rows) come from corrupt period-end dates (years 0001 / 3020; see
§1.4), not from filings predating their period. **Open item to confirm against CH product docs:**
whether a month-M file is published *during* M (covering M's acceptances) or at the *start* of M
(covering M-1); if the latter, the true availability bound is end-of-M which this design already
uses, so the conclusion is unchanged — but the exact cut-off should be cited precisely before build.

### 1.3 Lag between period end and archive month

Median **9 months** (the private-company filing deadline), p90 **10–12**, p99 **15**, measured over
all plausible rows. Stable by period-end year and by accounts category:

| period-end year | n | p50 | p90 |   | accounts category (register, current) | n | p50 | p90 |
|---|---:|---:|---:|---|---|---:|---:|---:|
| 2025 | 3,379,740 | 9 | 10 |   | MICRO ENTITY | 11,126,319 | 9 | 11 |
| 2024 | 3,687,232 | 9 | 10 |   | TOTAL EXEMPTION FULL | 8,663,574 | 9 | 11 |
| 2023 | 3,344,317 | 9 | 10 |   | DORMANT | 2,877,289 | 9 | 10 |
| 2022 | 3,362,233 | 9 | 11 |   | UNAUDITED ABRIDGED | 1,097,234 | 9 | 11 |
| 2021 | 3,290,910 | 9 | 11 |   | SMALL | 220,843 | 9 | 12 |
| 2020 | 3,090,608 | 9 | 12 |   | FULL / GROUP / MEDIUM | — | 9 | 12 |

(2026 shows p50 ≈ 3 only because only early-2026 period-ends have filed by T.) The lag is
essentially type-independent, so a single availability model applies to all accounts types. Accounts
category is **not** in WIDE or LONG; the by-type split above joins to the register's current
`AccountCategory`, which is a *current* label, not the category at that filing — a caveat, used only
to show the lag is uniform.

### 1.4 Amended / replacement filings

The product ships one monthly file per month; a re-filing for the same period appears as a **later
filing in a later archive**, same (company, period_end). In **`as_first_reported`** the earliest
cell wins, so an amendment is ignored for point-in-time values; in **`latest`** the amendment's
value wins. The two modes disagree on ~9.36% of repeated (company, period, concept) values
(`docs/accounts-restatement-2014-2026.md`) — that gap *is* the restatement/amendment signal.
Within `as_first_reported`, a (company, period) row draws from **more than one filing only 0.0%** of
the time (1,254 of 33,513,017 rows) — i.e. when a later filing adds a concept the first lacked; such
a row's `row_available_yyyymm` is the later archive, so it is correctly treated as available only
then. **Corrupt period ends:** ~1,642 rows have an impossible period_end (year 0001 or 3020); the
build must filter to a plausible window (proposal: `'2010-01-01' ≤ period_end ≤ T-month-end + 1y`).

## 2. Selection rule — which periods feed the features at T

For each company, over WIDE `as_first_reported` rows with `row_available_yyyymm <= T` and a plausible
period_end:

- **latest** = the row with the greatest `period_end` (the most recent period known by T).
- **prior** = the row with the next-greatest `period_end` (for period-over-period changes).

Edge cases:

- **Multiple filings for the same period** — there is one WIDE row per (company, period_end) already
  (the pivot dedupes to one cell per concept), so "latest period" is unambiguous. `n_source_filings`
  flags the rare multi-filing row.
- **Shortened / extended periods** — periods are not assumed 12 months. `prior` is simply the
  previous distinct `period_end`; period length is derivable (prior.period_end → latest.period_end)
  and surfaced as a diagnostic so a change computed across an 18-month long period isn't misread as
  annual.
- **Gap > 18 months between latest and prior period ends** — treat as **no comparable prior**: the
  change features (§4) are null, with a `prior_gap_months` diagnostic, rather than computing a delta
  across a gap that usually means a missed/!combined filing.

## 3. Reconciliation with the register (the accounts parity test)

For each company, the latest available period end at T (WIDE, `as_first_reported`,
`row_available <= T`) vs the register's **`Accounts.LastMadeUpDate`** from the register snapshot
nearest T (one-file 2026-09-01). Of the 5,689,366 register companies:

| bucket | n | % |
|---|---:|---:|
| exact match (WIDE latest period end = register LastMadeUpDate) | 3,915,396 | 68.8% |
| both absent (no WIDE row and no register LastMadeUpDate) | 1,457,025 | 25.6% |
| no WIDE row, but register has a LastMadeUpDate | 228,367 | 4.0% |
| register newer than WIDE latest | 88,434 | 1.6% |
| WIDE newer than register | 94 | 0.0% |

**Among the 4,003,942 companies present in both with a register LastMadeUpDate, 97.79% match
exactly** (same within one month: 97.79%). This is the accounts equivalent of the 07/08 parity
tests. Mismatch categories:

- **no WIDE row (4.0%)** — the register shows a last-made-up date but WIDE has nothing: an XML- or
  PDF-only filing (not iXBRL), a pre-2014 period, or a company type outside the iXBRL product.
- **register newer (1.6%)** — the register's latest period post-dates WIDE's: a filing accepted
  after T, or a latest filing that is XML/PDF-only while an earlier iXBRL one is in WIDE (a timing /
  format difference, not an error).
- **both absent (25.6%)** — overwhelmingly `NO ACCOUNTS FILED` companies (newly incorporated or
  dormant-never-filed); nothing to reconcile.

## 4. Candidate features

All over the **latest** period available by T (and **prior** for changes), `as_first_reported`.
Missingness (fill rate) is the WIDE column coverage from `column-dictionary.md`. Pitfalls:
**dash = nil = 0** (a filed dash is stored as `0`, so e.g. `Equity = 0` is a declared nil, not
missing — `docs/accounts-dash-nil-fix.md`); **use the creditors maturity buckets, not the bare
total** (`Creditors` is only 3.82% populated and unreliable — `docs/accounts-creditors-maturity-
reconciliation.md`); **`employees_unit_anomaly`** marks a GBP-tagged employee value but never alters
it (`docs/accounts-employee-unit-cutoff.md`); **scale and sign** are already normalised in
extraction.

| feature | formula | source columns | expected missingness | pitfalls |
|---|---|---|---|---|
| `negative_equity` | `Equity < 0` | `Equity` | Equity ~75.7% populated | dash=nil (0 ≠ negative); sign already normalised |
| `net_current_liabilities` | `NetCurrentAssetsLiabilities < 0` | `NetCurrentAssetsLiabilities` | ~85.1% | dash=nil; sign |
| `current_ratio` | `CurrentAssets / creditors_within_one_year` | `CurrentAssets`, `creditors_within_one_year` | limited by `creditors_within_one_year` ~32.7% | **denominator 0 or missing → `null`, never ±∞**; use the maturity bucket **not** `Creditors` |
| `cash` | `CashBankOnHand` | `CashBankOnHand` | ~35.4% | dash=nil |
| `employee_band` | band of `AverageNumberEmployeesDuringPeriod` (e.g. 0 / 1–9 / 10–49 / 50–249 / 250+) | `AverageNumberEmployeesDuringPeriod`, `employees_unit_anomaly` | ~60.7% | do **not** filter by unit; carry `employees_unit_anomaly` as a caveat, never drop a value |
| `n_periods_available` | count of periods with `row_available <= T` | WIDE rows | 100% (0 if none) | — |
| `months_since_latest_period_end` | months(T-month-end − latest.period_end) | `period_end`, T | 100% where a latest exists | filter corrupt period_end |
| `d_equity` / `d_net_current_assets` / `d_cash` | latest − prior | `Equity`, `NetCurrentAssetsLiabilities`, `CashBankOnHand` (×2 periods) | needs both periods; null if no prior or gap >18mo | dash=nil; period-length (§2) |
| `accounts_category` | register `AccountCategory` of the nearest-T snapshot | **register snapshot**, not WIDE | per register | WIDE has no category; this is the *current* register label |

**Tiers / governance.** None of these is person-derived — they are company financial facts and
counts. **So the governed and ungoverned tiers are identical**: the `data_governance` switch is
carried for symmetry with the register and PSC tables (governed default), but no accounts column is
dropped or added between tiers, and there is no ungoverned-only accounts feature. Stated explicitly
as the handoff requests.

## 5. Coverage

Share of **live (Active) register companies with any accounts feature at T** (any WIDE period with
`row_available <= T`): **70.08%** (3,624,290 / 5,171,599). By type and category:

| CompanyCategory | covered % |   | AccountCategory | covered % |
|---|---:|---|---|---:|
| Private Limited Company | 72.9 |   | MICRO ENTITY | 99.3 |
| PRI/LTD BY GUAR/NSC | 79.8 |   | UNAUDITED ABRIDGED | 98.7 |
| Limited Liability Partnership | 58.9 |   | TOTAL EXEMPTION FULL | 96.4 |
| Community Interest Company | 33.0 |   | DORMANT | 94.6 |
| Limited Partnership / CIO / Overseas Entity / Registered Society | 0.0 |   | MEDIUM | 88.3 |
| | |   | SMALL | 67.0 / FULL 34.3 / GROUP 49.6 |
| | |   | NO ACCOUNTS FILED | 0.0 |

This confirms the expectation: **micro-entity, filleted (total-exemption / abridged) and dormant
filers — the balance-sheet-only majority — are 94–99% covered**, while full/group accounts (often
PDF or richer filings) and non-iXBRL types (LP, CIO, overseas entities, registered societies) are
low or zero. "No accounts filed" is 0% by construction.

## 6. The joins

All three per-company tables key on the **normalised 8-character company number** (WIDE `company`,
register `CompanyNumber`, PSC `company_number` — all zero-padded; confirmed same format).

```
register_features (T_reg)  ⟕  accounts_features (T)  ⟕  psc_features (T_psc)   on company_number
```

- **Register** is the spine (it defines "live companies"); accounts and PSC **left-join** onto it.
- **Snapshot-date alignment.** The register is monthly (`BasicCompanyData`/`YYYY-MM-01`); PSC is in
  practice monthly (the snapshot we load); accounts availability is by **archive month**. Pick a
  reference month and take each table's nearest snapshot **at or before** the common T, recording
  the three source dates on the joined output (they will differ by days–weeks). For the measured T
  here: accounts archive 2026-08, register 2026-09-01, PSC 2026-09-25.
- **"Missing" means different things:**
  - *accounts missing* = no filing available by T (not yet filed, PDF/XML-only, pre-2014, or a
    non-iXBRL type) — **not** "zero".
  - *register missing* = company not on the live register at that snapshot (dissolved/removed).
  - *PSC missing* = no PSC record in that snapshot (outside the PSC regime, or genuinely none);
    distinct from `psc_information_state = none_reported`.
  - Within a present accounts row, a **null cell** = that concept not filed (filleted/micro), **not
    zero**; a **0** = a declared nil (dash).

## Open decisions (for review before Stage B)

1. **Point-in-time granularity** — row-level availability (`row_available_yyyymm <= T`, proposed:
   simple, no look-ahead) vs a cell-level refinement (null individual cells whose provenance archive
   month > T). Row-level drops the ~0.0% partially-available rows entirely; cell-level reconstructs
   the exact as-of-T picture at more cost. **Recommend row-level for v1.**
2. **T as an archive-month boundary** (`YYYYMM`, end-of-month) — confirm, vs an exact date.
3. **`current_ratio` zero/missing denominator → `null`** (no infinities) — confirm, vs emitting a
   separate `current_ratio_denominator_zero` flag.
4. **`employee_band` boundaries** — proposed 0 / 1–9 / 10–49 / 50–249 / 250+ (aligned to the
   micro/small/medium size tests). Confirm the cut-points.
5. **`accounts_category` source** — register nearest-T snapshot (proposed), accepting it is the
   *current* label. Confirm.
6. **Corrupt-period-end filter** — plausible window `'2010-01-01' … T-month-end + 1 year`. Confirm.
7. **Tiers** — governed == ungoverned for accounts (no person-derived feature); keep the switch for
   symmetry. Confirm this is acceptable rather than omitting the switch.
8. **Change features across a >18-month gap** → null + `prior_gap_months` diagnostic. Confirm.
9. **Mode** — feature table from `as_first_reported` only; `latest` left for descriptive analysis
   out of this table. Confirm.

## Stage B plan (after approval)

- Implement the approved features in a new module (mirroring `ukcompany.psc.features` /
  `ukcompany.snapshot.features`): one definition, FIELD_DOCS entries for every column, regenerated
  data dictionary, both tiers via `data_governance` (identical here).
- Tests (synthetic fixtures only):
  - **point-in-time**: a filing whose archive month is after T must never affect features at T;
  - **zero / missing denominator** → `null` current ratio (no ±∞);
  - one test per pitfall: dash=nil (0 not null, 0 not negative-equity), creditors bucket vs total,
    `employees_unit_anomaly` not dropped, scale/sign.
- Run the register reconciliation on real data and report it (as in §3).
- **Full-run warning.** The build scans WIDE `as_first_reported` (671 MB / 33.5M rows) and joins the
  register CSV (2.7 GB); the exploratory pass for this design took ~1–2 min at a few GB. The feature
  build will be of the same order (a few minutes, ≤10 GB). It will be announced with a measured
  time/memory before any full run, per Handoffs 07/08.
