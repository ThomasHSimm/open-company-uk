# Accounts extraction report

> Historical nine-concept regression sample. The current Stage 1 default is the full-fact archive; see `accounts-stage1-validation.md` for its two-archive validation. The `target_facts_seen` label below predates its rename to `facts_seen`.

## Run summary

- Archives represented: 2
- Completed archives: 0
- iXBRL filings processed: 1,994
- Long observations: 26,651
- Distinct company/period records: 3,725
- Fact accounting closes: **yes**

## Accounting invariant

| Bucket | Facts |
|---|---:|
| `target_facts_seen` | 29,861 |
| `kept_total` | 18,620 |
| `kept_member` | 8,031 |
| `collapsed_duplicate` | 2,205 |
| `ambiguous_nondimensional` | 0 |
| `member_value_conflict` | 0 |
| `skipped_multimember` | 1,005 |
| `skipped_typed` | 0 |
| `bad_period_refs` | 0 |

## Other integrity signals

- XML filings skipped: 6
- Filename exceptions: 0
- Unparseable filings: 0
- Company-number mismatches: 0
- Non-GBP monetary facts: 34
- Unresolved monetary unit references: 0

## V4 monotonic regression and lxml audit

The corrected parser was compared with the legacy extraction behavior over all 1,994 iXBRL filings in this sample. Identity included company, source member, period, concept, observation kind, normalized value, scale, sign, and currency.

- Legacy observations: 20,368
- Legacy observations reproduced identically: 20,368
- Legacy observations lost or changed: **0**
- Corrected production observations: 20,476
- Corrected-only additions: 108
- Corrected-only additions independently present in the lxml parse: 108
- Corrected-only additions absent from the lxml parse: **0**

All 108 additions are `AverageNumberEmployeesDuringPeriod` facts: 106 have value zero and two have value one. The legacy regex could allow a self-closing inline-XBRL element to consume a later closing tag. The earlier panel counts therefore remain valid as minimum counts, but they omit these recoverable employee observations.

## Non-dimensional total fill rates

| Concept | Genuine-total records | Genuine-total rate | Any-observation records | Any-observation rate |
|---|---:|---:|---:|---:|
| `Equity` | 3,438 | 92.3% | 3,609 | 96.9% |
| `NetCurrentAssetsLiabilities` | 2,956 | 79.4% | 2,967 | 79.7% |
| `CurrentAssets` | 2,735 | 73.4% | 2,735 | 73.4% |
| `Creditors` | 141 | 3.8% | 2,664 | 71.5% |
| `CashBankOnHand` | 1,544 | 41.4% | 1,544 | 41.4% |
| `Debtors` | 1,038 | 27.9% | 1,078 | 28.9% |
| `PropertyPlantEquipment` | 963 | 25.9% | 975 | 26.2% |
| `TotalAssetsLessCurrentLiabilities` | 2,800 | 75.2% | 2,812 | 75.5% |
| `AverageNumberEmployeesDuringPeriod` | 3,005 | 80.7% | 3,005 | 80.7% |

## Archive manifest

| Archive | Members | Observations | Complete |
|---|---:|---:|:---:|
| `Accounts_Monthly_Data-February2022.zip` | 223,041 | 13,293 | partial |
| `Accounts_Monthly_Data-January2022.zip` | 249,427 | 13,358 | partial |

## Limitations

- Archives before 2019 remain unvalidated. Do not describe this dataset as 2008–2025 until reconnaissance is run around 2010, 2013, and 2016.
- XML filings are counted but not extracted; the validated 2019–2025 samples were overwhelmingly iXBRL.
- Currency units are resolved in LONG. Non-GBP monetary observations are retained and flagged here; WIDE excludes them by default rather than converting currency.
- Non-zero scale is handled and synthetically tested, but no scale variation appeared in the real recon samples.
- Employee-count availability changes sharply from about 24% in 2019 to 33% in 2020 and 85% in 2021. Treat this as a reporting-regime break, not company signal.
- Equity has a greater-than-10-percentage-point monthly fill-rate range in the panel check, so its missingness is non-random.
- Creditors are dimensionally dominant: genuine non-dimensional totals were about 4% in the two-archive production sample. The panel check's roughly 52% rate includes a legacy dimensional fallback and is not a total benchmark. A null WIDE Creditors total is therefore expected; use curated member columns.
- Restatements remain separate LONG observations. Predictive WIDE publication must use `as_first_reported`; `latest` contains look-ahead information.
