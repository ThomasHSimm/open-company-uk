# Accounts restatement rate (month-ordered running tally)

Scope: **2022-2023 (continuous, 24 archives)** (continuous months only — a gap between archives makes "restated later" indistinguishable from "not resampled"; never aggregate this with the lone gap-separated months).

Same definition as the panel check (`docs/panel-check.md`'s 7.94%): non-dimensional (`dimension IS NULL`), `status == 'selected'` numeric facts for the nine target concepts, keyed by (company, period_end, concept). "Repeated" means the key appears in >=2 filings within scope; "disagree" means a later filing reports a different scale-normalised value than the first one seen.

- Distinct keys: 49,159,979
- Repeated keys: 13,553,889
- Disagree: 1,074,273 (7.93% of repeated)

## By concept

| Concept | Repeated keys | Exact match | Disagree |
|---|---:|---:|---:|
| `AverageNumberEmployeesDuringPeriod` | 2,134,380 | 1,966,164 (92.12%) | 168,216 (7.88%) |
| `CashBankOnHand` | 1,072,684 | 1,049,073 (97.80%) | 23,611 (2.20%) |
| `Creditors` | 106,740 | 102,175 (95.72%) | 4,565 (4.28%) |
| `CurrentAssets` | 2,067,555 | 1,917,486 (92.74%) | 150,069 (7.26%) |
| `Debtors` | 707,807 | 681,185 (96.24%) | 26,622 (3.76%) |
| `Equity` | 2,488,093 | 2,284,386 (91.81%) | 203,707 (8.19%) |
| `NetCurrentAssetsLiabilities` | 2,196,301 | 1,942,858 (88.46%) | 253,443 (11.54%) |
| `PropertyPlantEquipment` | 690,786 | 674,217 (97.60%) | 16,569 (2.40%) |
| `TotalAssetsLessCurrentLiabilities` | 2,089,543 | 1,862,072 (89.11%) | 227,471 (10.89%) |

Overall rate (7.93%) closely matches the panel check's 7.94% on an independent pipeline, which supports both. `Creditors`' repeated-key count (106,740) is far below the panel check's 1,393,444: the panel check's legacy pipeline promoted a single non-conflicting *dimensional* value to stand in for a missing total (a "legacy dimensional fallback"); this computation strictly requires `dimension IS NULL`, matching the task's definition and the current archive's documented ~4% genuine non-dimensional Creditors total rate. Use the curated member columns for Creditors, not this total-only comparison.
