# Deck corrections

Figures below are measured, not estimated, from `docs/accounts-parser-check.md` (Phase 3/4)
and this task's Phase A/B/C work. Listed as a correction list for the maintainer to apply to
the actual slide deck — that deck is not in this repository, so no slides were edited
directly. Update the specific slide/figure named in each item; don't reformat the rest.

## 1. Parser speed

**Was**: ~2ms (ours) vs ~33ms (ixbrlparse) per filing — an estimate.

**Now, measured** (5,000-file fixed subset, e2e/1-worker, 3 repeats, median):
- Ours: **0.65 ms/filing**
- ixbrlparse: **7.7 ms/filing**
- **Ours is ~12x faster than ixbrlparse** (not the ~16x the old estimate implied) — update
  any slide stating a speed multiplier.
- For context, Arelle (the third parser benchmarked): ~992 ms/filing, i.e. **~1 second per
  filing** — if a slide states an Arelle speed, this is the measured figure, not an estimate.

## 2. Archive size

**Now, measured (exact byte-scan, not sampled)**: **35,806,258 filings** in the full
2014-2026 Companies House accounts archive (152 months). If a slide states a different
total or an approximate figure ("~36 million", "~35 million"), replace with this exact count.

## 3. Full-archive processing time

**Was**: an estimate not tied to a measured throughput.

**Now, measured** (scaling the 5,000-file subset's 8-worker throughput to all 35,806,258
filings):
- Ours: **~2.1 hours**
- ixbrlparse: **~1.4 days** (~34.5 hours)
- Arelle: **~94.6 days** — not viable at this archive's scale under any parallelism this
  hardware offers.

Note for whoever updates the deck: these are *processing*-time projections from the 5,000
file benchmark, not a timed full-archive run. The actual Phase D full rerun (this task) found
the **production pipeline itself has no built-in parallelism** — a real full-archive run at 1
worker measured ~820 filings/sec, and needed an ad hoc 8-way parallel launch (independent
month ranges, see `scripts/run_phase_d2_parallel.sh`) to approach the multi-worker projection
above. If a slide implies the production pipeline is single-command turnkey at these speeds,
add a footnote: full-archive throughput requires explicit parallelisation across month
ranges, not a flag on the existing `run` command.

## 4. Numeric agreement (the accuracy figure)

**Was**: 89.5% agreement between ours and ixbrlparse (Phase 4 headline, archive-wide fact
comparison including non-numeric text).

**Now, publish instead**: **"99.999% on numeric facts (dashes excluded; resolved identically
at pivot)"** — verbatim wording, per the maintainer's explicit instruction. Measured on the
same 5,000-file subset: 119,812 / 119,813 shared numeric facts (excluding the deliberate
nil-dash-at-pivot design difference) agree, 95% CI [99.995%, 100%], every year 2014-2026
individually at 99.9-100%.

**Why the two figures differ so much**: the 89.5% figure mixed in non-numeric text
representational differences (raw displayed text vs Transformation-Registry-normalised text —
a deliberate design choice, not an error) and the nil-dash convention (also deliberate). Once
narrowed to what WIDE actually publishes — numeric cells — agreement is effectively perfect.
If a slide currently cites 89.5%, replace it with the numeric figure above; if the slide's
point was specifically about non-numeric/text fidelity, keep 89.5% but relabel it clearly as
"all facts including text" rather than "accuracy."

## 5. What is fixed now (accounts-parser v2)

If a slide lists known parser limitations, update against this list:

| Issue | Status |
|---|---|
| Prefix bug (wrong iXBRL namespace prefix → zero facts extracted) | **Fixed** (prior task) — ~291,802 filings affected, 2014-2022 |
| Comma-as-decimal number formats (`numdotcomma`/`numcomma`/`numspacecomma`/`numcommadecimal`) | **Fixed** — verified against real archive data (a real `CashBankOnHand` fact literally read as `3.349` before, `3349` after) |
| Unrecognised numeric formats | **Fixed** — now null + counted, never guessed (previously silently misparsed with the default comma-stripping logic) |
| Plain-XML filings (301,141 archive-wide, 0.84%) | **Fixed** — routed through an `ixbrlparse` adapter, verified 100% agreement with Arelle on shared facts across 186 real filings |
| Nested facts (an inner fact lost or merged into an outer fact's text) | **Not fixed, by decision** — measured at only 0.0015% of numeric facts and zero impact on any published WIDE column; documented as a known limitation rather than fixed, given the cost/benefit at that rate |
| Continuations (`ix:continuation` chains — only the first text fragment kept) | **Not fixed, by decision** — non-numeric-only impact; the public LONG dataset only keeps short allowlisted metadata fields, so this doesn't reach publication either |
| Multi-member contexts (25.3% of filings) and typed-member contexts (20.1% of filings) | **Still not captured, by design** — out of scope for this task; documented with exact counts rather than silently omitted. Every typed dimension found in a live scan is code-shaped (sequence numbers, e.g. distinguishing "director 1" from "director 2"), not name-shaped — no personal-data concern identified, but this was descriptive, not a decision to start capturing them |

## 6. Corrected LONG completeness claim

**Was**: LONG keeps "every concept, all-fact, exactly as read."

**Now**: replace with the exact statement from `docs/accounts-limitations.md` (Phase F) —
multi-member and typed-member contexts are skipped by design, with the counts in the table
above. If a slide repeats the old "every concept, all-fact" phrasing verbatim, it must change;
that claim is materially incorrect at current measured rates (37.9% of filings —
13,583,718 — have a multi-member context, a typed-member context, or are plain-XML; the
25.3%/20.1% multi-member/typed figures overlap heavily, so they don't simply add).
