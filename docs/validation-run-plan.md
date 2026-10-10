# Proposed validation run plan

**Approval gate:** this plan must be reviewed and committed before implementation. This document is
the committed design; no evaluation has been run under it.

## Recommendation

Use two explicitly separate studies:

1. after approval, begin an **accounts-only historical case lead-time study** using existing data;
   this validates temporal reconstruction, coverage and whether accounts attributes predate later
   recorded events, but not rule or population performance; and
2. retain the **12-month prospective, nested risk-set evaluation** as the smallest study that can
   validly report existing-rule firing rates, prospective recall and a comparison-cohort flag rate.
   It cannot run until future outcomes and follow-up states have been observed.

The already-completed 500-positive run remains a current-state detection/agreement check. An
accounts-only case study is useful now, but it is not a substitute for prospective rule evaluation
because no existing rule uses the historical financial attributes and no historical controls can
currently be identified
([`validation-feasibility.md`](validation-feasibility.md)).

## 1. Historical case-only study available now

### Cohort and cutoffs

- Start with the 165,292 label-side candidates in the four supported adverse groups with
  `month_registered` from 2015-01 through 2024-04 and a valid normalised company number.
- Reuse `load_labels()` exactly: apply the bulk, Administration-to-CVL, malformed-month and invalid
  company-number exclusions first; retain the first source row for each normalised company number;
  then keep the four supported adverse groups and the date window. Report every loader disposition,
  including duplicate rows and unsupported retained case types. The analysis unit is therefore one
  retained event row per unique company, not every insolvency proceeding for that company.
- Do not require presence in a current register and do not exclude companies dissolved today.
- Primary cutoff T is month-end 12 months before the event-registration month; predeclared
  sensitivities use 6 and 24 months. Subtract whole calendar months from `month_registered`; for
  example, an event in 2020-07 has T=2019-07 at the 12-month lead.
- A case enters an attribute-specific denominator only when the relevant account cell has
  first-reported provenance `source_year * 100 + source_month <= T`. Report zero-filing,
  source-row-present and attribute-observed states separately.
- Use no current register, PSC, officer, filing-history or charge values. Their local observations
  postdate the outcome window and cannot be back-cast.

### Period and attribute definitions

For each case, lead and availability convention, join cell provenance to the matching
`as_first_reported` WIDE cell on company, period end and mapped column. Exclude a cell unless its
own source year/month is within the cutoff. Never gate on `row_available_yyyymm`, and never expose a
WIDE value whose cell provenance is later than the cutoff. A period is available when at least one
planned cell is eligible. Rank available periods by parsed `period_end`, newest first, using the
existing plausible-date bounds and 18-month prior-period gap rule in
[`accounts/features.py`](../src/ukcompany/accounts/features.py).

Analyse only these predeclared attributes from the latest available period: `equity`,
`current_assets`, `creditors_within_one_year`, `net_current_assets`, `cash`, `negative_equity`
(`equity < 0`), `net_current_liabilities` (`net_current_assets < 0`), `current_ratio`
(`current_assets / creditors_within_one_year`, null for zero/missing denominator), `employee_band`
and `employees_unit_anomaly`. Also report latest/prior period end, periods available, months since
latest period end, prior gap, and `d_equity`, `d_net_current_assets`, `d_cash` only when the relevant
latest/prior cells are both observed and the period gap is at most 18 months. Do not use
`accounts_category` or any additional WIDE concept.

Denominators are fixed as follows:

- **candidate denominator:** every unique retained case in the fixed label cohort;
- **any-accounts coverage:** candidates with at least one eligible planned cell at that cutoff;
- **attribute coverage:** candidates with that exact derived attribute observed;
- **binary signal rate:** observed `true` divided by observed (`true` + `false`) for
  `negative_equity`, `net_current_liabilities` and `employees_unit_anomaly`; null is unavailable,
  never non-firing;
- **numeric/category summaries:** only observed values, always accompanied by observed count and
  candidate-denominator coverage; and
- **change coverage:** candidates with the corresponding change observed under the 18-month rule.

Report all denominators and counts at every 6/12/24-month cutoff and for both registration-month and
one-cycle-lag conventions. Do not compare conventions or lead times without also reporting their
coverage.

### Outputs and limits

Report aggregate counts and intervals only: linkage and filing coverage by event year/type, each
attribute's observed coverage at each lead time, distributions of frozen accounts attributes, and
paired within-case changes where both periods were already available. Separately repeat under the
conservative one-cycle-lag convention that an accounts registration month becomes usable only in
the next month. This is an approximation: exact historical ZIP publication dates are not retained,
so it must not be described as exact artifact availability.

This study can establish whether reconstructable accounts signals existed before recorded events,
how early, and in which covered subset of cases. It cannot estimate recall of the existing rules,
specificity, precision, false-positive rates, population prevalence or population predictive
performance. Do not invent thresholds, tune attributes, create rules or create a composite score.

Implementation must stop if exact cell-level provenance cannot be enforced, if cohort accounting
does not close, or if only current/latest/restated values are available. Report differential
coverage rather than treating missing accounts as no signal. No new source data is required, but
the maintainer must approve this descriptive estimand and the 12/6/24-month timing conventions
before implementation.

## 2. Prospective baseline and eligible population

### Baseline

- **Baseline artifact:** governed `data/join/v1-internal-202609/governed/` generated at
  `2026-10-10T12:33:23.902905+00:00` according to its manifest.
- **Operational freeze/enrolment:** 2026-10-10, after the output completed. Never describe
  2026-09-30 or any component reference date as the prediction date.
- **Source reference states:** register 2026-10-01, PSC 2026-09-25, accounts registration month
  <=202609. These describe input state, not when the joined prediction baseline became available.
- **State-lag limitation:** enrolment uses the 2026-10-01 register state observed in the join; it
  cannot see register changes from 2–10 October. Excluding all October outcomes prevents those
  events being credited as prospective predictions but does not make the baseline a 10 October
  snapshot.
- **Accounts artifact availability:** the September ZIP was published after month-end
  ([`accounts-internal-202609-stage1.md`](accounts-internal-202609-stage1.md)).
- **Freeze:** copy the existing manifest hashes, code commit and complete output schema into the run
  manifest before outcomes are obtained. Never rebuild baseline values after seeing outcomes.

### Risk set

Include one row per normalised company number that:

1. is present in the frozen 2026-10-01 register base;
2. has `reg_company_status = active` at baseline;
3. has no supported adverse insolvency label with registration month <=2026-10;
4. is not already in an insolvency-type or excluded/closed state at baseline; and
5. has a valid unique key.

Do not require `has_psc` or `has_accounts`; those flags define source coverage. Do not remove a
company later because it dissolves. Later dissolution/removal is a follow-up state, not a baseline
eligibility rewrite.

The outcome source available today ends in 2024-04, so this event-free check remains provisional
until the approved successor release fills the gap through enrolment. At outcome freeze, companies
with an earliest supported registration month through 2026-09 are prevalent and excluded from both
case and control cohorts. October 2026 is a separate **ambiguous baseline-month exclusion**:
month-only labels cannot distinguish events before versus after the exact 10 October build time, so
October events are neither assumed all prevalent nor credited as prospective predictions. The
outcome is registration, not unobserved distress onset; a process beginning before enrolment but
first registered later cannot be identified from these labels and must be disclosed as a limitation.

**Checked population bound:** the register baseline contains 5,704,711 rows. The exact active,
event-free risk-set count has not been scanned in this design handoff and must be the first aggregate
reported by implementation (`data/join/v1-internal-202609/governed/join_manifest.json`).

## 3. Prospective outcome collection and follow-up

- **Primary outcome:** first registration of one of the four supported adverse groups: Creditors
  Voluntary Liquidation, Compulsory Liquidation, In Administration, or Corporate Voluntary
  Arrangement. Apply the existing bulk and Administration-to-CVL duplicate exclusions
  ([`validation/labels.py`](../src/ukcompany/validation/labels.py)).
- **Follow-up window:** outcome month 2026-11 through 2027-10 inclusive. This is a 12-month outcome
  horizon after the operational baseline month, not a claim that labels are complete on 2027-10-31.
  Exclude October 2026 as an ambiguous baseline month because month-only timestamps cannot order
  its events around the 2026-10-10 freeze; do not classify the entire month as prevalent.
- **Concrete candidate source:** a successor to the official Insolvency Service record-level company
  insolvency CSV already consumed as `data/labels/record-level-data.csv`. Link on the existing
  normalised `company_number`, take event month from `month_registered`, retain the four controlled
  adverse groups and apply the existing exclusions
  ([`validation/labels.py`](../src/ukcompany/validation/labels.py)).
- **Last verified coverage:** the current checked file ends at 2024-04. Its local modification time
  does not prove source publication time, and the repository does not preserve its official landing
  URL, release identifier, checksum at acquisition, cadence or revision policy.
- **Source-verification gate:** before acquisition, record and approve the canonical official
  publication URL, publisher release identifier, documented coverage, field definitions and reuse
  terms. For every acquired release record retrieval time, SHA-256, row count, minimum/maximum event
  month, exclusions, duplicates and schema drift.
- **Publication lag:** unknown from checked evidence. For scheduling only, assume three calendar
  months after the horizon; label this assumption unverified until release dates and maximum covered
  months are observed. The horizon ends 2027-10-31, so the earliest planned label freeze is
  2028-01-31, or later if no approved release explicitly covers 2027-10 by then. Analysis starts
  only after that coverage gate passes; rerun against a release three months later to assess
  revisions.
- **Censoring/competing states:** retain monthly prospective register snapshots through follow-up.
  Record dissolution, conversion/closure and removal. If those states cannot be observed, controls
  remain unlabelled and their statistic must be called a **control flag rate**, not a false-positive
  rate or specificity.

## 4. Rules and attributes

No rule definitions, thresholds, severities or composite scores may change after baseline freeze.

| existing rule | baseline treatment | reason |
|---|---|---|
| `ACCOUNTS_OVERDUE` | evaluate | exact baseline register feature exists |
| `CS_OVERDUE` | evaluate | exact baseline register feature exists |
| `PSC_UNRESOLVED` | evaluate where PSC source semantics make it applicable; retain missing-source bucket | active statement codes exist in governed PSC features |
| `YOUNG_COMPANY` | report as informational covariate, not adverse predictor | baseline age exists; rule is severity `info` |
| `STATUS_INSOLVENT` | use to identify prevalent event/exclusion; do not claim prospective performance | firing means insolvency already recorded |
| `STATUS_STRIKEOFF` | unavailable | status detail is absent from the joined schema |
| `INSOLVENCY_ADVERSE` | unavailable | insolvency case resource is absent |
| `SOLVENT_WINDING_UP` | unavailable | case types are absent |
| `ADDR_DISPUTE` | unavailable | dispute/undeliverable fields are absent |
| `CHARGES_OUTSTANDING` | unavailable under its exact definition | joined table has charge counts, not the profile link trigger; do not silently substitute |

Financial accounts columns (`negative_equity`, `net_current_liabilities`, ratios and changes) may be
reported as frozen attributes and coverage strata. They are not rules and must not be thresholded or
combined into a score in this study.

## 5. Cohort sampling and size

Use a nested case-control design inside the frozen risk set:

1. retain **all incident supported cases** in the follow-up window;
2. for each case, select up to four controls from companies still under observation at the start of
   that case's outcome month;
3. match without replacement within case month on baseline company type, accounts category, SIC
   section and coarse age band; include `has_accounts` and `has_psc` in exact or coarsened matching
   where support permits;
4. use a deterministic seed and record target/achieved strata; controls can later become cases and
   then contribute as cases at their event time.

The current labels contain 22,993 supported events in 2022 and 26,221 in 2023, but these are
historical counts without a contemporaneous denominator and are **planning context, not a forecast**
(bounded local aggregate from `data/labels/record-level-data.csv`). Sample size is therefore governed
by observed prospective cases:

- analyse overall recall only if at least **400 incident cases** occur, giving a worst-case 95%
  binomial half-width of about 5 percentage points;
- report a case-type-specific estimate only with at least **100 cases** in that type (worst-case
  half-width about 10 percentage points); otherwise pool it into overall results and show its count;
- use all cases, even above those thresholds; select at most four controls per case because the
  principal gain comes from cases, while larger control ratios add limited precision;
- if fewer than 400 cases occur, extend follow-up under a newly approved amendment or stop with
  descriptive counts. Do not alter rules or select a higher-risk cohort after seeing outcomes.

## 6. Temporal and leakage checks

Implementation must fail before analysis unless all checks pass:

1. baseline output and every source/report hash equal the frozen join manifests;
2. register date = 2026-10-01, PSC date = 2026-09-25 and accounts T = 202609;
3. no accounts feature derives from `row_available_yyyymm > 202609`, and only
   `as_first_reported` is used;
4. no feature, status, correction or source row fetched after the 2026-10-10 baseline freeze enters
   baseline;
5. no October 2026 outcome enters follow-up;
6. all controls are in the risk set immediately before their matched case month;
7. no current/final status is copied backward to baseline;
8. no outcome field, post-baseline snapshot, label presence or censoring state enters matching or
   rule firing;
9. rule registry Git object and study code commit are recorded before unblinding outcomes; and
10. company-number keys remain unique and cohort accounting closes exactly.

## 7. Coverage gates and stop criteria

Report, before any rule result:

- baseline risk-set size and exclusions;
- `has_psc` and `has_accounts` overall and by company type/accounts category;
- each rule's observed, missing/not-applicable and firing counts;
- prospective case counts by type/month and outcome-source completeness;
- matched-control target/achieved counts and unmatched cases; and
- censoring/competing-state counts.

Stop or downgrade to descriptive reporting when:

- outcome coverage does not explicitly include the full horizon;
- fewer than 400 incident cases exist overall;
- more than 5% of cases cannot obtain at least one matched control (also report the four-control
  attainment rate);
- any cohort stratum has differential source coverage exceeding 20 percentage points between cases
  and controls after matching;
- a rule input is missing for more than 20% of either cases or controls, unless missingness is the
  documented source-applicability state and results are restricted to the applicable denominator;
- register follow-up cannot distinguish event-free observation from dissolution/removal; or
- any hash, date, uniqueness, temporal or leakage assertion fails.

Thresholds are design gates, not tuning targets. They may be changed only in a reviewed amendment
written before outcome analysis.

## 8. Estimands and uncertainty

For each evaluable rule, report separately:

1. **baseline firing rate** in the whole eligible risk set, with Wilson 95% interval;
2. **prospective case recall:** cases firing at baseline / all incident cases, with Wilson 95%
   interval;
3. **available-input recall:** the same numerator over cases with an observed/applicable input;
4. **missing-inclusive lower bound:** treat missing rule input as not firing, clearly labelled;
5. **control flag rate:** matched controls firing at baseline / matched controls, with a cluster-aware
   95% interval by matched set; and
6. rule-specific risk difference and risk ratio between baseline fire/non-fire groups, with matched
   or sampling weights as appropriate.

Unless complete outcome ascertainment and follow-up are established, item 5 remains a **control flag
rate**. It is not precision, specificity or a false-positive rate. Even with complete horizon
ascertainment, “no registered event in 12 months” means horizon-specific non-event, not confirmed
negative for all future insolvency.

Do not report one aggregate “any rule” score as the primary result. If an unweighted “any existing
evaluable rule fired” diagnostic is shown, label it descriptive and retain every per-rule result.

## 9. Missing inputs and unavailable rules

- `has_psc=false` and `has_accounts=false` mean no matching source row, not a null attribute.
- A present source row with a null attribute is a separate missing-value state.
- Missing/unavailable never becomes `false`, zero or no-risk by imputation.
- Report denominators for all-source, source-present and attribute-observed populations.
- Keep unavailable rules in the result table with reason and `not evaluated`; do not drop them
  silently.
- Do not classify unlabelled companies as confirmed negatives unless the outcome and censoring gates
  above pass.

## 10. Predeclared sensitivity analyses

1. follow-up starts 2026-12 instead of 2026-11 (washout for source staleness/near-baseline events);
2. six-month and 12-month horizons;
3. outcome freeze at first complete release versus the additional three-month lagged release;
4. complete-case versus missing-inclusive lower-bound rule recall;
5. results stratified by company type, accounts category, age band, SIC section, `has_accounts` and
   `has_psc`;
6. unmatched full-risk-set weighted estimates versus matched nested-case-control estimates;
7. companies censored at dissolution/removal versus treated as event-free only through censoring;
8. PSC 2026-09-25 baseline retained as dated versus excluding November outcomes to reduce the effect
   of its six-day pre-month-end gap; and
9. accounts registration-month convention versus a strict operational-availability convention
   lagged to the monthly ZIP publication.

No sensitivity may introduce a new threshold, rule or composite score after outcomes are observed.

## 11. Minimum additional data and approvals

The historical case-only study needs no new source data. Before implementing it, the maintainer must
approve its descriptive estimand, exact cell-level cutoff method, 12-month primary lead and 6/24-
month sensitivities.

The prospective study needs, at minimum:

1. use of the Handoff 10 governed join as a prospective baseline assembled on 2026-10-10;
2. the four supported outcome types and 2026-11–2027-10 horizon;
3. the canonical official URL and release/versioning procedure for the Insolvency Service
   record-level outcome CSV;
4. a verified publication-lag/completeness rule, replacing or approving the unverified three-month
   planning assumption;
5. versioned outcomes covering both pre-enrolment classification through 2026-10 and the complete
   follow-up through 2027-10;
6. prospective register snapshots for censoring and risk-set maintenance; and
7. the 4:1 matched-control design and matching variables.

**Stop after approval and implementation planning.** Do not run the evaluation, fetch data, tune
rules or publish results under this handoff.
