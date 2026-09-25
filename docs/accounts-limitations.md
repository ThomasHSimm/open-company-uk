# Scope and limitations of the accounts archive

This closes out the full-history accounts backfill: continuous monthly coverage from
2014-01 through 2026-08 (152 archives), extracted and computed within a ~30 GB machine's
memory throughout. It states what was kept, what was skipped, and what is and isn't
validated — read this before citing any number from the accounts archive. (Supersedes the
prior 30-archive-sample chapter; see "Where the numbers come from" for which reports moved
and which stayed as validation cross-checks.)

The archive keeps every concept, all-fact, exactly as read (verified: no non-numeric fact
carries a coerced numeric value). Only the nine core financial concepts are validated for
coverage and internal consistency; the remaining ~4,446 concepts are captured-as-read and
unvalidated — rare and single-filer concepts especially.

Non-numeric text (54.1% of observations) is retained untriaged: statutory boilerplate,
structured metadata (filing dates, registered number, names, filing software), and
categorical flags sit together, kept in full rather than pruned (most boilerplate is
near-identical across filings and compresses well, so its on-disk cost is modest).

## Coverage: continuous 2014-01 through 2026-08

152/152 requested months present and manifest-complete, 0 absent, 0 failed (see
`docs/accounts-coverage.md`). **Effective start year is 2014, not the full 2010+ range CH
technically serves**, a deliberate human decision based on live reconnaissance: Companies
House's iXBRL adoption was gradual, not a hard cutover — 0% of filings were iXBRL in 2010,
rising through roughly 3%–56% across 2011–2013, and reaching ~97% by 2014 and beyond. Pre-2014
months exist on the server but would return mostly-empty extractions dominated by plain-XML
filings the pipeline does not target; they were deliberately never fetched. If a future task
needs 2010–2013 coverage, treat it as a distinct, much lower-fill-rate regime requiring its
own validation, not a simple range extension.

**Regex-vs-lxml parser-agreement audit** (`scripts/parser_agreement_audit.py`, run against
real downloaded archives, not fixtures): the production `IX_FACT_RE` regex was validated
against 2019–2025 markup only, so early-year filings from unfamiliar filing software were an
open risk. Samples: 2013 (300 filings, real archive) → 98.0% exact fact-set agreement; 2022
(200–500 filings) → 82.5%. **Zero disagreements in either sample touched any of the nine
target concepts** — all were either CRLF/LF line-ending normalisation (benign, XML-spec
mandated) or a confirmed, narrow regex limitation: a non-greedy `ix:nonNumeric` match
truncates when a same-named element is nested inside it (e.g. a date fact embedded mid-
sentence in a narrative disclosure), which only affects non-numeric narrative concepts, never
the nine numeric core concepts this archive validates. Not fixed (out of the scope-discipline
for this chapter); flagged here for anyone extending non-numeric concept coverage.

Because the whole 2014–2026 span is now gap-free, longitudinal metrics (restatement,
`as_first_reported`) are valid across the **entire archive**, not just a sub-range — see
`docs/accounts-restatement-2014-2026.md`: **9.27%** of repeated (company, period_end,
concept) keys disagree with the first-seen value (178,916,771 distinct keys, 115,847,972
repeated). This is somewhat higher than the 2022–2023-only cross-check (7.93%, closely
matching the independent panel check's 7.94%) — plausible, since a 12-year span gives every
key far more opportunity to be restated than a 2-year window; both figures use the identical
definition and validate each other.

Known data quirks, handled downstream (Stage 2), not in the archive: employee-count facts
tagged with a GBP unit instead of a plain count (7,751,582 of ~9.8M+ employee facts, median
value 1.0 — real headcounts mis-tagged; only 281 facts ≥100,000 are a genuine monetary-value
contamination tail, to be bounded by value, not unit). Employee coverage has a 2020→2021
reporting-regime break. Creditors is heavily dimensional (only ~22% of non-dimensional
totals reconcile to their component sum, see below) — use the maturity/instrument-type split
via the curated member columns, not the bare total. Restatements affect ~9% of repeated
figures; use `as_first_reported` for predictive work.

**New at full scale — numeric facts with a missing/unresolved unit: 36,119** (0 non-numeric
facts carry a coerced numeric value, so read-correctness elsewhere is clean). This did not
appear as a finding at 30-archive scale; concentrated in `CalledUpShareCapital` (5,251),
`Debtors` (4,444), `ProfitLossAccountReserve` (3,754), and a long tail of mostly legacy/
alternate concept names (`CreditorsDueWithinOneYear`, `CashBankInHand`,
`ShareCapitalAllottedCalledUpPaid`, etc. — see `docs/accounts-concept-inventory.md` for the
full table). These look like older/alternate-taxonomy concept names from the pre-2014-
adjacent years that never got a resolvable unit tag; flagged here as a data-quality item, not
investigated or fixed further (out of scope for this chapter — none of the nine target
concepts are meaningfully affected: their gaps are 0–20 rows each against tens of millions of
observations).

**Total-vs-component reconciliation, now at real fractional rates (a bug fix this chapter,
see `docs/AUDIT.md`):** `AverageNumberEmployeesDuringPeriod` 50.3%, `CashBankOnHand` 38.4%,
`Creditors` 22.1%, `CurrentAssets` 49.9%, `Debtors` 90.3%, `Equity` 94.0%,
`NetCurrentAssetsLiabilities` 40.2%, `PropertyPlantEquipment` 93.6%,
`TotalAssetsLessCurrentLiabilities` 38.1%. The concepts with low agreement are exactly the
ones with the most *parallel* dimensional axes (e.g. Creditors has both a maturity split and
a financial-instrument-type split reported alongside the total) — this is diagnostic only,
not a correction signal; see `docs/accounts-qa.md`'s member-frequency histogram before
reading a low rate as "bad data".

**Pivot cell-count gap between modes narrows at full scale.** At 30-archive/2022-H1 sample
scale, `latest` mode's mapped-cell count ran ~1.8–1.9× `as_first_reported`'s. At full
2014–2026 scale the gap is much smaller — WIDE rows 36,709,276 (`latest`) vs 33,512,909
(`as_first_reported`), a ~1.10× ratio; provenance rows 206,062,454 vs 180,386,377, ~1.14×.
Plausible explanation: over a 12-year span most company-periods eventually accumulate a
first-reported filing too, whereas the 6-month 2022-H1 sample structurally excluded periods
whose *first* filing fell outside the narrow window. Not further investigated; noted as a
scale-dependent characteristic rather than a discrepancy.

## Kaggle publication chapter (2026-09-24)

Closes the accounts chapter with a publishable Kaggle dataset. Two data flaws in the WIDE
table were investigated and resolved (one added columns, one added a cut-off + flag); a
null-shadowing bug found during verification was fixed in both pivot engines; and a
privacy-reviewed public LONG dataset was built alongside WIDE. Full detail in each linked
report; `docs/AUDIT.md` has the complete chapter narrative including the bug fixes.

**Creditors maturity columns — added.** A full-corpus reconciliation
(`docs/accounts-creditors-maturity-reconciliation.md`) found `sign_flip` disagreements
completely absent (0 of 3,998 comparisons) and disagreements dominated by `incomplete_axis`
(79.1%) — the decision rule's threshold for safely adding the split. Added
`creditors_within_one_year` and `creditors_after_one_year` to the WIDE map. A secondary
finding narrows what the bare `Creditors` total means: even when a non-dimensional total *is*
filed alongside the maturity split, it frequently equals just one maturity bucket (80.3% of
such cases equal `WithinOneYear` alone) rather than a genuine sum — the total was already
documented as sparse (~4%) and is now understood to be unreliable even when present. The
financial-instrument current/non-current axis remains deliberately out of v1 (a parallel,
independent split of the same concept — mixing two dimensional axes into one WIDE table would
produce ambiguous cells).

**Employee GBP-unit cut-off — human-approved at 250.**
`docs/accounts-employee-unit-cutoff.md`: comparing the GBP-tagged and `pure`-tagged
non-dimensional employee-fact distributions, the task's example method (99.9th percentile of
`pure`) gives a cut-off of 250. GBP-tagged values ≤250 are kept as real (mislabelled)
headcounts; values >250 (2,262 of 7,715,981 GBP-tagged facts, 0.029%) are set to `null` in
WIDE only — Stage 1/LONG is unaffected. A new `employees_unit_anomaly` WIDE column flags every
row whose winning employee fact was GBP-tagged (kept or nulled), so both cases are
identifiable. This supersedes the old 100,000 ad-hoc threshold (which nulled almost nothing —
275 facts, 0.004%) referenced earlier in this document.

**A null-shadowing bug, found and fixed in both pivot engines.** Verifying "provenance matches
WIDE one-to-one" (a stated rebuild check) surfaced a real, pre-existing defect: a source fact
with a blank/unparseable value (`raw_value='-'`, `numeric_value=NULL` — a legitimate Stage 1
shape) could still win a cell's source ranking and shadow a real value from a different
filing, producing a `null` WIDE cell where a usable value existed elsewhere. Fixed in both
`pivot.pivot_long` and `ooc.pivot_duckdb` (excluded from the candidate pool before ranking);
full detail and the resulting row-count changes in
`docs/accounts-wide-rebuild-verification.md`. This is a genuine data-quality improvement to
what's published, not just a bookkeeping fix.

**Superseded before upload: employee cut-off removed, dashes now treated as nil.**
`docs/accounts-dash-nil-fix.md` records two corrections applied after the two paragraphs
above and before publication:

- The 250 employee cut-off is **removed**. Every `AverageNumberEmployeesDuringPeriod` value
  is kept exactly as filed, regardless of unit or size — `employees_unit_anomaly` remains
  (1 for a GBP-tagged winning fact) but is now purely diagnostic and never alters a value.
- The null-shadowing fix above was the right instinct for genuinely unparseable text but
  wrong for one specific shape: **a bare dash (`-`, `–`, `—`) in a UK company account means
  nil, not "unknown"**. Excluding it from the candidate pool (as the null-shadowing fix did)
  let a *different* filing's value win instead of treating the dash as the zero it
  represents. Both pivot engines and both restatement engines now coalesce a dash to `0` and
  let it compete in ranking/comparison normally — a dash in the winning filing legitimately
  produces a `0` cell, rather than being skipped.
- Impact, diffed cell-by-cell against the pre-fix build: 1,936,525 WIDE cells changed under
  `as_first_reported` (1,936,433 `null`→`0`, 92 real-value→`0`) and 3,444,428 under `latest`
  (3,310,785 `null`→`0`, 133,643 real-value→`0`) — every changed cell falls into exactly one
  of those two categories, nothing unexplained. The restatement rate moved from 9.27% to
  **9.36%** on the same continuous 2014–2026 span, consistent with dash facts now
  legitimately counting as first-seen values that can later be restated.

**Restatement rate by year.** `docs/accounts-restatement-by-year.md`: the 9.27% all-span rate
is not flat — most years run 7.9–10%, but keys first reported in 2016–2017 restate distinctly
more (13–15%), plausibly reflecting less-settled filer-software conventions in the earliest
near-universal-iXBRL years, the longest possible window to accumulate a restatement, or both
(not distinguished further here). Computed *before* the dash-nil fix below (all-span rate
9.27%, not the post-fix 9.36%); the by-year breakdown was not regenerated after that fix, so
treat its exact percentages as indicative rather than final — the shape of the finding
(2016–2017 elevated, the rest of the span in a narrower band) is expected to hold.

**Public LONG dataset — personal data removed, published separately.** The private
`data/accounts/long/` archive (used to build WIDE) contains personal data from the all-fact
capture — names, the signing director, addresses, director loans and remuneration — and stays
private, never published; the earlier statement in this document that "financials are not
personal data" was scoped to the validated nine-concept WIDE output, not to this private
archive. A maintainer-approved filter (`docs/accounts-public-long-concepts.md`: a 95-concept
numeric denylist covering director/officer/key-management/related-party/remuneration/trustee
concepts, 0.44% of numeric observations; a 17-concept non-numeric allowlist of structured
fields only, everything else non-numeric dropped) produces `kaggle-long/`, one Parquet per
year, 1,301,140,617 rows total — built as a DuckDB filter over the existing per-month
Parquets, never re-extracted. The Open Government Licence does not cover personal data, which
is part of why this split exists. An automated staging guard
(`scripts/kaggle_staging_guard.py`) independently re-scans every published Parquet in both
`kaggle/` and `kaggle-long/` against the same lists (plus an independently-derived
person-name pattern) as the last check before upload.

## What was kept and what was skipped this chapter

- Kept: all-fact extraction scope (numeric and non-numeric, unchanged), `--disposable-store`
  for the entire backfill run (kept peak transient disk to ~1 archive rather than a
  multi-hundred-GB monolith), the two-location download fallback (now covered by a dedicated
  test), a persistent manifest (`data/accounts/manifest.sqlite`) separated from the
  disposable per-month scratch stores so resumability survives store deletion.
- Reclaimed: the 221 GB monolithic SQLite scratch store from the prior chapter was exported
  (manifest rows only, `export-manifest` CLI command) then deleted, after a final
  manifest-vs-Parquet `verify` re-check (30/30 passed) and explicit human confirmation.
- Skipped, deliberately, as explicit human/later calls: switching `accounts.kinds` to
  `numeric-only`; extending coverage below 2014 (see the iXBRL-adoption finding above); the
  Stage-2 per-model table; fixing the nested-same-tag-name regex limitation (confined to
  non-numeric narrative concepts, zero target-concept impact); investigating the 36,119
  numeric-unit-gap finding further; any publishing/Kaggle step.
- Built this chapter: an out-of-core DuckDB engine (`ukcompany/accounts/ooc.py`,
  `--engine duckdb` on `pivot`/`restatement`/`qa`) as an *additive* alternative to the
  sample-scale Polars implementations, which do not scale past roughly 30 archives on this
  machine (see `docs/AUDIT.md` for the OOM evidence and the engine's internal bugs found and
  fixed during validation). The Polars engines remain the default and are unchanged.

## Where the numbers come from

- Per-concept read-correctness audit, numeric/non-numeric split, employee GBP-unit anomaly,
  numeric-unit-gap finding: `docs/accounts-concept-inventory.md` (`companies` is
  approximate — `approx_n_unique`, ~2% typical error — not an exact count; an exact
  cross-file count does not fit in memory at 4,455-concept scale).
- Member histogram and total-vs-component reconciliation, full corpus, via the DuckDB
  engine: `docs/accounts-qa.md`.
- Restatement rate, full continuous 2014–2026 span, via the DuckDB engine:
  `docs/accounts-restatement-2014-2026.md`. The earlier `docs/accounts-restatement-
  2022-2023.md` (Polars running-tally, 7.93%) is kept as an independent cross-check against
  the panel check's 7.94%, not superseded numerically — both use the identical definition.
- WIDE pivot + cell-level provenance, both modes, full corpus, via the DuckDB engine:
  `data/accounts/accounts-wide-{as_first_reported,latest}.parquet` and
  `accounts-wide-provenance-{as_first_reported,latest}.parquet`.
- Manifest-vs-Parquet completeness: `docs/accounts-verification.md` (152/152 passed).
- Coverage (present/absent/failed months, real span): `docs/accounts-coverage.md`.
- Creditors maturity reconciliation: `docs/accounts-creditors-maturity-reconciliation.md`.
- Employee GBP-unit cut-off derivation: `docs/accounts-employee-unit-cutoff.md`.
- WIDE rebuild verification (row counts, provenance alignment, the null-shadowing fix):
  `docs/accounts-wide-rebuild-verification.md`.
- Restatement rate by year of first filing: `docs/accounts-restatement-by-year.md` (pre-dates
  the dash-nil fix; see below).
- Public LONG concept lists (maintainer-approved) and Kaggle staging safety checks:
  `docs/accounts-public-long-concepts.md`, `docs/accounts-kaggle-safety-checks.md`.
- Employee cut-off removal and dash-means-nil fix (supersedes the cut-off described above):
  `docs/accounts-dash-nil-fix.md`.
