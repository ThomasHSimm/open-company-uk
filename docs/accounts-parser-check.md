# Accounts parser check: fairness benchmark, bug fix, and completeness audit

Answers, with evidence, three questions about the accounts iXBRL extractor
(`src/ukcompany/accounts/core.py`): how many filings a real prefix bug affected, what the
parser does not handle and how often, and how the fixed parser compares to `ixbrlparse` and
Arelle on a 1% company sample. Per the governing brief, a full-year comparison is out of
scope — Phase 3/4 operate on a fixed 5,000-file subset of the 1% sample.

Branch: `feature/accounts-parser-check`. Nothing pushed.

## Environment

| | |
|---|---|
| CPU | Intel(R) Core(TM) Ultra 9 288V, 8 cores, 1 thread/core |
| RAM | 30 GiB |
| OS | Ubuntu 24.04.5 LTS, kernel 7.0.0-34-generic |
| Python | 3.14.3 |
| `ixbrlparse` | 0.11.2 |
| `arelle-release` | 2.45.3 |
| Taxonomy setup | Online mode with Arelle's own web cache (not offline FRC packages — see below) |
| Taxonomy versions encountered | `uk-gaap-full-2009-09-01` (2014-2017 vintage filings), `FRS-102-2014-09-01` (2018-2021), `FRS-102-2019-01-01` (2022), `FRS-102-2021-01-01` (2023), `FRS-102-2023-01-01` (2024, 2026), `FRS-102-2024-01-01` (2025) |

**Taxonomy setup decision.** The brief allowed up to ~1.5h to set up offline FRC taxonomy
packages before falling back to Arelle's online web cache. After ~15 minutes of
investigation (searching the FRC website for a full 2014-2026 set of downloadable taxonomy
package ZIPs, without a quick, reliable path to all of them), a direct test of Arelle's
*default* online behaviour — no special configuration — loaded a real filing correctly in
22s (including first-time taxonomy download over HTTPS from `xbrl.frc.org.uk`) and
extracted facts cleanly. Given this worked immediately and reliably, the remaining ~1h15m of
the offline-setup budget was not spent hunting for a multi-year taxonomy archive; Arelle ran
online throughout, with its cache warmed by loading one real filing from each of the 13
years (2014–2026) before any timing began.

## Coverage achieved

- **Phase 1 (census)**: full monthly coverage, all 152 months, 2014-01 through 2026-08 —
  the projected time (~4h at measured throughput) came in under the brief's 8-hour stop-rule
  threshold, so the quarterly-months fallback was never triggered. Real elapsed time for the
  full download+census run was **~77 minutes** (much faster than the conservative
  projection — see "Phase 1 timing" below).
- **Sample**: 356,469 filings (`sha256(normalised company number) % 100 == 0`), ~25 GB,
  extracted to `data/accounts/parser-sample/`.
- **Phase 3/4 fixed subset**: 5,000 files, seeded-random from the full sample
  (`data/accounts/parser-benchmark-subset.json`), used identically for both the timing
  benchmark (Phase 3) and the fact-level comparison (Phase 4) — the same files ground both
  sets of numbers.
- **Arelle correctness-set coverage**: 7,977 filings (the 4,977 files Phase 4 flagged as
  disagreeing, plus a random 3,000-file top-up from outside the fixed subset), zero failures,
  zero timeouts — see §4's "Arelle correctness-set cross-check" for the budget decision and
  results.

## 1. The prefix bug: how many filings it affected, by year

`core.py`'s `IX_FACT_RE` hardcoded the literal `ix:` prefix for matching `nonFraction`/
`nonNumeric` elements. A filing that bound the inline-XBRL namespace to a different prefix,
or to the default namespace (no prefix at all), extracted **zero facts** — silently, with no
error, indistinguishable from a filing that was genuinely fact-free.

**A second, independent bug was found and fixed during this audit's own byte-scan census**
(`scripts/parser_census.py`), before the headline number below could be trusted. The first
version of the census's namespace-detection regex was double-quote-only
(`xmlns:ix="..."`); real 2013/2014-vintage CH filing software wrote `xmlns:ix='...'` with
single quotes, which the regex silently missed, classifying genuinely `ix:`-prefixed
filings as "no binding at all". This inflated the naive full-archive count to 612,750. A
**cross-check against the existing LONG dataset** (filings the byte-scan called
bug-affected should have zero rows there, since the old code could never have extracted
them) caught it directly: 311,610 of the 612,750 had real LONG rows — impossible if they
were genuinely bug-affected. Both `IX_NAMESPACE_RE` (`core.py`) and the census's own
`IX_NS_RE` were fixed to accept either quote character, the same way `core.py`'s existing
`ATTR_RE` already does (`(['"])...\1`) — a pattern this fix should have used from the start.
A regression test (`test_single_quoted_namespace_declaration_is_recognised`) now guards
this specifically.

Every fact-matching and counting regex in the census (`nonFraction`/`nonNumeric`/
`continuation`/`exclude` counts, context classification) matches **element tag names**, not
attribute values, so none of them shared this blind spot — only the descriptive `ix_prefix`
classification did. Re-scanning the full 1% sample (356,469 files, already on local disk, no
re-download needed) with the corrected regex gives an accurate, confidence-interval-bounded
estimate; re-running the LONG cross-check against the corrected classification now shows
**zero mismatches** (0 of 2,907 corrected-bug-affected sample filings have LONG rows) —
fully validating the fix.

**Exact figures (from the full 35,806,258-filing byte-scan, unaffected fields):**

| Year | Total filings | Plain-XML |
|---|---:|---:|
| 2014 | 1,586,883 | 53,298 (3.359%) |
| 2015 | 1,854,090 | 83,742 (4.517%) |
| 2016 | 2,089,128 | 56,200 (2.690%) |
| 2017 | 2,345,974 | 33,735 (1.438%) |
| 2018 | 2,594,938 | 17,078 (0.658%) |
| 2019 | 2,759,100 | 16,194 (0.587%) |
| 2020 | 2,600,098 | 13,410 (0.516%) |
| 2021 | 3,502,091 | 16,289 (0.465%) |
| 2022 | 3,357,005 | 11,174 (0.333%) |
| 2023 | 3,503,453 | 1 (0.00003%) |
| 2024 | 3,644,790 | 0 |
| 2025 | 3,705,859 | 0 |
| 2026 | 2,262,849 | 20 (0.001%) |
| **Total** | **35,806,258** | **301,141 (0.841%)** |

(35,806,258 vs. the production manifest's raw `member_count` sum of 35,809,176 — a gap of
2,918 members whose filenames don't match the standard `Prod<n>_<batch>_<company>_<date>`
pattern at all; both this census and the production extractor's own `parse_member_filename`
exclude them identically, as `filename_exceptions`.)

**Corrected bug footprint (sample-derived, 95% Wilson CI, validated against LONG):**

| Year | Total filings | Sample n | Sample bug-affected | Rate | 95% CI | Estimated bug-affected |
|---|---:|---:|---:|---:|---:|---:|
| 2014 | 1,586,883 | 15,774 | 525 | 3.328% | [3.060%, 3.620%] | 52,816 |
| 2015 | 1,854,090 | 18,452 | 840 | 4.552% | [4.261%, 4.863%] | 84,405 |
| 2016 | 2,089,128 | 20,782 | 567 | 2.728% | [2.515%, 2.959%] | 56,998 |
| 2017 | 2,345,974 | 23,506 | 320 | 1.361% | [1.221%, 1.518%] | 31,937 |
| 2018 | 2,594,938 | 25,974 | 151 | 0.581% | [0.496%, 0.681%] | 15,086 |
| 2019 | 2,759,100 | 27,526 | 151 | 0.549% | [0.468%, 0.643%] | 15,136 |
| 2020 | 2,600,098 | 25,973 | 117 | 0.451% | [0.376%, 0.540%] | 11,713 |
| 2021 | 3,502,091 | 34,762 | 136 | 0.391% | [0.331%, 0.463%] | 13,701 |
| 2022 | 3,357,005 | 33,541 | 99 | 0.295% | [0.243%, 0.359%] | 9,909 |
| 2023 | 3,503,453 | 34,763 | 0 | 0.000% | [0.000%, 0.011%] | 0 |
| 2024 | 3,644,790 | 36,170 | 0 | 0.000% | [0.000%, 0.011%] | 0 |
| 2025 | 3,705,859 | 36,783 | 0 | 0.000% | [0.000%, 0.010%] | 0 |
| 2026 | 2,262,849 | 22,463 | 1 | 0.0045% | [0.0008%, 0.025%] | 101 |
| **Total** | **35,806,258** | **356,469** | **2,907** | — | — | **≈291,802 [264,049, 324,455]** |

**FLAG for the maintainer**: the exact, full-byte-scan bug-footprint count is not reported
here as a headline figure, because it is known to be wrong (see above) and fixing it
exactly would require re-downloading the ~171 GB spanning the years with a non-negligible
corrected rate (2014-2022; the zips were deleted after Phase 1 processing, per the brief's
own storage-bounding rule). The **291,802 (95% CI 264,049–324,455)** figure is the accurate
one to cite; getting an exact count would need the re-download costed in Section on
targeted re-extraction below. Filing software has essentially eliminated the bug since
2023 — the true rate is indistinguishable from zero in 2023-2025 and is a single filing in
26,463 sampled for 2026.

**Erratum, resolved (2026-09-28) — full root-cause trace, not just a corrected number.**
The first version of this erratum (below, struck through in spirit but left as written for
the record) claimed a contradiction existed between this section's "0 of 2,907 mismatches"
finding and a 10-file spot-check that found complete v1 rows. **The maintainer caught this
contradiction and asked for it to be resolved, not glossed over.** Here is what was actually
wrong, traced to ground truth:

- **Root cause: the persisted census data was never regenerated after the quote-style fix.**
  `scripts/parser_census.py`'s `IX_NS_RE` was fixed for single-quoted `xmlns:ix='...'`
  declarations (as this document already describes), but that fix was only ever applied to
  the *script*. The 152 Parquet files in `data/accounts/parser-census/` were never re-run
  against the fixed script — confirmed directly: `find data/accounts/parser-census -name
  "*.parquet" -newer scripts/parser_census.py` returns **0 of 152** files. Every `ix_prefix`
  classification this document and the original ≈291,802 estimate relied on — even after the
  "fix" — was computed by the *stale, pre-fix* regex the whole time.
- **This fully explains the 10-file spot-check "contradiction."** Those 10 files were drawn
  from the stale `ix_prefix='none'` population. Re-running the *current* (correctly quote-
  fixed) `detect_ix_prefix()` against the one traced example
  (`Prod224_0005_03318735_20140331.html`) returns `"ix"`, not `"none"` — the live regex
  detects `xmlns:ix='http://www.xbrl.org/2008/inlineXBRL'` correctly. The persisted
  classification was simply never updated to match.
- **A deeper problem, found while chasing this**: even with the quote-fix, re-classifying the
  *entire* 1% sample (353,562 real `.html` files, freshly scanned, not from the stale
  Parquets) found **zero** files classified `"none"`. Every sample filing declares a
  detectable inline-XBRL namespace binding somewhere. This means namespace-*declaration*
  presence was never a reliable proxy for "will this filing's facts actually extract" in the
  first place — a filing can declare `xmlns:ix=...` and still use a *different* prefix on its
  actual `<fact>` tags. The census's `ix_prefix` field measures the wrong signal, regardless
  of the quote bug.
- **What is and isn't affected.** None of this touches the *direct* v1-vs-v2 diff numbers
  (§6.5) — that comparison was always computed straight from LONG-vs-LONG, never through the
  census's `ix_prefix` field. **61,085 filings recovered by the prefix fix remains correct**,
  now corroborated two independent ways: (1) the direct diff, and (2) a full-archive
  anti-join confirming **zero `.html` filings have zero v2 rows, at all, in any year** —
  `zero_fact_ixbrl_filings = 0` archive-wide in v2 — meaning the prefix fix is total and
  complete for iXBRL filings, with no residual gap left to find. (27,723 `.xml` filings do
  still fail — entirely ixbrlparse's own type-sniffing rejecting them, a pre-existing,
  already-documented Phase C limitation, unrelated to the prefix bug.)
- **What *is* corrected**: the ≈291,802 estimate and everything derived from the stale
  `ix_prefix` census field (narrative explanations, not the direct-diff numbers) should be
  read as measuring "how many filings an already-known-buggy classifier couldn't classify,"
  which was never a good proxy for "how many filings the extraction bug actually broke,"
  independent of whether the quote-fix was correctly applied to the live data.

**A second, real, separate bug was found and fixed while tracing this** (via the WIDE
"newly null" cells this same investigation was asked to explain — see §6.5's update):
`normalise_number` recognised `numdotdecimal` but not the hyphenated spelling
`num-dot-decimal`, the exact same Transformation Registry family under a different naming
convention. This silently nulled out 540 numeric facts (3 archive months:
`July2024`×12, `July2026`×217, `August2026`×311) that had parsed *correctly* even before the
comma-decimal fix existed. Fixed (`normalise_format_name`, stripping hyphens/underscores
before matching), tested against the real markup that found it (verified to fail on the
un-fixed code in isolation from the rest of the comma-decimal fix), and the 3 affected months
re-extracted. Full detail: §6.5.

---

*Original erratum text, left for the record (superseded by the resolution above, which
traces the actual root cause rather than attributing the mismatch to sample luck):*

The estimate above was itself wrong — corrected by direct measurement, not by another
estimate. The v2 rebuild (§6 below) ran the fixed parser against the *entire* archive and
diffed its LONG output directly against v1's, filing by filing — no sampling, no
census-regex proxy. That direct measurement found **61,085 filings** genuinely recovered by
the prefix fix (zero LONG rows in v1, real facts in v2), not ≈291,802. Spot-checking ten real
filings the census classified as "no ix: binding detected" (the population the ≈291,802
estimate was built from) found all ten already had **complete, identical row counts in both
v1 and v2** — they were never bug-affected at all. The root cause: the census's namespace-
*declaration* detector (`IX_NS_RE`, used only for classification/reporting) and the actual
fact-*extraction* regex (`IX_FACT_RE`, used for real extraction) are two independent regexes
matching two different things, and they disagreed on more filings than the earlier LONG
cross-check (2,907 sampled filings) happened to catch.

## 2. What the parser does not handle, and how often (exact, full byte-scan)

| Case | Filings affected | Share of archive | Total occurrences |
|---|---:|---:|---:|
| Plain-XML (skipped entirely) | 301,141 | 0.841% | — |
| Continuations (`ix:continuation`, not followed) | 1,869,865 | 5.222% | 62,264,338 |
| Exclusions (`ix:exclude`) | 1,887,331 | 5.271% | 5,126,407 |
| Facts nested inside other facts | 3,526,809 | 9.850% | 6,169,655 |
| Multi-member contexts (skipped) | 9,056,099 | 25.292% | 260,525,784 |
| Typed-member contexts (skipped) | 7,211,781 | 20.141% | 122,221,877 |

Multi-member and typed-member contexts affect roughly a **quarter and a fifth of all
filings respectively** — far larger than "edge case". Continuations/exclusions/nested facts
affect 5-10% of filings each. All six phenomena are essentially absent before 2016-2017 and
become common from 2017 onward (`ix:continuation` support in filing software appears to be
a ~2017+ feature: 0 continuation occurrences found in any 2014 or 2015 filing in the full
byte-scan) — consistent with the existing `docs/accounts-limitations.md` finding that
`IX_FACT_RE` "was validated against 2019-2025 markup only".

**Number formats outside the supported set.** 43 distinct `format` values found archive-wide
(1,000,162,727 `nonFraction` + 1,232,585,140 `nonNumeric` elements total). Two families are
genuine misreads, demonstrated here with the real production `normalise_number` against
`ixbrlparse`'s actual `ixtNumComma`/`ixtNumWordsEn` classes (no example of either format
happened to fall in the 1% sample; both are demonstrated with realistic values through the
real code paths, not fabricated comparisons):

| Format | Raw value | `normalise_number` (ours) | `ixbrlparse` | Archive-wide occurrences |
|---|---|---|---|---:|
| `ixt:numdotcomma` | `"1.234,56"` | `"1.23456"` (1000× too small) | `1234.56` | 2,519 |
| `ixt:numcomma` | `"1234,56"` | `"123456"` (100× too large) | `1234.56` | 145 |
| `ixt:numspacecomma` | `"1 234,56"` | `"123456"` (100× too large) | `1234.56` | 89 |
| `ixt2:numcommadecimal` | (same family) | — | — | 282 |
| `ixt:numwordsen` (word-based numbers, e.g. "one hundred") | — | — | — | **0 found archive-wide** |

Total comma-as-decimal misread risk: **3,035 occurrences** archive-wide (0.0002% of all
tagged values) — rare, but a real and severe silent misread (100-1000× magnitude error) when
it occurs. Word-based numbers do not occur at all in this archive.

The most common formats by far are `ixt:numcommadot` (407.1M) and `ixt2:numdotdecimal`
(357.3M) — both comma-thousands/dot-decimal or plain dot-decimal, which `normalise_number`
already handles correctly. `ixt:numdash`/`ixt2:zerodash` (nil-as-zero transforms, 32.4M
combined) are also handled correctly, but via a deliberately deferred design choice (see
below), not via format-transform logic.

## The prefix bug fix

`IX_FACT_RE` in `core.py` now matches any prefix or no prefix at all (the same
`(?:[\w.-]+:)?` wildcard style already used by the file's other element-matching regexes —
`CONTEXT_RE`, `UNIT_RE`, etc. — applied independently to the opening and closing tag). The
document-root gate in `extract.py` (previously `<html|ix:header>`, also hardcoding `ix:`)
now checks for `<html` or the inline-XBRL namespace URI itself (`IX_NAMESPACE_RE`, prefix-
and quote-agnostic) rather than a hardcoded prefixed local name. A new counter,
`zero_fact_ixbrl_filings`, flags any filing that declares the inline-XBRL namespace but
yields zero facts — a safety net so a residual mismatch the fix didn't anticipate would show
up as a flagged anomaly, never silently as "clean, no relevant facts".

**Six regression tests added** to `tests/test_accounts_core.py`, using structurally-real
iXBRL markup (synthetic company data, real element/namespace shapes): an `ix:`-prefixed
filing (baseline), an other-prefix filing, a default-namespace filing, a zero-fact-despite-
namespace filing, a non-iXBRL document, and the single-quoted-namespace case found during
this audit. **Verified, not just asserted**: the fix was `git stash`-reverted and the same
tests re-run against the old code — the other-prefix and default-namespace tests genuinely
failed (extracted `[]` instead of the real fact), confirming they are meaningful regressions,
not just new assertions that happen to pass. The `ix:`-prefixed baseline still passed on old
code (as expected — no behaviour change for the already-working case). Full suite: 167
passed, `ruff` clean, after the fix.

## Cost of a targeted re-extraction (not run)

The corrected bug footprint (≈291,802 filings, 95% CI 264,049–324,455) is concentrated in
2014-2022 — the true rate is indistinguishable from zero from 2023 onward. A targeted
re-extraction would need to re-download those years' archives, since the brief's
bounded-storage rule means zips are deleted after processing and were not retained:

- **2014-2022 filings**: 22,689,307 of 35,806,258 (63.4% of the archive).
- **Estimated re-download size**: ≈171.5 GB (63.4% of the 270.7 GB archive, by filing-count
  proportion — a slight overestimate of the true byte share, since later years' filings
  average somewhat larger).
- **Estimated time**: ≈49 minutes, scaling Phase 1's own observed real elapsed time (77
  minutes for the full 270.7 GB / 35.8M filings) by the 63.4% filing-count share. This
  combines download and a full byte-scan census pass; the actual re-extraction (running the
  now-fixed `extract_filing` and merging into LONG for just the affected keys) is a smaller
  additional cost on top, given `extract_filing` and the census's own regex work are
  comparable in per-file cost, and only ≈292K of the 22.7M filings in scope (1.3%) actually
  need new rows — the rest would be rescanned only to confirm they're unaffected.
- **Not run** in this task, per the brief.
- **Superseded (2026-09-27)**: a later task ran a *full* (not targeted) re-extraction of the
  entire archive with the fixed parser — see §6, "v2 rebuild". The real, directly-measured
  prefix-fix recovery was 61,085 filings, not ≈291,802 (see the erratum in §1) — a targeted
  re-extraction, had it been built against the corrected number, would have been a much
  smaller job than estimated above.

## Anything that changes the published dataset or its limitations

- The prefix bug means the published LONG dataset is silently missing facts from an
  estimated ≈291,802 filings (2014-2022 only; negligible 2023+) — these filings currently
  contribute **zero rows**, not partial or wrong rows, so no already-published number is
  wrong, but coverage is incomplete for those specific filings.
- `docs/accounts-limitations.md`'s existing plain-XML framing ("Pre-2014 months... would
  return mostly-empty extractions dominated by plain-XML filings the pipeline does not
  target") is corroborated and quantified within 2014-2026 too: plain-XML share falls from
  3.4% (2014) to effectively 0% by 2023, confirming the pipeline's target format has been
  correctly identified throughout the archive's live span.
- Multi-member and typed-member contexts (25.3% and 20.1% of all filings respectively) are
  skipped by design, not a defect — but this is a materially larger completeness gap than
  "edge case" framing would suggest, worth stating plainly given the archive's own claim to
  keep "every concept, all-fact, exactly as read".

## 3. Benchmark: ours (fixed) vs ixbrlparse vs Arelle

Timed per the brief's fairness rules: setup untimed; identical input for every parser (the
same 5,000-file fixed subset, `data/accounts/parser-benchmark-subset.json`, seeded-random
from the 356,469-file sample); parse-only (data already in memory) and end-to-end (from a
local file, warm page cache) timings for ours/ixbrlparse, end-to-end only for Arelle; one
parser at a time; 200-file uncounted warm-up then 3 timed repeats, median + range reported;
same N=8 parallelism for every parser (all three fit comfortably in RAM at N=8 — Arelle's
worst per-worker RSS was 348MB, so no parser needed to run at reduced N); 60-second per-file
timeout (ours/ixbrlparse via `SIGALRM`, Arelle via a hard subprocess kill — see below); run
under `systemd-inhibit --what=sleep:idle`; `CLOCK_MONOTONIC`/`CLOCK_BOOTTIME` compared every
repeat (no repeat differed by more than 1s — no sleep/suspend interrupted any run).

| Parser | Mode | Workers | Median ms/file (range, 3 runs) | Throughput (files/s, range) | Peak RSS/worker (MB) | Failures | Timeouts |
|---|---|---|---|---|---|---|---|
| ours (fixed) | parse | 1 | 0.664 (0.662–0.727) | 912 (885–949) | 25.8 | 0/5,000 | 0 |
| ours (fixed) | parse | 8 | 0.827 (0.823–0.834) | 4,712 (4,580–4,792) | 20.2 | 0/5,000 | 0 |
| ours (fixed) | e2e | 1 | 0.653 (0.650–0.659) | 961 (956–965) | 25.8 | 0/5,000 | 0 |
| ours (fixed) | e2e | 8 | 0.839 (0.830–0.840) | 4,771 (4,679–4,835) | 20.4 | 0/5,000 | 0 |
| ixbrlparse | parse | 1 | 8.233 (8.228–8.489) | 63 (61–64) | 125.8 | 2/5,000 | 0 |
| ixbrlparse | parse | 8 | 14.386 (13.402–14.699) | 285 (277–299) | 108.1 | 2/5,000 | 0 |
| ixbrlparse | e2e | 1 | 7.694 (7.648–7.773) | 67 (66–68) | 108.4 | 2/5,000 | 0 |
| ixbrlparse | e2e | 8 | 14.131 (11.619–14.323) | 304 (287–337) | 97.4 | 2/5,000 | 0 |
| Arelle | e2e | 1 | 992.263 (987.5–996.3) | 1.00 (1.00–1.01) | 348.2 | 0/5,000 | 0 |
| Arelle | e2e | 8 | 1842.227 (1809.7–1844.2) | 4.39 (4.36–4.43) | 344.0 | 0/5,000 | 0 |

**Headline speed.** Per file (e2e, 1 worker): ours is **~11.8x faster than ixbrlparse**
(0.65ms vs 7.7ms) and **~1,520x faster than Arelle** (0.65ms vs 992ms). ixbrlparse is
**~129x faster than Arelle**. All three scale well to 8 workers on this 8-core/8-thread
machine (4.4–5.0x aggregate throughput gain), so the per-file numbers above translate almost
linearly into the N=8 throughput column — 8 workers was never memory-constrained for any
parser.

**Projected full-archive time** (35,806,258 filings, scaling from the measured e2e numbers
above — CPU-seconds from the 1-worker median, wall-clock from the measured 8-worker
throughput; both are projections, not re-runs on the full archive, which was out of scope):

| Parser | Projected CPU time (1 core, serial) | Projected wall-clock (8 workers, measured throughput) |
|---|---|---|
| ours (fixed) | ~6.5 hours | ~2.1 hours |
| ixbrlparse | ~76.5 hours (~3.2 days) | ~34.5 hours (~1.4 days) |
| Arelle | ~9,868 hours (~411 days) | ~2,271 hours (~94.6 days) |

**ixbrlparse's two failures** (consistent across all four ixbrlparse runs, same two files
every time) are both `IXBRLParseError: Filetype not recognised`, raised by ixbrlparse's own
document-type sniffing before it attempts to parse anything:
`Prod224_0004_07688706_20130630.html` and `Prod224_0011_07923388_20140131.html` — both
early-vintage filings from the same 2013/2014 window where this task separately found and
fixed a single-quote-namespace-declaration blind spot in our own tooling (see §1). ixbrlparse
apparently has a comparable, independent blind spot for the same era's markup conventions;
this was not investigated further (out of scope — it is ixbrlparse's own parser, not ours),
but it is a relevant data point for the recommendation below: **no parser here handles the
oldest filings in the archive without gaps.**

**A real Arelle robustness bug was found and fixed during this phase.** The first Phase 3
run hung for over two hours on a single file
(`Prod224_0076_06934149_20190630.html`, which references an unresolvable company-specific
extension taxonomy, `dpl-frs`) with the CPU pinned at ~99% doing genuine (if useless) work —
logging thousands of repeated `xmlSchema:valueError` messages — never yielding back to the
Python bytecode loop long enough for the in-process `signal.alarm()` timeout to fire. Fixed
by moving Arelle's timeout enforcement to a hard OS-level subprocess kill
(`multiprocessing.Process` + `.join(timeout)` + `.kill()`, in
`scripts/parser_benchmark.py::parse_arelle_hard_timeout`); ours and ixbrlparse, being
pure-Python and yielding to the interpreter regularly, were left on the original `SIGALRM`
approach. Re-tested directly against the exact triggering file with a 15s budget: it
completed in isolation in ~13s (126 facts) — suggesting the original hang was more likely
accumulated in-process state from Arelle's long-running persistent controller (already having
processed hundreds of prior filings) than something uniquely broken about this one file in
isolation, though this is an informed hypothesis, not a proven root cause (the original stuck
process's state could not be recovered once killed). The full matrix re-ran cleanly afterward
with zero failures or timeouts on every combination.

## 4. Fact-level comparison: ours vs ixbrlparse

Not timed — a separate correctness-only pass over the identical 5,000-file subset Phase 3
benchmarks, so the same files ground both the speed numbers and the accuracy numbers. Facts
are matched by key: `(company, source_member, concept, period_end, dimension_members)`,
where `dimension_members` is a sorted tuple of `(dimension, member)` local-name pairs — empty
for a non-dimensional fact. Plain-XML filings are excluded from ours' side of the comparison
(ours cannot parse them by design; ixbrlparse's XML-mode output is not a like-for-like fact
set), which is why the "xml" reason exists in the tables below but was not observed in this
subset's `ixbrlparse_only` breakdown.

| Year | Shared facts | Agreement | Agreement rate | 95% CI | ixbrlparse-only | ours-only |
|---|---|---|---|---|---|---|
| 2014 | 10,931 | 9,750 | 89.20% | [88.60%, 89.76%] | 6 | 134 |
| 2015 | 13,084 | 11,672 | 89.21% | [88.66%, 89.73%] | 26 | 0 |
| 2016 | 15,560 | 13,833 | 88.90% | [88.40%, 89.39%] | 39 | 0 |
| 2017 | 17,436 | 15,647 | 89.74% | [89.28%, 90.18%] | 279 | 0 |
| 2018 | 20,857 | 18,752 | 89.91% | [89.49%, 90.31%] | 552 | 0 |
| 2019 | 20,257 | 18,055 | 89.13% | [88.69%, 89.55%] | 567 | 0 |
| 2020 | 20,626 | 18,343 | 88.93% | [88.50%, 89.35%] | 497 | 0 |
| 2021 | 28,163 | 25,198 | 89.47% | [89.11%, 89.83%] | 765 | 0 |
| 2022 | 26,044 | 23,270 | 89.35% | [88.97%, 89.72%] | 744 | 0 |
| 2023 | 25,286 | 22,510 | 89.02% | [88.63%, 89.40%] | 1,849 | 1 |
| 2024 | 27,877 | 25,092 | 90.01% | [89.65%, 90.36%] | 1,266 | 0 |
| 2025 | 30,662 | 27,504 | 89.70% | [89.36%, 90.04%] | 892 | 0 |
| 2026 | 15,012 | 13,539 | 90.19% | [89.70%, 90.65%] | 431 | 0 |
| **Total** | **271,795** | **243,165** | **89.47%** | — | **7,913** | **135** |

**Reading the agreement rate.** ~89.5% of facts both parsers find, they agree on exactly (or
after whitespace/numeric-representation normalisation — see `values_equal`). The remaining
~10.5% break down as follows, in order of materiality:

*Value mismatches on shared facts* (28,630 total, i.e. ~9.5% of the 271,795+28,630 facts both
parsers produced a value for):

| Reason | Count | Share | What it is |
|---|---|---|---|
| `text_format_untransformed` | 20,102 | 70.2% | ours keeps raw displayed text for non-numeric facts (e.g. "3 January 2023"); ixbrlparse applies iXBRL Transformation Registry rules (e.g. "2023-01-03"). Both faithfully represent the same underlying value — a systematic representational difference, not a parsing error. |
| `nil_dash_deferred_to_pivot` | 5,127 | 17.9% | A bare dash is deliberately kept as "no value" by ours at extraction time (resolved to 0 only downstream, at pivot time — see `core.py`'s `NIL_RAW_VALUES`); ixbrlparse's `ixtZeroDash` format resolves it to `0` immediately. Not a parsing gap, a different point in the pipeline where the same decision is made. |
| `continuation` | 2,338 | 8.2% | ours never follows `ix:continuation` chains — it only sees the first text fragment. Confirmed genuine (not a formatting artefact) by testing whitespace-collapsed prefix containment. |
| `nested_fact` | 993 | 3.5% | A fact nested inside another fact of the same local name (`nonFraction`/`nonNumeric`) gets its text absorbed into the outer fact by ours' non-greedy closing-tag match. Same root defect as the `ixbrlparse_only` `nested_fact` reason below, manifesting here as a corrupted shared value instead of a missing key. |
| `other` | 70 | 0.24% | Residual, not further categorised. Manual inspection of examples across several years shows most of these are a second, harder-to-detect manifestation of the same nested-fact defect — the inner fact has a *different* concept name and its text gets spliced into the middle of the outer fact's text (e.g. ours: `"Atrue"`, ixbrlparse: `"true...at the time of approving the financial statements..."`), which does not fit the clean prefix/suffix test used for the `nested_fact` category above. Not chased further given how small this residual is. |

*Facts only ixbrlparse found* (7,913 total — every one of these is a fact category ours skips
by design, not a parsing failure on a fact ours was trying to extract):

| Reason | Count | Share | What it is |
|---|---|---|---|
| `multi-member` | 7,603 | 96.1% | Contexts with 2+ dimension members — ours skips multi-member contexts entirely by design (see `docs/accounts-limitations.md`). |
| `nested_fact` | 271 | 3.4% | A fact nested inside another fact of a *different* concept, entirely missing from ours' output (not merely mis-valued) — confirmed live via `business:BalanceSheetDate` nested inside another `nonNumeric` fact in a real filing. |
| `typed` | 34 | 0.4% | Typed-member (as opposed to explicit-member) dimensional contexts — also skipped by design. |
| `continuation` | 5 | 0.1% | A continuation-only fact where ours produced no value at all for the key (rather than a truncated one, which would show up as a value mismatch instead). |

**Facts only ours found** (135 total, 0.05% of shared-or-ours-only facts): concentrated
entirely in 2014, and **not a genuine completeness gap** — 134 of the 135 come from a single
file where ixbrlparse's own `IXBRLParseError: Filetype not recognised` (see §3) meant
ixbrlparse produced zero facts for that document, so every fact ours extracted registered as
"ours-only" by elimination rather than through any real disagreement.

### Arelle correctness-set cross-check

A third, independent parser run over every disagreement above, to see which side Arelle's
own (standards-based, tree-parsing) model resolution sides with — not timed, run once
(`scripts/arelle_correctness.py`).

**Correctness-set composition** (a scope decision, flagged rather than assumed): the 4,977
files Phase 4 flagged as disagreeing (out of the 5,000-file subset) plus a random top-up of
3,000 further files drawn from the wider 356,469-file sample, excluding the subset —
7,977 files total, sized from Phase 3's measured 8-worker Arelle throughput (~4.4 files/s) to
fit roughly 30 minutes; actual run took 33.3 minutes. **Zero failures, zero timeouts** across
all 7,977 files (the earlier hard-hang fix held up); 14 files turned out to have no
disagreement once fully reprocessed, so Arelle ran fact-extraction on the remaining 7,963,
producing 59,276 individual disagreement-level verdicts.

**Caveat, stated plainly**: this join is best-effort, not as rigorously reconciled as the
ours-vs-ixbrlparse `FactKey` match in §4. Arelle's own context/period model is date-shifted
(confirmed by probing a real filing before writing this: an instant context dated
"2023-07-31" surfaces in Arelle as `ctx.instantDatetime == 2023-08-01`, XBRL's exclusive-end
convention), corrected for by subtracting one day, but a `arelle_missing_key` verdict below is
genuinely ambiguous between "Arelle didn't produce this fact" and "the independently-computed
key didn't line up" — most concentrated in the multi-member category, exactly where dimension
key-matching is hardest.

| Disagreement category | n | Arelle agrees: ours | ixbrlparse | both | neither | missing key |
|---|---|---|---|---|---|---|
| `text_format_untransformed` | 32,433 | 10,393 (32.0%) | 21,620 (66.7%) | — | 18 (0.1%) | 402 (1.2%) |
| `nil_dash_deferred_to_pivot` | 8,438 | — | 8,215 (97.4%) | — | — | 223 (2.6%) |
| `multi-member` (ixbrlparse-only) | 12,132 | — | 8,711 (71.8%) | 563 (4.6%) | — | 2,858 (23.6%) |
| `continuation` (value mismatch) | 3,894 | 1 (0.0%) | 3,682 (94.6%) | — | 126 (3.2%) | 85 (2.2%) |
| `nested_fact` (value mismatch) | 1,661 | — | 1,661 (100%) | — | — | — |
| `nested_fact` (ixbrlparse-only) | 424 | — | 422 (99.5%) | 2 (0.5%) | — | — |
| `ours_only` | 135 | 105 (77.8%) | — | 3 (2.2%) | 20 (14.8%) | 7 (5.2%) |
| `typed` (ixbrlparse-only) | 47 | — | 44 (93.6%) | — | — | 3 (6.4%) |
| `other` (value mismatch) | 106 | — | 10 (9.4%) | — | 96 (90.6%) | — |
| `continuation` (ixbrlparse-only) | 6 | — | 6 (100%) | — | — | — |
| **Total** | **59,276** | **10,499 (17.7%)** | **44,371 (74.9%)** | **568 (1.0%)** | **260 (0.4%)** | **3,578 (6.0%)** |

**What this confirms.** Where Arelle has an opinion at all (excluding missing-key), it sides
with ixbrlparse over ours **~4.2x as often** (44,371 vs 10,499). But the breakdown by category
is the useful part, not the aggregate:

- **`nested_fact` (both variants, 2,085 combined): Arelle agrees with ixbrlparse 99.9% of the
  time, 0% with ours.** This is the clearest possible confirmation that the nested-fact defect
  (§1/§4) is a genuine bug, not a design difference — a third, independent, standards-based
  parser corroborates ixbrlparse's value/presence over ours' in essentially every case.
- **`continuation`: Arelle agrees with ixbrlparse 94.6–100%** (both variants) — Arelle also
  follows `ix:continuation` chains, as expected; ours does not. Also a genuine gap, not a
  design choice.
- **`nil_dash_deferred_to_pivot`: Arelle agrees with ixbrlparse 97.4%** — Arelle also resolves
  a bare dash to a zero/blank value at extraction time. This confirms ours' behaviour here is
  the *unusual* one among the three parsers, but it is a documented, deliberate Stage-1 design
  choice (resolved later, at pivot time), not a defect — nothing to fix, but worth knowing
  ours is the outlier.
- **`text_format_untransformed`: split 32.0% ours / 66.7% ixbrlparse.** Less one-sided than
  the categories above — Arelle applies Transformation Registry rules like ixbrlparse, but a
  third of the time its normalised value happens to match ours' raw text anyway (e.g. formats
  that are already in canonical form, or transform edge cases). Confirms this category is a
  genuine representational difference, not a one-sided error.
- **`multi-member`: Arelle agrees with ixbrlparse 71.8%** when it can find a matching key at
  all (23.6% missing-key, the highest of any category — consistent with the caveat above that
  multi-member dimension keys are the hardest to reconcile across three independently-computed
  key schemes). Not a surprise ours never appears here — it does not produce multi-member
  facts at all — but Arelle's independent extraction corroborates that ixbrlparse's
  multi-member facts are real, correctly-formed facts, not noise.
- **`ours_only`: Arelle agrees with ours 77.8%.** This is the strongest evidence in ours'
  favour anywhere in this cross-check — for the 135 facts that exist only because ixbrlparse's
  own type-sniffing failed outright on 2 files, Arelle (working from the same raw markup,
  independently) confirms ours' extracted values are correct the large majority of the time.
- **`other` (the un-categorised residual from §4): Arelle agrees with neither parser 90.6% of
  the time.** This validates the decision in §4 not to chase this bucket further — it is
  genuinely murky even to a third, independent parser, not a disagreement this task's
  categorisation heuristics failed to resolve.

### Optional: WIDE-table cell-by-cell comparison — skipped

**Decision (flagged for the maintainer, not made silently): skipped.** The brief makes this
conditional on ≥2h remaining; assessed against the existing pivot pipeline
(`src/ukcompany/accounts/pivot.py`, 295 lines: `WideColumnMap`-driven column mapping,
`_reduce_to_cells`/`_finalize_pivot` with `PivotMode` first-reported tie-breaking) rather than
against a guess. Reusing "the same reconciliation code" cell-by-cell as the brief asks for
would mean mapping ixbrlparse's raw fact set into the same LONG schema this pipeline expects
(concept/value/dimension columns matching `WideColumnMap`'s config, including its
first-reported tie-break semantics) before the pivot code could run on it at all — a second,
separate data-engineering task in its own right, not an incremental extension of Phase 4's
fact-level comparison already done above. Given the time already spent on this task (Phase 1's
77-minute live run, the Phase 3 Arelle matrix's several hours of real wall-clock timing
including the hung-then-fixed run, and the Arelle correctness-set pass above), building and
validating a second reconciliation pipeline was judged not to fit the remaining budget with
the rigor the rest of this report has held to. The fact-level comparison in §4 already
answers the same underlying question (where do the two parsers disagree, and why) at finer
grain than a WIDE-table diff would — every WIDE-table disagreement will trace back to one of
the categories already quantified there.

## 5. Recommendation

**Update (2026-09-27): recommendation (b) below was subsequently acted on** — see §6. The
XML-fallback piece was implemented in full (a dedicated `ixbrlparse` adapter, not a permanent
runtime dependency); the continuation/nested-fact "follow-on engineering opportunity"
mentioned below was assessed with real data and deliberately deferred (quantified rate too
low to justify the fix, not overlooked); multi-member/typed-member capture remains out of
scope, per an explicit decision, not by default. The original recommendation text below is
left as written for the historical record of the reasoning that led there.

**(b): keep ours as the default parser, and fall back to ixbrlparse for the specific
filings/facts ours is known to skip by design** (multi-member contexts, typed-member
contexts, and plain-XML filings). Reported here with evidence, per the brief — not
implemented.

**Why not (a), keep ours unchanged after the prefix fix.** The prefix fix (§1/§2) closes a
real, quantified gap (~291,802 filings, 2014-2022), but the fixed parser still has, by design,
*zero* visibility into multi-member and typed-member dimensional facts, and no
`ix:continuation`-chain following. §2's full-archive census puts multi-member alone at 25.3%
of all filings and typed-member at 20.1% (materially overlapping); this is not an edge case
worth waving away, and the Arelle cross-check above independently corroborates that
ixbrlparse's facts in these categories are real, correctly-formed facts ours simply never
attempts.

**Why not (c), switch to ixbrlparse entirely.** Per file, ours is **~11.8x faster than
ixbrlparse** (0.65ms vs 7.7ms, e2e/1-worker) and **has zero failures** on the 5,000-file
subset, versus ixbrlparse's 2 (`IXBRLParseError: Filetype not recognised`, both early-vintage
filings — ixbrlparse has its own, independent blind spot for old markup, just a different one
than ours had). Projected to the full archive at measured 8-worker throughput: **~2.1 hours
for ours vs ~34.5 hours (~1.4 days) for ixbrlparse** — a ~16x slowdown for the whole pipeline.
And on the 89.5% of shared facts both parsers already extract, they agree — so a full switch
pays that entire cost for a benefit concentrated in the minority of filings and facts where
ours is deliberately narrower, while giving up speed on the majority where the two already
agree.

**What (b) requires, quantified from the existing full-archive census** (no new scanning
needed — `data/accounts/parser-census/*.parquet` already has these flags for all 35,806,258
filings, not just the 1% sample):

- **13,583,718 filings (37.9% of the archive)** have a multi-member context, a typed-member
  context, or are plain-XML — the *structural*, by-design exclusions. These need ixbrlparse
  (or Arelle, but ixbrlparse is ~129x faster) to extract the facts ours cannot reach at all.
- **5,350,027 filings (14.9%)** have an `ix:continuation` element or a nested fact — these are
  genuine *bugs* in ours' regex approach (confirmed by the Arelle cross-check: ~95-100%
  agreement with ixbrlparse on both), not permanent design limitations. They are flagged here
  as a separate, scoped follow-on engineering opportunity (chain-following continuation
  elements; nesting-aware closing-tag matching, analogous to the prefix-bug fix in §2) that
  could shrink the ixbrlparse-fallback population further, rather than being treated as a
  reason to fall back to ixbrlparse permanently. Not attempted in this task — out of the
  stated scope (§2's fix was the one bug this brief named).
- These two groups overlap; the union needing *some* form of fallback today is **15,484,687
  filings (43.3% of the archive)**. Running ixbrlparse only on this subset, rather than the
  whole archive, keeps the ~1.4-day full-ixbrlparse-pass cost down to roughly **43% of it,
  ~14.8 hours at 8 workers** — still a meaningful cost, but a bounded, one-time one rather than
  a permanent per-filing tax on every future ingest.
- Combined with §2's prefix-bug re-extraction (2014-2022, ~171.5 GB, ~49 minutes), a full
  remediation pass under recommendation (b) would need, in total: the prefix-bug
  re-extraction (§2) **and** an ixbrlparse-fallback pass over the 15.48M structurally-affected
  filings above. Neither was run in this task, per the brief — both are quantified here so the
  maintainer can decide whether and when to schedule them.

**What does not need to change**: the `nil_dash_deferred_to_pivot` and
`text_format_untransformed` categories (§4) are confirmed design choices, not defects — ours
differs from both ixbrlparse and Arelle here, but deliberately and by a documented convention
(deferred nil-resolution at pivot time; raw untransformed text preserved rather than
normalised). No fallback or fix is needed for either.

## 6. v2 rebuild: fixes applied, XML added, full archive rerun (2026-09-27)

Branch unchanged (`feature/accounts-parser-check`), nothing pushed. All work here is
additive: v1 (`data/accounts/long/`, `data/accounts/accounts-wide-*.parquet`, `kaggle/`,
`kaggle-long/`) was never modified or deleted; v2 writes to `data/accounts/v2/`,
`kaggle-v2/`, `kaggle-long-v2/` exclusively.

### 6.1 Phase A: analysis before any code change

Restricting the existing Phase 4 comparison to exactly the 13 WIDE columns
(`config/accounts-wide-columns.json`) found agreement of 93.5-99.85% per column, with
**every disagreement being either the nil-dash design choice or one of the two known
ixbrlparse hard-failures** — zero multi-member/typed/nested/continuation gaps touch any
published WIDE column in the 5,000-file subset. Restricting further to numeric facts only
and excluding nil-dash gives **99.999% agreement (119,812/119,813 shared numeric facts, 95%
CI [99.995%, 100%])** — this is the figure published in place of the original 89.5% headline.
A typed-member personal-data scan found every sampled typed dimension code-shaped (sequence
numbers), not name-shaped; the two "Directors"-named dimensions were checked with
non-identifying aggregate statistics (100% all-digit, max length 2 characters) rather than
trusting a classifier alone. Full detail: §4 above (folded into the existing sections rather
than kept as a separate report).

### 6.2 Phase B: nested facts deferred, continuations deferred, comma-decimal formats fixed

**Nested-fact pre-check** (before writing any fix): splitting the existing nested-fact
disagreements by numeric-vs-non-numeric found only **2 of 131,096 numeric facts affected
(0.0015%)** in the 5,000-file subset, and **zero WIDE-column concepts affected at all**. Per
the maintainer's explicit threshold (fix only if >0.1% of numeric facts or any WIDE concept
is affected), **deferred, not fixed** — documented as a known limitation in
`docs/accounts-limitations.md` instead.

**Continuations**: deferred alongside nested facts, per the maintainer's instruction — the
defect is non-numeric-only, and the public `kaggle-long/` dataset's 17-concept structured
metadata allowlist doesn't include any concept long enough to need continuation, so it
doesn't reach publication regardless.

**Comma-as-decimal number formats** (`numdotcomma`/`numcomma`/`numspacecomma`/
`numcommadecimal`, both `ixt` and `ixt2` registry namespaces): fixed in
`normalise_number`. An unrecognised `format` on a numeric fact now resolves to `null` and is
counted (`IntegrityCounts.unrecognised_numeric_format`), never guessed. Six new regression
tests, five of which fail on the pre-fix code (verified via `git stash`); a sixth confirms the
existing dot-decimal family is unaffected. Verified directly against real archive data: a
real `CashBankOnHand` fact with raw text `"3.349"` (format `ixt:numdotcomma`) read as `3.349`
(≈100,000x too small) before the fix, `3349` after. Speed impact: unmeasurable — before/after
timings on the same 5,000-file subset were within normal run-to-run noise (well under the
3x stop-rule threshold), and the fix's real-world archive footprint (1,108 facts changed
value across the full 35.8M-filing archive — see §6.4) is too rare to move the fixed subset's
aggregate numbers at all.

### 6.3 Phase C: plain-XML filings added via an ixbrlparse adapter

New module `src/ukcompany/accounts/xml_adapter.py`, routing `.xml` members (previously
`xml_skipped` outright) through `ixbrlparse` into the *same* `FactObservation` schema as the
iXBRL path — same dedupe/conflict-status logic (reused directly, not reimplemented, via a
small refactor exposing `core.py`'s internal grouping functions to both paths). Two things
were checked empirically before writing the adapter, not assumed:

- **ixbrlparse already applies scale and sign** to a numeric fact's resolved value
  (confirmed by reading `ixbrlparse.components._base.ixbrlFormat.parse_value`) — the adapter
  must not reapply them, which would double-count. Verified with a dedicated test
  (`test_scale_and_sign_are_not_reapplied_on_top_of_ixbrlparse`).
- **ixbrlparse's own `segments` list has a duplication quirk for typed members**
  (BeautifulSoup's `findChildren()` walks all descendants of `<segment>`, not just direct
  children, so one typed dimension produces two segment entries) — confirmed against two real
  filings before writing the context-classification logic, which checks for a `typedMember`
  tag's *presence*, not count.

Every observation now carries a `parser` column (`"ours"` or `"ixbrlparse"`) — provenance,
added to the storage schema (`OBSERVATION_SCHEMA_VERSION` 2 → 3) and propagated automatically
to Parquet export via the existing `OBSERVATION_COLUMNS`-driven design (no export-code changes
needed). Ten new tests. Checked against Arelle on 200 real `.xml` filings: **100% agreement
on shared facts (5,845/5,845), zero facts Arelle found that the adapter missed**, across 186
successfully-compared files (14 excluded — a pre-existing, unrelated zero-byte
sample-extraction artifact from the 2015-12 archive month, confirmed isolated to that one
month's `.xml` sample files and to have zero overlap with the Phase 3/4 HTML-only benchmark
subset).

### 6.4 Phase D: full archive rerun

**Disk check**: 441 GB free; v1's total footprint (LONG + WIDE + public LONG + Kaggle
staging) is ~30 GB, so even a generous projection for v2 left an estimated ~400 GB free
afterward — nowhere near the 50 GB stop-rule floor.

**A real production-pipeline limitation was found before committing to a timing plan**: the
`ukcompany-accounts run` command has no built-in parallelism — a live single-threaded run
measured **~820 filings/sec**, projecting **~12.1 hours** for the full archive, well past the
brief's ~4-5 hour estimate (that estimate came from Phase 3's benchmark *scripts*, which use
`ProcessPoolExecutor`; the production CLI does not). Flagged to the maintainer with three
options; the maintainer chose to parallelise. The single-threaded run was killed (no
completed months lost) and replaced with an 8-way month-range parallel launch
(`scripts/run_phase_d2_parallel.sh`): 8 concurrent `ukcompany-accounts run` invocations over
disjoint ~19-month ranges, each with its own `--store` (SQLite doesn't tolerate concurrent
writers to one file) but a shared `--output-dir` (per-month Parquet filenames never collide
across disjoint ranges). Smoke-tested on a 2-worker/300-filing-limit run first. Completed all
152 months with **zero errors**, in significantly under the original single-threaded
projection (workers finished between roughly 45 minutes and 2.75 hours after launch,
staggered by each worker's download queue). The 8 workers' manifests were merged into one
combined `data/accounts/v2/manifest.sqlite` via the existing `export-manifest` machinery.

**Rebuilt from v2 LONG** (`ukcompany-accounts pivot`/`build-public-long`/`inventory`/
`restatement`, `--engine duckdb`, each inside a `systemd-run` cgroup): WIDE in both modes with
provenance, public LONG (1,312,845,786 rows, close to v1's 1,301,140,617), the concept
inventory (4,593 concepts vs v1's ~4,455 — the difference is new concept names first seen in
the newly-added XML filings), and restatement rates (overall 2014-2026 plus all 13
individual years). One transient failure: the by-year restatement loop was OOM-killed by its
cgroup right at a step transition after the four earlier steps had already succeeded cleanly
(peaks of 17.5-19.1 GB each) — relaunched in a fresh cgroup with more headroom and completed
cleanly; the already-successful overall restatement result was unaffected and not rerun.

**Staging guard** (`scripts/kaggle_staging_guard.py`) run against `kaggle-v2/` and
`kaggle-long-v2/` (hard-linked from the v2 outputs, not copied): **passed**.

### 6.5 Phase E: the v1 → v2 change, measured directly

Every number below comes from diffing v1's and v2's actual LONG/WIDE output files directly —
no sampling, no census-regex proxy. (`scripts/phase_e_step.py`, `scripts/
phase_e_compare_wide.py`.) Two DuckDB queries needed a rewrite after hitting resource limits
on the full ~2-billion-row corpus: a naive multi-column join on facts with conflicting/
duplicate status exploded into a disk-filling cartesian product (fixed by restricting the
value-comparison join to `status='selected'` rows only — the only shape "did this already-
resolved value change?" makes sense for anyway); a 7-column anti-join across the full corpus
exceeded the 22 GB cgroup limit (fixed by joining on a single hashed key column instead of
seven raw text columns).

**LONG, newly-covered filings by cause** (zero rows in v1, real facts in v2):

| Cause | Filings | Observations |
|---|---:|---:|
| Plain-XML (Phase C) | 273,418 | 15,499,375 |
| Prefix-bug fix (§1/§2) | 61,085 | 5,455,875 |
| **Total** | **334,503** | **20,955,250** |

**This directly measured prefix-bug recovery (61,085) is the number to cite going forward —
see the erratum in §1** for why the earlier sample-based estimate (≈291,802) was itself
wrong, not just imprecise. The XML count (273,418) is lower than the full-archive census's
301,141 plain-XML total; the gap is filings that were *already* zero-content in both v1 and
v2 (e.g. genuinely fact-free cover-page-only documents) plus the small number of
`.xml`-extension files ixbrlparse's own type-sniffing rejects (§3's ixbrlparse blind spot).

**LONG, value changes on already-shared keys** (both sides had a fact, comma-decimal fix
changed it): **1,096 facts across the full archive** (updated from an initial 1,108 — see
the update below; the difference is 12 facts that were counted as "changed" only because a
second, separate bug was nulling them in v2, now fixed) — consistent with the original
comma-decimal risk estimate (3,035 occurrences found archive-wide by format-attribute
alone; not every flagged occurrence produces a *different* final value, e.g. a value with no
actual thousands separator present). Real examples (company numbers obfuscated):

| Concept | Raw value | v1 (wrong) | v2 (correct) |
|---|---|---|---|
| `ValueSharesAllotted` | `"30,00"` | `3000` | `30.00` |
| `ShareCapitalAllottedCalledUpPaid` | `"309,50"` | `30950` | `309.50` |
| `OtherCreditors` | `"1.675"` | `1.675` | `1675` |
| `Equity` | `"4.506"` | `4.506` | `4506` |

**Regression check**: keys present in v1 (`status='selected'`) with no v2 counterpart:
**0**, re-verified after the update below. The fix is a strict improvement — nothing was
lost.

**Update (2026-09-28) — a real regression found and fixed via the "newly null" WIDE cells
below.** The table beneath this paragraph originally showed 11–73 "newly null" cells per
column — a published value present in v1 disappearing in v2, which the maintainer correctly
flagged as needing a traced explanation rather than a shrug. Tracing real examples (e.g.
`Equity` for one company/period: v1 `49386.0`, v2 `NULL`) led straight to the underlying
LONG fact: raw value `"49,386"`, `format="ixt2:num-dot-decimal"` — the *hyphenated* spelling
of the Transformation Registry's dot-decimal family. `normalise_number` recognised
`numdotdecimal` but not `num-dot-decimal`, so every fact using the hyphenated spelling was
being treated as "unrecognised format" and nulled — silently regressing values that had
parsed *correctly* even before this chapter's comma-decimal fix existed. Confirmed archive-
wide via the existing format census (`data/accounts/parser-format-census-total.json`, no
re-scan needed): **540 occurrences, confined to 3 months** — `ixt:num-dot-decimal` in
July2026 (217) and August2026 (311), `ixt2:num-dot-decimal` in July2024 (12). (A second,
genuinely unfamiliar format, `numunitdecimal`, also appears 36 times across 8 other months —
left correctly nulled-and-counted, not guessed at, since its semantics aren't confirmed.)
Fixed with `normalise_format_name()` (strips hyphens/underscores before matching), tested
against the real markup that found it, verified to fail in isolation from the rest of the
comma-decimal fix (not just against the pre-chapter baseline, which would have passed by
coincidence — see `test_hyphenated_format_name_is_recognised_same_as_unhyphenated`). The 3
affected months were re-extracted; WIDE, public LONG, and restatement were rebuilt from the
corrected LONG; the numbers below reflect the corrected data.

**WIDE, cell by cell, `as_first_reported` mode** (the flagship, predictive-safe file),
**after the hyphen-format fix**:

| Column | Newly filled | Changed | Newly null |
|---|---:|---:|---:|
| Equity | 61,091 | 61 | **0** |
| CashBankOnHand | 61,085 | 96 | **0** |
| AverageNumberEmployeesDuringPeriod | 61,086 | 0 | **0** |
| equity_share_capital | 61,084 | 16 | **0** |
| creditors_within_one_year | 1 | 88 | **0** |
| creditors_after_one_year | 1 | 3 | **0** |
| *(remaining 7 columns: same pattern — zero newly-null on every column, both modes; full table in* `data/accounts/parser-compare-results/phase_e_wide_diff.json`*)* | | | |

**Every "newly null" cell, on every column, in both modes, is now zero.** The hyphenated-
format bug was the complete explanation — there is no remaining unexplained disappearance of
a published value anywhere in this comparison.

"Newly filled" still clusters tightly around 61,085 for every column — the exact count of
prefix-fix-recovered filings, each contributing its first-ever WIDE row/cell. The `latest`
mode shows much larger "changed" counts (up to 6,043 for
`TotalAssetsLessCurrentLiabilities`) than `as_first_reported` (max 94) or the 1,096 total
LONG-level value changes — because `latest` mode's winning filing per company-period can
*shift* to a newly-recovered filing that turns out to be the genuinely most recent one,
changing the published cell even though neither the old nor new underlying fact value was
individually wrong. This is a real, expected consequence of previously-invisible filings now
correctly competing in the ranking, not a defect — confirmed by "changed" counts being
essentially unchanged before/after the hyphen-format fix (that fix only ever moved facts out
of "newly null", never in or out of "changed").

**Restatement rate**: v1 (post-dash-fix) 9.36%; v2 9.36% — unchanged to two decimal places
(recomputed after the hyphen-format fix, still 9.36%, 117,739,387 repeated keys), as expected
(the fixes touch a tiny, isolated fraction of facts, not enough to move an aggregate rate
over 117M+ repeated keys).

**Fill rates**: unchanged to within 0.3 percentage points on every column, both modes (v2 has
more total WIDE rows — 36,931,122 vs 36,710,673 in `latest` mode — from the newly-recovered
and newly-added filings, but the *proportion* filled per column is stable, meaning the new
rows have similar sparsity patterns to the existing archive rather than skewing it).

**Q2 (full-archive, no download needed)**: anti-joining every `.html` census member against
v2 LONG finds **zero `.html` filings with zero v2 rows, in every single year** — the prefix
fix has no residual gap. `zero_fact_ixbrl_filings = 0` archive-wide in v2, consistent with
the anti-join. All 27,723 filings still missing from v2 are `.xml` (ixbrlparse's own
type-sniffing rejections, §3, unrelated to the prefix bug) — zero `.html` filings are
missing. Since the "still zero v2 rows" population for `.html` filings is empty, there was
nothing left to classify by namespace URI for that format — the fix is complete.

Full step-by-step data: `data/accounts/parser-compare-results/phase_e_steps/*.json`,
`phase_e_wide_diff.json`, `phase_e_fill_rates.json`.
