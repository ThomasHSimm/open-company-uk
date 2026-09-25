# WIDE rebuild verification (Task 3, Kaggle publication chapter)

Full-scale rerun of `pivot_duckdb` (`--engine duckdb`), both modes, over the complete
152-archive corpus, with the updated column map (Task 1's Creditors maturity columns) and
the approved employee cut-off (Task 2, 250). Each run capped via `systemd-run --scope
-p MemoryMax=24G`.

## A bug found and fixed during verification, before publication

Checking "provenance matches WIDE one-to-one" (a stated Task 3 requirement) turned up a
genuine, pre-existing defect shared by **both** pivot engines (the sample-scale
`pivot.pivot_long` and the out-of-core `ooc.pivot_duckdb`): a source fact whose filed value
was blank/unparseable (`raw_value = '-'`, `numeric_value = NULL` — a real, legitimate Stage 1
shape, not corrupted data) was still eligible to win the source-ranking for a cell. If that
was the only, or the highest-ranked (e.g. most recent, under `latest` mode), fact for a key,
it would **shadow a real value from a different filing**, producing a `NULL` WIDE cell even
though a usable value existed elsewhere. Traced from 10,382 provenance rows with no matching
non-null WIDE cell for `Creditors` alone (as_first_reported); every other mapped column showed
the same pattern.

**Fix:** both `pivot._reduce_to_cells` and `ooc._cells_with_sql` now exclude
`numeric_value IS NULL` from the candidate pool before ranking, so a blank fact can never win
a slot a real value could otherwise fill. Covered by a new regression test
(`test_null_valued_fact_does_not_shadow_a_real_value`) exercising both engines. This is a
genuine data-quality improvement to what gets published, not just a bookkeeping fix — it was
applied to both engines to keep them equivalent (the existing `pivot_duckdb`-vs-`pivot_long`
equivalence tests depend on this).

Both WIDE files were rebuilt again after this fix; the numbers below are from the
**post-fix** rebuild.

## Row counts

| Mode | WIDE rows | Provenance rows |
|---|---:|---:|
| `as_first_reported` | 33,461,467 | 193,433,750 |
| `latest` | 36,623,698 | 220,404,940 |

Compared with the pre-Kaggle-chapter build (33,512,909 / 36,709,276 WIDE rows): the net
change is small and has two explained causes, not one:

1. **Increase** from the two new Creditors maturity columns (Task 1) — some company-periods
   now qualify for a WIDE row via `creditors_within_one_year`/`creditors_after_one_year`
   alone.
2. **Decrease** from the null-shadowing fix above — company-periods whose *only* target-concept
   fact was a blank/dash value no longer produce an all-null WIDE row, since that fact is no
   longer eligible to be selected at all.

The employee cut-off (Task 2) does not change row counts — it only nulls a value and sets a
flag within an already-existing row.

## Provenance-vs-WIDE alignment (one-to-one)

Every mapped column has **zero** provenance rows without a matching non-null WIDE cell,
**except** `AverageNumberEmployeesDuringPeriod` (1,225 such rows in `as_first_reported`) — and
that gap is exactly the intended employee cut-off behaviour: those are winning employee facts
whose value was nulled for being a GBP-tagged monetary outlier (Task 2), not a data-quality
defect. `employees_unit_anomaly = 1` identifies every one of them.

## Other checks

- **Company numbers**: `VARCHAR`/string dtype confirmed via schema; sample rows with leading
  zeros (e.g. `00000086`) round-trip unchanged.
- **GBP-only monetary values**: guaranteed by construction (`usable_filter` requires
  `currency = 'GBP'` for every non-employee mapped column); spot-checked by construction, not
  just by filter text.
- **No unresolved-unit facts published**: zero published monetary cells trace back to a source
  fact with a missing/unresolved `unit` (checked by joining every non-employee provenance row
  back to its source fact in LONG).

## Re-verification after the dash-nil fix and cutoff removal

See `docs/accounts-dash-nil-fix.md` for the change itself. WIDE was rebuilt a third time
(both modes, both engines, same `systemd-run` cap) and every Task 3 check above was rerun:

- **Row counts**: `as_first_reported` 33,513,017; `latest` 36,710,673 — both restored to
  (and matching almost exactly) the numbers from *before* the null-shadowing fix, since a
  dash is no longer excluded from the candidate pool at all — it now legitimately wins as 0
  instead of leaving a company-period with no other target-concept fact absent from WIDE.
- **Provenance-vs-WIDE alignment**: now **zero gap on every column, including
  `AverageNumberEmployeesDuringPeriod`** — the one remaining gap noted above was entirely the
  cut-off's nulling, which no longer exists.
- **Company numbers, GBP-only, no unresolved-unit facts**: re-confirmed, unchanged from
  above.
- **Starter notebook**: re-executed end-to-end against the updated `kaggle/` files
  (`jupyter nbconvert --execute`) to confirm it still runs cleanly against the new numbers.
- **Staging guard**: rerun against both `kaggle/` and `kaggle-long/`, passed.
