# Design: per-company accounts features and the join to the register (Handoff 02)

**Status: Stage A approved; Stage B built.** This specifies (and now implements, in
`ukcompany.accounts.features`) a per-company **accounts feature table for a reference date T**, built
from the published WIDE accounts dataset and its provenance, so it joins to the register features
(Handoff 08) and the PSC features (Handoff 07) on the normalised company number. **T is an
end-of-month boundary, applied consistently across all three tables** (see §0). Numbers below are
measured on the local corpus (WIDE `as_first_reported`, 33,513,017 rows over archive months
2014-01 … 2026-08) at the **aligned reference T = 2026-07** (end of July), paired with the register
snapshot **dated 2026-08-01** (published on the 1st, reflecting the register at end of July — the
correct pairing; see §0 and §6). Attributes only — no rules, no composite score.

> **Stage B decisions (approved).** Point-in-time is **row-level** (`row_available_yyyymm <= T`):
> only **0.0036%** of WIDE rows (1,211 / 33,513,017) draw cells from more than one archive month —
> far below the 1–2% threshold for switching to cell-level. `current_ratio` is **null** on a zero or
> missing denominator (never ±∞) and `current_assets`, `creditors_within_one_year`, `equity`,
> `net_current_assets` ship as columns. Employee bands use the **Companies Act** thresholds
> (0 / 1–10 / 11–50 / 51–250 / 251+). `accounts_category` comes from the register snapshot paired to
> T by the **end-of-month rule** (the snapshot dated ≤ the first day of T+1; see §0/§6), **not** a
> same-numbered-month snapshot. The `data_governance` switch is kept (governed == ungoverned here;
> nothing is person-derived). **Coverage is strongly size-skewed — see §5; this is the single most
> important caveat on the whole table.**

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

### 0.1 T is end-of-month, and the register/PSC snapshot must be paired to that — not by month number

**T means the state as at the *end* of calendar month T, used identically for all three tables.**
This matters for pairing because the three products are dated on different conventions:

- **WIDE accounts**: `row_available_yyyymm` is the archive month a filing appeared in. Archive month
  M = filings accepted *during* M = available by **end of M**. So `row_available_yyyymm <= T` already
  means "available by end of T".
- **Register / PSC `BasicCompanyData`**: Companies House publishes the snapshot dated **`YYYY-MM-01`**
  (confirmed from each snapshot's `manifest.json`: the `2026-08-01` snapshot's files are
  `BasicCompanyData-2026-08-01-*`, `downloaded_at` 2026-08-06). A snapshot dated the **1st of a
  month** reflects the register at the *start* of that month, i.e. **end of the previous month**.

So the snapshot aligned to **T = end of archive month M** is the one dated **`(M+1)-01`** — formally,
**the latest snapshot dated ≤ the first day of T+1**. For T = 2026-07 (end of July) that is the
**2026-08-01** snapshot. Pairing a same-numbered-month snapshot (register `2026-08-01` with WIDE
`<= 2026-08`) puts WIDE a full month ahead of the register and manufactures a spurious "WIDE-newer"
gap — see §3.

## 1. Availability

### 1.1 The archive month is recoverable for every cell — confirmed

`accounts-wide-provenance-*.parquet` holds one row per **(company, period_end, wide_column)** with
`source_year`, `source_month` (the archive month the cell's value came from), `source_member` and
`made_up_to_date`. Measured over the `as_first_reported` provenance: **195,937,522 cells, 0 with a
null archive month, 0 with a null `made_up_to_date`.** So the availability date of any WIDE cell is
recoverable exactly, and the row-level `row_available_yyyymm` in WIDE is its max.

### 1.2 Archive month M is the registration month; the monthly ZIP arrives after month-end

The source is Companies House's **"Company accounts data"** bulk product. Its
[monthly product page](https://download.companieshouse.gov.uk/en_monthlyaccountsdata.html) says the
filename identifies the month/year the data relates to and that a new monthly file is added within
five working days **after** the previous month ends. Its
[daily product page](https://download.companieshouse.gov.uk/en_accountsdata.html) says each daily
file contains accounts data registered on the previous day (with the Tuesday weekend exception).
The pipeline records the monthly archive label as `source_year`/`source_month`.

The cutoff question is therefore resolved in two parts. Archive M is a month-grained
**registration-month** boundary, while the consolidated monthly ZIP is published after M ends (the
September 2026 object observed for the internal extension was last modified on 9 October). The
project's `row_available_yyyymm <= T` convention means “registered in or before T”, not “the monthly
ZIP was already downloadable at T”. Exact artifact-time availability would require the daily files
(with a next-morning edge for the final day) or a lagged monthly cutoff. See the explicitly internal
`accounts-internal-202609-stage1.md` for the live check; published WIDE remains v2 through 2026-08.

Empirical support: the lag from period end to archive month is never negative for a valid period
end — the only negatives (1,642 rows) come from corrupt period-end dates (years 0001 / 3020; see
§1.4), not from filings predating their period.

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
Within `as_first_reported`, a (company, period) row draws cells from **more than one archive month
only 0.0036%** of the time (**1,211 of 33,513,017 rows**, measured on the provenance parquet) — i.e.
when a later filing adds a concept the first lacked; such a row's `row_available_yyyymm` is the later
archive, so it is correctly treated as available only then. The spread among those rows is a p50 of
12, p90 of 14 and max of 29 months. Because this is far below the 1–2% threshold for a cell-level
rebuild, **row-level point-in-time is used** (see §0 and the Stage B decisions box). **Corrupt period
ends:** ~1,642 rows have an impossible period_end (year 0001 or 3020); the build filters to a
plausible window (`'2010-01-01' ≤ period_end ≤ T-year + 1`).

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
`row_available <= T`) vs the register's **`Accounts.LastMadeUpDate`**, taken from the register
snapshot **paired to T by the end-of-month rule (§0.1)**. At the aligned **T = 2026-07** that is the
**2026-08-01** snapshot. Of the 5,695,465 register companies:

| bucket | n | % |
|---|---:|---:|
| exact match (WIDE latest period end = register LastMadeUpDate) | 3,914,598 | 68.73% |
| both absent (no WIDE row and no register LastMadeUpDate) | 1,460,748 | 25.65% |
| no WIDE row, but register has a LastMadeUpDate | 229,527 | 4.03% |
| register newer than WIDE latest | 90,461 | 1.59% |
| WIDE newer than register | 102 | 0.00% |
| WIDE row present, but register has no LastMadeUpDate | 29 | 0.00% |

**Among the 4,005,161 companies present in both, 97.74% match exactly** — the accounts equivalent of
the 07/08 parity tests. The remaining ~2% is almost entirely *register-newer* (a latest filing that
is XML/PDF-only while WIDE holds an earlier iXBRL one) plus *no-WIDE-row* companies.

**Pairing matters — ran it both ways to prove the alignment, not the data, drives the gap:**

| WIDE cutoff | register snapshot | exact (both-present) | WIDE-newer |
|---|---|---:|---:|
| `<= 2026-07` | 2026-08-01 (aligned, end-of-July both sides) | **97.74%** | **0.00%** (102 cos) |
| `<= 2026-08` | 2026-08-01 (register one month behind WIDE) | 92.22% | 5.60% (224,442 cos) |

The **3.94% "WIDE-newer" reported in the first Stage-B pass was an alignment artefact, not a
finding**: pairing WIDE `<= 2026-08` (end of August) against the `2026-08-01` register (end of July)
made WIDE a month ahead, so August filers showed a "newer" period the register simply had not been
sampled late enough to show. Aligning per §0.1 collapses it to 102 companies (0.00%) and restores the
~97–98% exact match. (The complementary aligned check, WIDE `<= 2026-08` vs register `2026-09-01`,
could not be run: no `2026-09-01` snapshot is present locally — only `2026-08-01` and `2026-10-01`.)
No claim is made that the residual bucket is "consistent with the monthly-cut-off assumption"; the
cut-off question (§1.2) is left open and independent of this reconciliation.

Mismatch categories at the aligned T:

- **no WIDE row (4.03%)** — the register shows a last-made-up date but WIDE has nothing: an XML- or
  PDF-only filing (not iXBRL), a pre-2014 period, or a company type outside the iXBRL product.
- **register newer (1.59%)** — the register's latest period post-dates WIDE's: a latest filing that
  is XML/PDF-only while an earlier iXBRL one is in WIDE (a format difference, not an error).
- **both absent (25.65%)** — overwhelmingly `NO ACCOUNTS FILED` companies (newly incorporated or
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
| `equity`, `current_assets`, `creditors_within_one_year`, `net_current_assets`, `cash` | raw latest-period figures (shipped as columns) | `Equity`, `CurrentAssets`, `creditors_within_one_year`, `NetCurrentAssetsLiabilities`, `CashBankOnHand` | per column (see §5) | dash=nil; scale/sign already normalised |
| `current_ratio` | `CurrentAssets / creditors_within_one_year` | `CurrentAssets`, `creditors_within_one_year` | limited by `creditors_within_one_year` ~32.7% | **denominator 0 or missing → `null`, never ±∞**; use the maturity bucket **not** `Creditors` |
| `cash` | `CashBankOnHand` | `CashBankOnHand` | ~35.4% | dash=nil |
| `employee_band` | band of `AverageNumberEmployeesDuringPeriod`, **Companies Act thresholds 0 / 1–10 / 11–50 / 51–250 / 251+** | `AverageNumberEmployeesDuringPeriod`, `employees_unit_anomaly` | ~60.7% | do **not** filter by unit; carry `employees_unit_anomaly`, never drop a value. **Break around 2020–21**: employee tagging for micro/small entities changed, so band distributions are not comparable across it (noted in FIELD_DOCS) |
| `n_periods_available` | count of periods with `row_available <= T` | WIDE rows | 100% (0 if none) | — |
| `months_since_latest_period_end` | months(T-month-end − latest.period_end) | `period_end`, T | 100% where a latest exists | filter corrupt period_end |
| `d_equity` / `d_net_current_assets` / `d_cash` | latest − prior | `Equity`, `NetCurrentAssetsLiabilities`, `CashBankOnHand` (×2 periods) | needs both periods; null if no prior or gap >18mo | dash=nil; period-length (§2) |
| `accounts_category` | register `AccountCategory` of the nearest-T snapshot | **register snapshot**, not WIDE | per register | WIDE has no category; this is the *current* register label |

**Tiers / governance.** None of these is person-derived — they are company financial facts and
counts. **So the governed and ungoverned tiers are identical**: the `data_governance` switch is
carried for symmetry with the register and PSC tables (governed default), but no accounts column is
dropped or added between tiers, and there is no ungoverned-only accounts feature. Stated explicitly
as the handoff requests.

## 5. Coverage — **STRONGLY SIZE-SKEWED (the headline caveat)**

> **Read this before using the table for anything.** iXBRL accounts coverage is **not uniform across
> companies**: it is near-complete for the small/micro/dormant majority and partial-to-absent for
> larger entities and non-iXBRL legal forms. A company's **absence from the accounts table is NOT the
> absence of accounts** — it is usually an XML/PDF-only or non-iXBRL filing. Any downstream use that
> compares companies, or treats "no accounts feature" as a signal, must condition on size/type or it
> will mistake a **data-availability artefact** for a real difference.

Share of **live (Active) register companies with any accounts feature at T** (any WIDE period with
`row_available <= T`), at the aligned T = 2026-07 vs register 2026-08-01: **70.38%**
(3,926,714 / 5,579,415). By type and category:

| CompanyCategory | covered % |   | AccountCategory | n | covered % |
|---|---:|---|---|---:|---:|
| Private Limited Company | 73.1 |   | MICRO ENTITY | 1,823,934 | 99.3 |
| PRI/LTD BY GUAR/NSC | 79.2 |   | UNAUDITED ABRIDGED | 159,887 | 98.7 |
| PRI/LBG/NSC | 61.1 |   | TOTAL EXEMPTION FULL | 1,299,198 | 96.4 |
| Limited Liability Partnership | 58.5 |   | DORMANT | 635,200 | 94.9 |
| Community Interest Company | 32.8 |   | MEDIUM | 6,180 | 88.2 |
| Limited Partnership | 0.0 |   | SMALL | 63,611 | 66.8 |
| Charitable Incorporated Organisation | 0.0 |   | GROUP | 27,116 | 49.4 |
| Overseas Entity | 0.0 |   | AUDIT EXEMPTION SUBSIDIARY / FULL | 33,327 / 79,773 | 35.6 / 34.1 |
| | |   | NO ACCOUNTS FILED | 1,446,381 | 0.0 |

This is the expected shape: **micro-entity, filleted (total-exemption / abridged) and dormant filers
— the balance-sheet-only majority — are 95–99% covered**, while full/group/subsidiary accounts
(often PDF or richer filings) sit at 34–50%, and **non-iXBRL legal forms (LP, CIO, overseas
entities) are ~0%**. "No accounts filed" is 0% by construction. The size-skew is restated prominently
in FIELD_DOCS on `latest_period_end` and `equity`.

## 6. The joins

All three per-company tables key on the **normalised 8-character company number** (WIDE `company`,
register `CompanyNumber`, PSC `company_number` — all zero-padded; confirmed same format).

```
register_features (T_reg)  ⟕  accounts_features (T)  ⟕  psc_features (T_psc)   on company_number
```

- **Register** is the spine (it defines "live companies"); accounts and PSC **left-join** onto it.
- **Snapshot-date alignment (end-of-month rule, §0.1).** T is the **end of calendar month T** for
  all three tables. Accounts use `row_available_yyyymm <= T` directly. The register and PSC
  `BasicCompanyData`/snapshot files are dated `YYYY-MM-01` and reflect the *start* of that month
  (≈ end of the previous month), so each is paired by taking the **latest snapshot dated ≤ the first
  day of T+1** — i.e. the snapshot dated `(month-after-T)-01`. Verify each snapshot's as-of date from
  its `manifest.json` before pairing. Record the three source dates on the joined output. For the
  aligned measured T here: accounts archive end-2026-07, register **2026-08-01**
  (`accounts_category` and the §3 reconciliation both use this snapshot), PSC the correspondingly
  paired ≤-first-of-T+1 snapshot. Pairing a same-numbered-month register (e.g. `2026-08-01` with WIDE
  `<= 2026-08`) is **wrong** — it puts WIDE a month ahead and fabricates a WIDE-newer gap (§3).
- **"Missing" means different things:**
  - *accounts missing* = no filing available by T (not yet filed, PDF/XML-only, pre-2014, or a
    non-iXBRL type) — **not** "zero".
  - *register missing* = company not on the live register at that snapshot (dissolved/removed).
  - *PSC missing* = no PSC record in that snapshot (outside the PSC regime, or genuinely none);
    distinct from `psc_information_state = none_reported`.
  - Within a present accounts row, a **null cell** = that concept not filed (filleted/micro), **not
    zero**; a **0** = a declared nil (dash).

## Decisions (resolved at Stage B approval)

1. **Point-in-time granularity** → **row-level** (`row_available_yyyymm <= T`). The gate the
   maintainer asked for — share of WIDE rows whose cells span more than one archive month — came back
   at **0.0036%** (1,211 / 33,513,017), far below the 1–2% threshold, so cell-level is unnecessary.
2. **T as an archive-month boundary** (`YYYYMM`, end-of-month) → **confirmed**.
3. **`current_ratio` zero/missing denominator → `null`** (no infinities) → **confirmed**; and
   `current_assets`, `creditors_within_one_year`, `equity`, `net_current_assets` ship as columns.
4. **`employee_band` boundaries** → **Companies Act thresholds 0 / 1–10 / 11–50 / 51–250 / 251+**
   (revised from the first draft's 1–9/10–49/… cut-points). The 2020–21 reporting break is noted in
   FIELD_DOCS.
5. **`accounts_category` source** → register snapshot **dated ≤ T** (revised from "nearest"),
   accepting it is the *then-current* label.
6. **Corrupt-period-end filter** → plausible window `'2010-01-01' … T-year + 1`. **Confirmed.**
7. **Tiers** → governed == ungoverned for accounts (no person-derived feature); the `data_governance`
   switch is **kept** for symmetry. **Confirmed.**
8. **Change features across a >18-month gap** → null + `prior_gap_months` diagnostic. **Confirmed.**
9. **Mode** → feature table from `as_first_reported` only; `latest` left for descriptive analysis.
   **Confirmed.**

## Stage B — delivered

- **Module** `ukcompany.accounts.features.build_accounts_features` (mirrors `ukcompany.psc.features` /
  `ukcompany.snapshot.features`): one definition, 20 feature columns, both tiers via `data_governance`
  (identical here). FIELD_DOCS entries for every new column in `derive.py`; data dictionary
  regenerated via `ukcompany data-dict`.
- **Tests** (`tests/test_accounts_features.py`, synthetic polars fixtures, 9 cases, all passing):
  point-in-time exclusion (an archive month after T never affects features at T); zero **and** missing
  denominator → `null` current ratio (no ±∞); one case per pitfall — dash=nil (0 not null, 0 not
  negative-equity), creditors maturity bucket vs the bare total, `employees_unit_anomaly` carried not
  dropped, sign respected; the >18-month-gap null rule; and governed==ungoverned schema equality.
- **Real run (aligned T = 2026-07, register 2026-08-01).** Both tiers built: **6,795,318 companies**
  each, ~32 s wall-clock, peak well under the 10 GB limit. Reconciliation **97.74%** exact among
  both-present and coverage **70.38%** as reported in §3 and §5. Outputs written under
  `data/accounts/features/{governed,ungoverned}/` (gitignored).
