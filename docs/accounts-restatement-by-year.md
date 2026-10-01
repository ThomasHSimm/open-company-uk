# Restatement rate by year of first filing (Task 4, Kaggle publication chapter)

Same definition as `docs/accounts-restatement-2014-2026.md` (non-dimensional, `status =
'selected'`, numeric, the nine target concepts, keyed by (company, period_end, concept)),
grouped by the year each key was **first** reported rather than aggregated across the whole
span. Computed via `ooc.restatement_rate_by_year_duckdb` over the full corpus, capped at
20 GB peak. Report only — nothing is corrected.

| First seen | Distinct keys | Repeated | Disagree | Rate |
|---|---:|---:|---:|---:|
| 2014 | 7,730,306 | 3,563,559 | 347,111 | 9.74% |
| 2015 | 5,659,323 | 4,140,710 | 413,590 | 9.99% |
| 2016 | 6,390,394 | 4,443,473 | 671,812 | 15.12% |
| 2017 | 10,470,216 | 6,599,203 | 879,791 | 13.33% |
| 2018 | 13,913,555 | 9,385,352 | 907,592 | 9.67% |
| 2019 | 14,025,426 | 10,716,103 | 959,277 | 8.95% |
| 2020 | 14,319,347 | 10,968,276 | 952,450 | 8.68% |
| 2021 | 19,453,151 | 15,154,985 | 1,200,284 | 7.92% |
| 2022 | 17,917,566 | 13,302,645 | 1,087,501 | 8.18% |
| 2023 | 17,409,340 | 13,478,076 | 1,125,913 | 8.35% |
| 2024 | 19,716,135 | 14,862,096 | 1,321,587 | 8.89% |
| 2025 | 20,051,413 | 9,064,529 | 859,133 | 9.48% |
| 2026 | 11,860,599 | 168,965 | 14,715 | 8.71% |

## Reading this honestly

Early years (2016–2017) restate distinctly more than the rest of the span (13–15% vs a broad
7.9–10% band elsewhere) — not a smooth "early years are always higher" story. 2014–2015 are
close to the all-span average, and the rate does **not** monotonically decline as filing
years get more recent. **2026 is the current, still-open year**: only 168,965 of 11,860,599
keys have had a chance to repeat at all, so its 8.71% is based on a much smaller, less mature
sample and should not be read as comparable to a fully-elapsed year.

Plausible contributors to the 2016–2017 bump (not verified further here — a report, not an
investigation): those are the earliest years with near-complete iXBRL adoption (see
`docs/accounts-limitations.md`'s adoption-curve finding), so filer-software and taxonomy
conventions were less settled; they have also had the longest possible window (up to 10 years)
to accumulate a comparative restatement by the time this corpus was extracted. Both are
plausible; distinguishing them was out of scope for this task.

The all-span aggregate (9.27%, `docs/accounts-restatement-2014-2026.md`) is not a simple
average of this table — it aggregates at the key level across the whole span, so years with
more distinct keys (e.g. 2021–2025) dominate it more than 2016–2017 do.
