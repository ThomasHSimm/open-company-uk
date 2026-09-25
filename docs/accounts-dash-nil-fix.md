# Dash-means-nil fix and employee cutoff removal (pre-Kaggle-upload correction)

Two changes applied before upload, both WIDE/restatement-only — no re-extraction, Stage 1
(LONG) is untouched in every case.

## 1. Employee cutoff removed

The 250 cut-off from `docs/accounts-employee-unit-cutoff.md` (nulling GBP-tagged employee
values above 250) has been **removed**. Every `AverageNumberEmployeesDuringPeriod` value is
now kept exactly as filed, regardless of unit or size. `employees_unit_anomaly` is
unchanged in meaning: still 1 for a GBP-tagged winning fact, 0 otherwise, `null` if no
employee fact was selected — now purely diagnostic, never altering a value.

## 2. Dash means nil, not "no value"

**The problem this replaces.** A numeric fact filed as a bare dash (`-`, `–`, or `—`) has
`numeric_value = NULL` in the LONG archive — a real, legitimate Stage 1 shape (Stage 1 never
guesses; an unparseable raw value stays `NULL`). The previous fix
(`docs/accounts-wide-rebuild-verification.md`) excluded these facts from the pivot's
candidate pool entirely, so that a genuinely blank/unparseable fact could never *shadow* a
real value from a different filing. That was the right instinct for genuinely unparseable
text, but wrong for a dash specifically: **a dash in a UK company account means nil (zero)**,
not "unknown" — excluding it was a workaround that let a different filing's value win
instead of treating the dash as the real value it represents.

**The fix.** In both pivot engines (`pivot.pivot_long`'s `_reduce_to_cells`,
`ooc.pivot_duckdb`'s `_cells_with_sql`) and both restatement engines
(`qa.restatement_rate_over_parts`, `ooc.restatement_rate_duckdb` and
`restatement_rate_by_year_duckdb`), a fact with `raw_value` in `{-, –, —}` is now coalesced to
`numeric_value = 0` and competes in ranking/comparison on equal footing with every other
fact — a dash in the winning filing legitimately produces a `0` cell (or counts as a genuine
`0` first-seen value in restatement), rather than being skipped in favour of another filing's
number. Regression-tested in both engines and both pivot modes
(`test_dash_in_later_filing_wins_latest_as_zero`,
`test_dash_in_original_filing_wins_as_first_reported_as_zero`,
`test_restatement_treats_dash_as_zero_in_both_engines`).

## Impact: how many WIDE cells changed

Diffed the pre-fix and post-fix `as_first_reported`/`latest` WIDE files cell-by-cell on the
12 non-employee mapped columns (the employee column is excluded from this table because its
change is confounded with the cutoff removal above, not isolated to the dash fix):

| Mode | Cells changed | `null` → `0` | real value → `0` |
|---|---:|---:|---:|
| `as_first_reported` | 1,936,525 | 1,936,433 | 92 |
| `latest` | 3,444,428 | 3,310,785 | 133,643 |

Every changed cell falls into exactly one of these two categories in both modes — no
unexplained changes. The overwhelming majority (>99.9% under `as_first_reported`, ~96% under
`latest`) are cells that were previously `null` (no other filing had a usable value for that
key) and are now correctly `0`. The smaller "real value → 0" category — far more common under
`latest` (133,643) than `as_first_reported` (92) — is a dash in a *more recent* filing
correctly overriding an earlier real number under most-recent-wins ranking; under
`as_first_reported` this can only happen in the rare case where the *very first* filing for a
key was itself a dash.

`AverageNumberEmployeesDuringPeriod` also changed (481,834 cells under `as_first_reported`,
590,189 under `latest`) — this is dominated by the cutoff removal restoring previously-nulled
values, not isolated further here.

## Impact: restatement rate

Same definition, same continuous 2014–2026 span, before and after:

| | Distinct keys | Repeated | Disagree | Rate |
|---|---:|---:|---:|---:|
| Before (dash excluded) | 178,916,771 | 115,847,972 | 10,740,756 | 9.27% |
| After (dash = 0) | 182,103,810 | 116,932,963 | 10,940,719 | **9.36%** |

A small increase (+0.09 points), consistent with the mechanism: including dash facts adds
~3.2M previously-excluded observations to the key population, some of which are now
`repeated` (paired with a real value elsewhere) and disagree with that non-zero counterpart.
