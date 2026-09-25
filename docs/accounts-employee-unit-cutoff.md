# Employee GBP-unit cut-off (Task 2, Kaggle publication chapter)

Computed via `ooc.employee_unit_distribution_duckdb`, over the full 152-archive corpus,
capped at 20 GB. Scope matches the WIDE total column: `AverageNumberEmployeesDuringPeriod`,
`status = 'selected'`, `dimension IS NULL`.

## Distribution by tagged unit

| Unit | Facts | Median | p99 | p99.9 | p99.99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| `GBP` | 7,715,981 | 1.0 | 12.0 | 47.0 | 18,358.9 | 99,499,000 |
| `pure` | 28,007,617 | 1.0 | 54.0 | 250.0 | 2,342.5 | 7,477,500,000 |

Both distributions have a median of 1.0, supporting the existing finding that most GBP-tagged
facts are genuine headcounts with the wrong unit label, not monetary values. Note the `pure`
distribution's own extreme tail (max 7.48 billion — obviously not a real headcount) is a
separate, pre-existing data-quality issue in the `pure` population; per the task's explicit
instruction, no cap is applied to `pure` values here — large companies genuinely employ
thousands of people, and this task addresses the GBP-tagged population only.

## Cut-off options considered

| Cut-off | Source | GBP kept | GBP nulled | Nulled share |
|---|---|---:|---:|---:|
| 54.0 | p99 of `pure` | 7,709,885 | 6,096 | 0.079% |
| **250.0** | **p99.9 of `pure`** | **7,713,719** | **2,262** | **0.029%** |
| 2,342.5 | p99.99 of `pure` | 7,714,384 | 1,597 | 0.021% |
| 2,000,000.0 | p99.999 of `pure` | 7,715,976 | 5 | 0.0001% |
| 100,000 | prior ad-hoc threshold (pre-Kaggle concept inventory) | 7,715,706 | 275 | 0.004% |

The p99.999 cut-off illustrates why percentile choice can't go arbitrarily high: at that
percentile the `pure` population's own contamination (see above) starts dominating the
threshold, and the cut-off stops filtering anything meaningful.

## Decision — human-approved (2026-09-23)

**Cut-off: 250** (p99.9 of `pure`-tagged values), the task's literal example method.
GBP-tagged employee values ≤ 250 are kept as-is (treated as real headcounts with a mislabelled
unit); values > 250 are set to `NULL` in the WIDE `AverageNumberEmployeesDuringPeriod` column.
2,262 of 7,715,981 GBP-tagged facts (0.029%) are affected.

**Not a unit filter.** No employee value is dropped for carrying a GBP (or any other) unit —
only the small monetary-sized tail above the cut-off is nulled. `pure`-tagged values, and
GBP-tagged values at or below the cut-off, are both kept unchanged. This preserves the ~29%
of employee coverage that is GBP-tagged (dropping it outright, i.e. filtering by unit, was
explicitly ruled out).

**`employees_unit_anomaly` flag.** Every WIDE row whose selected employee fact was GBP-tagged
gets `employees_unit_anomaly = 1` (0 if the winning fact used a different unit; `NULL` if no
employee fact was selected for that row at all). Combined with the value column, a row with
`employees_unit_anomaly = 1` and a non-null employee value is a kept mislabelled headcount; a
row with `employees_unit_anomaly = 1` and a null employee value is one that was nulled by this
cut-off — both are identifiable from the two columns together, per the task's requirement.
Stage 1 (the LONG archive) is unaffected — every value is kept as read; this rule only applies
inside the WIDE pivot.
