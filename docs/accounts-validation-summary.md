# Accounts parser validation summary

Written for the future site-restructure branch's `docs/site/datasets/accounts-validation.qmd`
(that branch doesn't exist yet, so this stands alone until it does — see
`docs/accounts-parser-check.md` for full detail and methodology on every figure below).

## What this validates

Three parsers — this project's own regex-based extractor ("ours"), the general-purpose
`ixbrlparse` library, and Arelle (a full standards-compliant XBRL processor) — were run on
the same fixed samples of real Companies House accounts filings, under controlled, fair
timing conditions (identical input, warm-up runs excluded, 3 repeats, median reported). Where
ours and `ixbrlparse` disagreed, Arelle's independent extraction was used as a tie-breaker to
determine which side was actually correct.

## Measured speed

| Parser | ms/filing (e2e, 1 worker) | Relative to ours |
|---|---|---|
| Ours | 0.65 | 1x |
| `ixbrlparse` | 7.7 | ~12x slower |
| Arelle | ~992 (~1 second) | ~1,520x slower |

Projected to the full 35,806,258-filing archive, at measured 8-worker throughput: **~2.1
hours** (ours) vs **~1.4 days** (`ixbrlparse`) vs **~94.6 days** (Arelle — not viable at this
scale under any parallelism available).

## Measured accuracy

**99.999% agreement on numeric facts** (dashes excluded — both other parsers resolve a dash
to zero immediately, this pipeline defers that to pivot time; a design difference, not a
disagreement), 95% CI [99.995%, 100%], every year 2014–2026 individually at 99.9–100%. This
is the number that matters for the published WIDE table, which only ever holds numeric
cells. An unfiltered, all-facts comparison (including non-numeric text) shows 89.5%
agreement — most of that gap is a deliberate design choice (raw displayed text vs.
Transformation-Registry-normalised text for non-numeric facts), not a parsing error.

## Defects found and fixed

- **Prefix bug**: a hardcoded `ix:` namespace prefix meant any filing binding inline-XBRL to
  a different prefix (or the default namespace) silently extracted zero facts. Fixed.
  Estimated footprint: ~291,802 filings, concentrated 2014–2022.
- **Comma-as-decimal number formats** (`numdotcomma`/`numcomma`/`numspacecomma`/
  `numcommadecimal`, both `ixt` and `ixt2` registry namespaces): silently misread by roughly a
  factor of 100–1,000 (e.g. a real filing's `CashBankOnHand` fact read as `3.349` instead of
  the correct `3349`). Fixed, verified against real archive data.
- **Plain-XML filings** (301,141 archive-wide, 0.84% of the archive): previously skipped
  entirely; now extracted via an `ixbrlparse`-based adapter, verified against Arelle on 186
  real filings with 100% agreement on shared facts (5,845/5,845) and zero facts Arelle found
  that the adapter missed.

## Defects found, deferred by reasoned decision

- **Nested facts** (an inner fact lost or merged into an outer fact's text): affects 9.85% of
  filings archive-wide, but only 0.0015% of numeric facts and zero published WIDE columns.
  Confirmed by Arelle siding with `ixbrlparse` in ~100% of these cases (ours is the outlier
  here, not a matter of interpretation). Not fixed — the rate didn't clear the bar for the
  engineering cost.
- **Continuations** (`ix:continuation` chains — only the first text fragment kept): also
  non-numeric-only, and the published `kaggle-long/` dataset's structured-metadata allowlist
  doesn't currently include any concept long enough to need continuation. Not fixed.

## What's still not captured, by design

Multi-member and typed-member dimensional contexts (25.3% and 20.1% of all filings
respectively, 37.9% combined) are skipped entirely — not a bug, a scope boundary. A
personal-data check on typed-member values found every one sampled to be code-shaped (short
sequence numbers), not name-shaped — no personal-data concern identified, but this doesn't
change the scope decision.

## v1 → v2 change

The fixed parser (comma-decimal formats, plain-XML via ixbrlparse) was run against the full
archive and diffed directly against the original build — no sampling. Full detail, query
methodology, and a resolved contradiction the maintainer caught and asked to be traced to
ground truth (not glossed over): `docs/accounts-parser-check.md` §1 erratum and §6.5.

- **334,503 filings gained real facts** that had zero rows before: 273,418 from the new
  plain-XML route, 61,085 from the prefix-bug fix — a **directly-measured** figure that
  corrects an earlier sample-based estimate (≈291,802). That estimate's error was traced to
  its actual root cause, not just re-estimated: the census data it was built from was never
  regenerated after a namespace-detection regex fix was applied to the script, so every
  classification it used — even after the "fix" — was computed by the stale, pre-fix logic
  the whole time. Corroborated two independent ways: the direct diff, and a full-archive
  check confirming **zero `.html` filings have zero rows in v2, in any year** — the prefix
  fix is complete, with no residual gap.
- **1,096 facts changed value** on keys both versions already had — the comma-decimal fix,
  confirmed against real examples (e.g. a `CashBankOnHand`-family fact read as `3.349`
  before, correctly `3349` after).
- **A second, real bug was found and fixed while tracing published values that disappeared
  between v1 and v2** (WIDE "newly null" cells, 11–73 per column — the maintainer flagged
  that a published value vanishing needs an explanation, not a shrug). Root cause: a
  hyphenated format spelling (`num-dot-decimal`, the same family as the far more common
  `numdotdecimal`) wasn't recognised, silently nulling 540 facts across 3 archive months that
  had parsed correctly even before this chapter's fixes. Fixed, tested against the real
  markup that found it, and the 3 affected months re-extracted. **Every "newly null" cell,
  on every column, in both modes, is now zero** — fully explained, not just reduced.
- **Zero regressions**: every fact present in v1 is still present in v2 — re-verified after
  the hyphen-format fix.
- **WIDE**: ~61,000 newly-filled cells per column in `as_first_reported` mode (matching the
  prefix-fix filing count almost exactly — each recovered filing becomes its own first-ever
  row). `latest` mode shows larger "changed" counts, explained by newly-recovered filings
  sometimes becoming the new most-recent-filing winner for a company-period, not by any new
  defect.
- **Restatement rate**: unchanged, 9.36% before and after (recomputed after the
  hyphen-format fix). **Fill rates**: unchanged to within 0.3 percentage points on every
  column.
