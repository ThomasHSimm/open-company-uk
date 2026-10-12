# UK Company Accounts — WIDE (2014–2026)

Balance-sheet facts for UK companies, one row per company per accounting period,
extracted from Companies House's free monthly bulk iXBRL accounts archives.
Financial facts and company numbers only — no names, addresses or director data.
Open Government Licence v3.0.

## What this is

A tidy, analysis-ready table of the core balance-sheet figures UK companies file
with Companies House. Each row is **one company, one accounting period**; each
column is a reviewed accounting concept. Values are parsed from the iXBRL (and
plain-XML) tags in the public monthly accounts archives and carried through only
from **non-dimensional totals** plus **four reviewed dimensional members**
(two equity splits, two creditor-maturity splits) — so a figure that only exists
inside a related-party, director or key-management breakdown has no column here
and is never included.

- **Coverage:** 152 monthly archives, continuous **2014-01 → 2026-08, no gaps.**
- **Size:** **33,513,017 rows** (flagship `as_first_reported` file);
  **36,710,673 rows** in the `latest` file. About **6.8 million distinct
  companies.**
- **Scope:** balance-sheet only for most companies — filleted small-company
  filings rarely carry turnover or profit. Most rows are deliberately sparse: a
  company that filed only `Equity` and `CurrentAssets` genuinely filed only those.

## Which file to use

Two files share one schema and differ only in which filing wins each cell:

- **`accounts-wide-as_first_reported.parquet` — flagship, use this by default.**
  Each cell holds the value from the **earliest** filing that reported it. **Use
  it for any predictive or point-in-time work.**
- **`accounts-wide-latest.parquet` — secondary.** Each cell holds the value from
  the **most recent** filing, which can fold in later comparative restatements of
  an earlier period. Do **not** use it for predictive work.

Across the full span, **9.36%** of repeated (company, period, concept) values
disagree between the first-reported and a later filing — which is exactly why the
two files are kept separate rather than collapsed into one ambiguous column.

## Avoiding look-ahead (read this before any time-series or predictive use)

This dataset does **not** claim to be free of look-ahead by construction. What it
actually guarantees, and what you must do:

- The flagship file **excludes later restatements** (`as_first_reported` takes the
  earliest filing of each value).
- Rows carry **period-end dates, not filing dates.** `period_end` tells you the
  accounting period a figure describes — **not** when that figure became public.
- To avoid look-ahead you must **lag by availability**: filter on
  **`row_available_yyyymm`**, the archive (registration) month by which every value
  in the row had actually been filed and published. A row describing a period
  ending in March can only be *known* months later, once the accounts were filed
  and appeared in a monthly archive. The same archive-month provenance is in the
  companion `accounts-wide-provenance-{mode}.parquet`, per cell. Using `period_end`
  alone as if it were the availability date will leak the future.

## Columns

| Column | Meaning | Unit |
|---|---|---|
| `company` | Companies House number (leading zeros preserved) | string |
| `period_end` | Accounting period end date | date |
| `Equity` | Total equity (shareholders' funds) | GBP |
| `NetCurrentAssetsLiabilities` | Net current assets/liabilities | GBP |
| `CurrentAssets` | Total current assets | GBP |
| `Creditors` | Total creditors, all maturities — sparse; prefer the splits | GBP |
| `CashBankOnHand` | Cash and bank balances | GBP |
| `Debtors` | Total debtors | GBP |
| `PropertyPlantEquipment` | Property, plant & equipment (net book value) | GBP |
| `TotalAssetsLessCurrentLiabilities` | Total assets less current liabilities | GBP |
| `AverageNumberEmployeesDuringPeriod` | Average employees during the period | headcount |
| `equity_share_capital` | Equity split: called-up share capital | GBP |
| `equity_retained_earnings` | Equity split: retained earnings / accumulated losses | GBP |
| `creditors_within_one_year` | Creditors falling due within one year | GBP |
| `creditors_after_one_year` | Creditors falling due after one year | GBP |
| `employees_unit_anomaly` | Diagnostic: was the employee value GBP-tagged? | 0/1 |
| `n_concepts_present` | How many concept columns are populated in the row | count |
| `n_source_filings` | How many filings contributed to the row | count |
| `row_available_yyyymm` | Month by which the whole row was known (use for point-in-time) | YYYYMM |

Per-column coverage (fill rates) ships *with* the download in the generated
`column-dictionary.md`. The two Equity splits are ~30% populated, the two
Creditors maturity splits ~33% / ~14%; the headline totals range from ~4%
(`Creditors` total) to ~85% (`NetCurrentAssetsLiabilities`).

## v1 → v2 changelog

- **Full history.** v2 spans 2014-01 → 2026-08 (152 archives); v1 was a shorter,
  development-era span.
- **Creditors maturity splits added.** `creditors_within_one_year` and
  `creditors_after_one_year` are promoted into WIDE (the sparse `Creditors` total
  alone was hard to use).
- **First-reported vs latest split out.** Two files replace v1's single table, so
  point-in-time users get a no-restatement file and others get current values.
- **Availability provenance.** `row_available_yyyymm` and the per-cell
  `accounts-wide-provenance-{mode}.parquet` are shipped so availability lagging is
  a single filter.

## Licence, provenance and the withdrawn LONG table

Contains public sector information licensed under the **Open Government Licence
v3.0**. Source: Companies House free monthly bulk accounts archives. The dataset
carries **financial facts and company numbers only** — no personal data.

A per-fact **LONG** companion table was briefly published and has since been
**withdrawn** pending a dimension-aware privacy filter; it is not currently
available.

## Links

- **Methodology & extractor accuracy:** the methodology site
  (<https://thomashsimm.github.io/open-company-uk/datasets/accounts.html>) and the
  repository (<https://github.com/ThomasHSimm/open-company-uk>), which document the
  parser comparison, every reconciliation and the known limitations.
- **This dataset:**
  <https://www.kaggle.com/datasets/thomassimm/uk-company-accounts-wide-2014-2026>

---

*Not part of the card — notes for the maintainer*

- **Confirm the site URL** before pasting: I used the conventional GitHub Pages URL
  `https://thomashsimm.github.io/open-company-uk/datasets/accounts.html`; swap it
  for the real published location if different.
- **Company count** (~6.8M) is from local measurement of the as_first_reported file
  (6,849,384 distinct `company`); confirm it matches the published, Kaggle-filtered
  file, which may differ marginally.
- **Column-list check vs `docs/accounts-wide-columns.md`:** the published column set
  matches `config/accounts-wide-columns.json` (9 totals + 4 members + helpers), but
  it is **out of sync with `docs/accounts-wide-columns.md`**, which still describes
  the two creditors-maturity members as *gated / not yet approved* ("Creditors
  members are gated", "If Creditors members are later approved…"). They are in fact
  shipped in v2. The PP&E *total* is shipped; PP&E *members* remain excluded, which
  the doc's "deferred to v2" text still (correctly) reflects. Recommend regenerating
  / updating `docs/accounts-wide-columns.md` to show the creditors splits as shipped.
