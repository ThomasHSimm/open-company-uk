# Accounts-only historical case lead-time results

**Status:** completed case-only descriptive study. Aggregate results only. This is not a matched
evaluation, rule validation or population prediction study. The prospective study remains on hold.

## Study definition

The cohort and denominators follow the committed clarification in
[`validation-run-plan.md`](validation-run-plan.md#1-historical-case-only-study-available-now).
Cases were not joined to or filtered by the current register. Every accounts value was taken from
the `as_first_reported` WIDE table only when that exact cell's provenance satisfied
`source_year * 100 + source_month <= T`; `row_available_yyyymm` was not used. This preserves an
earlier available cell even when another cell in the same row was filled later.

The primary lead is 12 months before the event-registration month, with predeclared 6- and 24-month
analyses. The primary convention treats the accounts source registration month as available in that
month. The sensitivity convention delays it by one month. Both are archive-month resolution, not
exact filing timestamps. The one-cycle lag is an approximation because historical ZIP publication
dates are not retained.

Only the planned accounts attributes were analysed. No rule, threshold or composite score was
created or tuned.

## Inputs and reproducibility

The aggregate run used implementation commit `ddfc1153a9434ec70e8246cf390893365af9ac47`.

| input | bytes | SHA-256 |
|---|---:|---|
| `data/labels/record-level-data.csv` | 24,774,815 | `a026af069d12646901372a787cd6eafcd25443143e2b4aa30fcf7acc3c69b9d7` |
| `data/accounts/v2-internal-202609/accounts-wide-as_first_reported.parquet` | 716,234,482 | `957b6169121a124c9582924b869117852c1ab60210c65d93036eba6cfe533e47` |
| `data/accounts/v2-internal-202609/accounts-wide-provenance-as_first_reported.parquet` | 628,989,416 | `e8ee476d23d3c4c14a93391acc95f38e5aff234494c1e388b6f51f3874633b5d` |

The gitignored aggregate JSON is
`data/validation/accounts-case-lead-time-aggregate.json` (40,088 bytes; SHA-256
`64aaf28d409360cc341975d381ee9f1938030e9d7bacf9be7ab1baae7470ef6e`). It contains no company
numbers. The scan took 6.4 seconds and peaked at 3,186,085,888 bytes (2.97 GiB RSS) under an 8 GiB
DuckDB limit.

## Cohort flow

The existing label loader first removes ineligible source rows, then retains the first remaining row
per normalised company number. The analysis unit is therefore one retained label row per company,
not every proceeding for a company. The publication has no event identifier, so this pipeline does
not establish a unique-event count.

| transition | removed | remaining | unit after transition |
|---|---:|---:|---|
| publication input | — | 237,391 | source rows |
| remove explicit bulk rows | 5,740 | 231,651 | source rows |
| remove Administration-to-CVL rows | 7,102 | 224,549 | source rows |
| remove unusable company numbers | 736 | 223,813 | source rows |
| remove unusable month rows | 0 | 223,813 | source rows |
| retain first row per normalised company | 3,352 additional company rows | 220,461 | unique companies, one retained label row each |
| remove unsupported retained case types | 201 companies | 220,260 | supported unique companies |
| remove supported labels before 2015-01 | 54,968 companies | 165,292 | companies in the fixed date window |
| remove supported labels after 2024-04 | 0 companies | **165,292** | **candidate companies** |

The previously unexplained 13,578-row difference is fully accounted for before deduplication:

`5,740 bulk + 7,102 Administration-to-CVL + 736 unusable numbers + 0 unusable months = 13,578`.

Then `237,391 - 13,578 = 223,813` eligible source rows before company deduplication, and
`223,813 - 3,352 = 220,461` unique retained companies. The 3,352 are subsequent rows for an already
retained company; they are not asserted to be 3,352 unique events or exact duplicate proceedings.

The supported/date transitions also reconcile:

`220,461 - 201 unsupported - 54,968 before window - 0 after window = 165,292 candidates`.

Candidate composition was 124,736 creditors' voluntary liquidations, 25,066 compulsory
liquidations, 13,436 administrations and 2,054 corporate voluntary arrangements.

## Coverage and observed signals

`Any accounts` means at least one planned cell was available. Attribute coverage uses all 165,292
candidates as denominator. Binary rates use only observed true + false values; unavailable values
are never counted as false.

| lead | convention | any accounts | equity observed | negative equity | net current assets observed | net current liabilities | current ratio observed | employees observed | unit-anomaly diagnostic |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 6m | registration month | 124,228 (75.2%) | 80,050 (48.4%) | 26,460 / 80,050 (33.1%) | 120,621 (73.0%) | 52,907 / 120,621 (43.9%) | 35,001 (21.2%) | 67,691 (41.0%) | 11,456 / 67,691 (16.9%) |
| 6m | one-cycle lag | 122,754 (74.3%) | 78,769 (47.7%) | 25,598 / 78,769 (32.5%) | 119,181 (72.1%) | 51,957 / 119,181 (43.6%) | 34,365 (20.8%) | 66,407 (40.2%) | 11,202 / 66,407 (16.9%) |
| 12m | registration month | 114,615 (69.3%) | 71,999 (43.6%) | 21,725 / 71,999 (30.2%) | 111,266 (67.3%) | 47,570 / 111,266 (42.8%) | 31,255 (18.9%) | 59,489 (36.0%) | 9,891 / 59,489 (16.6%) |
| 12m | one-cycle lag | 112,724 (68.2%) | 70,617 (42.7%) | 21,027 / 70,617 (29.8%) | 109,442 (66.2%) | 46,622 / 109,442 (42.6%) | 30,626 (18.5%) | 57,958 (35.1%) | 9,553 / 57,958 (16.5%) |
| 24m | registration month | 91,190 (55.2%) | 55,231 (33.4%) | 14,422 / 55,231 (26.1%) | 88,396 (53.5%) | 37,313 / 88,396 (42.2%) | 23,468 (14.2%) | 39,838 (24.1%) | 5,708 / 39,838 (14.3%) |
| 24m | one-cycle lag | 89,377 (54.1%) | 53,993 (32.7%) | 13,874 / 53,993 (25.7%) | 86,594 (52.4%) | 36,534 / 86,594 (42.2%) | 22,877 (13.8%) | 38,191 (23.1%) | 5,350 / 38,191 (14.0%) |

At the primary 12-month registration-month cutoff, 50,677 candidates (30.7%) had no eligible
planned accounts cell. The corresponding absent counts were 41,064 (24.8%) at six months and
74,102 (44.8%) at 24 months. The one-cycle lag increased absence by 1,474, 1,891 and 1,813 cases at
6, 12 and 24 months respectively.

### Primary attribute coverage

| attribute | observed | share of 165,292 candidates |
|---|---:|---:|
| any planned accounts cell | 114,615 | 69.3% |
| equity | 71,999 | 43.6% |
| current assets | 107,393 | 65.0% |
| creditors within one year | 33,111 | 20.0% |
| net current assets | 111,266 | 67.3% |
| cash | 42,278 | 25.6% |
| current ratio | 31,255 | 18.9% |
| employee band | 59,489 | 36.0% |
| equity change | 51,220 | 31.0% |
| net-current-assets change | 82,294 | 49.8% |
| cash change | 27,776 | 16.8% |

The large differences between `any accounts` and concept-specific coverage are material. In
particular, absence of a ratio or change is not evidence that the condition did not occur.

## Case-only temporal patterns

These are unadjusted distributions among cases with each attribute observed. The observed subset
changes by lead time, so movements are descriptive and are not predictive lift.

| attribute | 24m observed; median [Q1, Q3] | 12m observed; median [Q1, Q3] | 6m observed; median [Q1, Q3] |
|---|---:|---:|---:|
| equity | 55,231; 3,115 [-822, 34,215] | 71,999; 2,157 [-6,642, 33,072] | 80,050; 1,525 [-12,458, 31,426] |
| net current assets | 88,396; 1,296 [-15,544, 30,822] | 111,266; 1,422 [-19,653, 33,644] | 120,621; 1,127 [-23,694, 32,719] |
| current ratio | 23,468; 1.02 [0.57, 1.72] | 31,255; 1.04 [0.56, 1.85] | 35,001; 1.02 [0.52, 1.80] |
| equity change | 37,641; 0 [-11,973, 9,357] | 51,220; -87 [-16,295, 8,629] | 57,835; -558 [-20,564, 7,514] |
| net-current-assets change | 62,920; 616 [-11,440, 18,596] | 82,294; 158 [-15,044, 19,551] | 91,290; 0 [-18,899, 17,416] |

Among observed cases, negative equity rose from 26.1% at 24 months to 30.2% at 12 months and 33.1%
at six months. Net current liabilities were more stable: 42.2%, 42.8% and 43.9%. The lower quartiles
of equity and net current assets became more negative nearer registration, while median current
ratio stayed close to one. These patterns show that adverse balance-sheet attributes can predate
recorded insolvency in the covered case subset. They do not show how often the same attributes occur
in non-cases.

## Differential coverage

Primary 12-month any-accounts coverage differed substantially by recorded case type:

| case type | candidates | any accounts | coverage |
|---|---:|---:|---:|
| administration | 13,436 | 6,886 | 51.3% |
| compulsory liquidation | 25,066 | 15,159 | 60.5% |
| corporate voluntary arrangement | 2,054 | 1,265 | 61.6% |
| creditors' voluntary liquidation | 124,736 | 91,305 | 73.2% |

Coverage also rose sharply across event years, reflecting the 2014 archive start, changing iXBRL
coverage and filing selection rather than an outcome trend:

| event year | candidates | any accounts at 12m | coverage |
|---:|---:|---:|---:|
| 2015 | 14,956 | 3,370 | 22.5% |
| 2016 | 15,435 | 8,025 | 52.0% |
| 2017 | 15,137 | 9,292 | 61.4% |
| 2018 | 16,733 | 11,104 | 66.4% |
| 2019 | 17,862 | 12,145 | 68.0% |
| 2020 | 13,014 | 9,283 | 71.3% |
| 2021 | 14,657 | 11,253 | 76.8% |
| 2022 | 22,993 | 19,411 | 84.4% |
| 2023 | 26,221 | 23,323 | 88.9% |
| 2024 through April | 8,284 | 7,409 | 89.4% |

## What this establishes

- Accounts data can be reconstructed at archive-month cutoffs for a substantial, increasing subset
  of later recorded insolvency cases without using today's register or later-filled cells.
- Negative equity and net current liabilities were already observable in meaningful shares of the
  attribute-observed case subset 6–24 months before event registration.
- Coverage, not only attribute value, changes materially by lead, year and case type. Any later
  controlled study must model or stratify that selection.
- The one-cycle publication sensitivity changes coverage modestly and leaves the broad observed-case
  pattern similar, but it is only a lag approximation.

## Limitations

- This is case-only. It cannot estimate specificity, precision, false-positive rates, predictive
  lift, population prevalence or population predictive performance.
- Cases are conditional on appearing in the Insolvency Service file and on parseable iXBRL/plain-XML
  accounts. PDF-only accounts, non-filers and companies without the planned tags remain unavailable.
- There is no historical register population/status series. Historical company type, accounts
  category, alive-at-T state and competing dissolution were not inferred from current values.
- Outcome dates and accounts availability are month-grained. No result implies a daily filing or
  prediction timestamp. Registration month is not the monthly ZIP publication date.
- The label loader keeps the first source row per normalised company and removes 3,352 subsequent
  company rows. Results describe one retained label row per company; unique proceedings cannot be
  counted because the source has no event identifier.
- The 2015 cohort is close to the 2014 accounts archive boundary, and year coverage is therefore not
  comparable without accounting for archive maturity and iXBRL adoption.
- Employee bands and the unit-anomaly diagnostic are secondary because tagging changed around
  2020–2021. The diagnostic is not a distress signal.
- Monetary distributions are untrimmed source values. They describe the observed case subset and
  were not used to create thresholds.

## Validation

Synthetic tests cover exclusion of cells after T, preservation of earlier cells when a later fill
moves row availability, null-versus-observed-false semantics, the one-cycle lag and label cohort
selection. The focused suite passed 18 tests. Input key uniqueness, cohort expansion and disposition
reconciliation are fail-loud assertions. No company-level output was written; the gitignored run
artifact and this document contain aggregates only.
