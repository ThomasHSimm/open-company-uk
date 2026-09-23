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
