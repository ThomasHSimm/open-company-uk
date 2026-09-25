# Creditors maturity reconciliation (Task 1, Kaggle publication chapter)

Computed via `ooc.creditors_maturity_reconciliation_duckdb`, over the full 152-archive
corpus, capped at 20 GB (`systemd-run --scope -p MemoryMax=20G`).

## Method

Every filing where a non-dimensional Creditors total (`dimension IS NULL`) and at least one
`MaturitiesOrExpirationPeriodsDimension` component exist for the same
(company, period_end, source_year, source_month, source_archive, source_member) key. Bucketed
in priority order:

1. `incomplete_axis` — exactly one of `WithinOneYear`/`AfterOneYear` present.
2. `match` — component sum within tolerance of the total (max(£1, 1e-6 × |total|), same
   tolerance as `qa.total_component_reconciliation`).
3. `sign_flip` — component sum within tolerance of *negative* the total.
4. `other`.

## Result

3,998 comparisons total (a small fraction of the corpus — most filings report the maturity
split *without* also tagging a non-dimensional total, which is exactly why the total is ~96%
null and already documented as unreliable).

| Bucket | Count | Share |
|---|---:|---:|
| `incomplete_axis` | 3,161 | 79.1% |
| `other` | 825 | 20.6% |
| `match` | 12 | 0.3% |
| `sign_flip` | 0 | 0.0% |

## What's actually driving `other`

`other` looked concerning on its own — mismatches up to 37× the total — so it was investigated
further rather than taken at face value. Restricting to the 833 filings where *both*
`WithinOneYear` and `AfterOneYear` are present (`match` + `other` here, a slightly different cut
than the priority-ordered buckets above):

| Explanation | Count | Share of 833 |
|---|---:|---:|
| Genuinely reconciles (total = within + after) | 11 | 1.3% |
| Total equals `WithinOneYear` alone | 669 | 80.3% |
| Total equals `AfterOneYear` alone | 97 | 11.6% |
| Unexplained | 56 | 6.7% |

**Finding:** the non-dimensional Creditors "total" fact is frequently a mislabelled duplicate
of a single maturity bucket (usually `WithinOneYear`) rather than a genuine within+after sum —
not a sign or scale corruption. This does not implicate the maturity member values themselves;
it is a further reason the bare Creditors total is unreliable and the maturity columns are the
right unit for users to rely on.

## Decision (per the stated rule)

`sign_flip` is 0 — not just negligible but absent — and disagreements are dominated by
`incomplete_axis` (79.1% of all comparisons, and the `other` bucket's own root cause does not
implicate the individual maturity values). **Proceeding to add the maturity columns**:

- `creditors_within_one_year` (`Creditors` × `MaturitiesOrExpirationPeriodsDimension` ×
  `WithinOneYear`)
- `creditors_after_one_year` (`Creditors` × `MaturitiesOrExpirationPeriodsDimension` ×
  `AfterOneYear`)

The financial-instrument current/non-current axis
(`FinancialInstrumentCurrentNon-currentDimension`) is deliberately kept out of v1 and not
combined with the maturity columns — it is a parallel, independent split of the same Creditors
concept (see `docs/accounts-qa.md`'s member histogram), and mixing two orthogonal dimensional
axes into one WIDE table without a clear precedence rule would produce cells that silently mix
two different classification schemes. This is a scope decision, not a data-quality finding;
revisit only if a specific downstream use needs it.

The bare `Creditors` total column is kept (not dropped) for continuity with the existing WIDE
schema, but the dataset card must state plainly that it is sparse by design and, per this
report, sometimes actually equals a maturity component rather than a true total — users should
rely on the maturity columns, not the total.
