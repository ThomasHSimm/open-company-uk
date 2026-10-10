# Validation feasibility after Handoff 10

**Status:** design and feasibility only. No evaluation was run for this handoff. The September
2026 joined table is a current/future baseline candidate; it is **not** treated as historical
pre-event data.

## Evidence standard

This review uses two labels:

- **Checked** means verified in code, a local manifest/schema, an existing report, or a bounded
  local aggregate. Paths are cited beside each finding.
- **Assumption / requires approval** means the repository does not establish the fact. It must be
  confirmed or supplied before an evaluation can rely on it.

No individual company records or identifiers are reported here. The only new empirical work was
bounded metadata/schema inspection, a 237,391-row label aggregate (24.8 MB), and cache-envelope
metadata over 1,013 locally cached companies. No accounts WIDE, register or PSC full-data scan was
run.

## 1. What validation already occurred

The claim that no validation has ever occurred is incorrect.

### Correctness fixes are present

- **Checked — exclusion gate.** `evaluate()` classifies `excluded_status` before rule IDs, matching
  `score_all()` so dissolved/closed companies do not receive adverse-hit credit
  ([`validation/evaluate.py`](../src/ukcompany/validation/evaluate.py),
  [`score.py`](../src/ukcompany/score.py)). The synthetic outcome-bucket test includes a dissolved
  labelled company and expects `excluded`, not `flagged_adverse`
  ([`test_insolvency_validation.py`](../tests/test_insolvency_validation.py)).
- **Checked — cohort scope.** The CLI now requires `--positives`; `evaluate()` iterates that explicit
  set rather than every labelled company present in the shared cache
  ([`cli.py`](../src/ukcompany/cli.py), [`validation/evaluate.py`](../src/ukcompany/validation/evaluate.py)).
  A synthetic test supplies two cached labels but selects one and gets one outcome
  ([`test_insolvency_validation.py`](../tests/test_insolvency_validation.py)).
- **Checked — defect history.** The first run's invalid 500/501 headline came from bypassing the
  exclusion gate and admitting an older cached positive. The corrected run is recorded as 298
  excluded + 202 flagged + 0 genuine misses + 0 unavailable
  ([`AUDIT.md`, “Validation reconciliation fix”](AUDIT.md#validation-reconciliation-fix-and-disposition-reframe-2026-08-07),
  [`status-2026-10.md`, Q1](status-2026-10.md#q1--validation-run)).

### What the corrected run measured

**Checked — it measured current-state detection/agreement, not pre-event prediction.** The local
report compares Insolvency Service cases registered through 2024-04 with Companies House API
responses fetched in 2026-08. The two adverse triggers are `STATUS_INSOLVENT` and
`INSOLVENCY_ADVERSE`, which restate current registrar status or the same filed insolvency cases
([`validation/evaluate.py`](../src/ukcompany/validation/evaluate.py),
[`rules.md`](rules.md), local `data/insolvency-validation.md`). Consequently, 100% conditional
recall among 202 screenable positives establishes agreement/detection of an already-recorded event.
It does not establish lead time, prospective recall, precision, or general predictive performance.

The corrected local positive disposition is:

| outcome | count | valid interpretation |
|---|---:|---|
| excluded by current pipeline status | 298 | current-state exclusion; not a detected historical case |
| current adverse rule fired | 202 | agreement/detection after the event was recorded |
| genuine current-state miss | 0 | none among the 202 currently screenable cases |
| cached 404, status moved, not fetched | 0 | none in this selected sample |

### Control results do exist locally

**Checked — local, gitignored evidence.** `data/control-numbers.csv` contains 499 rows after its
header; one company number is invalid under the current normaliser, leaving 498 valid unique
controls. The corrected local report records 3/498 (0.6%) with at least one current high-severity
flag, broken down by the old age-band labels (`data/insolvency-validation.md` and
`data/control-numbers.csv.strata.json`). The report is not committed because `data/` is gitignored.

That 0.6% is a **current flag rate in an unlabelled sample**, not a false-positive rate. It has two
additional limits:

1. The controls were active in the 2026-08 register, not members of the risk set at each historical
   event date ([`validation/control.py`](../src/ukcompany/validation/control.py)).
2. **Checked semantic mismatch:** the label file's `month_registered` runs from 2012-01 through
   2024-04, and the existing report describes that as the insolvency-registration window. The audit
   and sampler also call it the insolvency-registration month
   ([`AUDIT.md`](AUDIT.md#positives-sampling--the-missing-symmetric-step-f-v2d),
   [`validation/sample.py`](../src/ukcompany/validation/sample.py)). But `stratify_targets()` passes
   it to `age_band()` as if it were company incorporation month
   ([`validation/control.py`](../src/ukcompany/validation/control.py)). The old control was therefore
   SIC-stratified but not validly company-age matched.

The old control result remains evidence that the pipeline was exercised end to end. It is not a
historical matched-risk-set comparison and should not be reused as one.

## 2. Historical source and feature feasibility

### Source matrix

| source | checked local coverage and provenance | event/effective date versus availability | historical reconstruction | corrections, overwrites and missing history | feasibility |
|---|---|---|---|---|---|
| Register | Complete manifests for 2026-08-01 (5,695,466 source rows; downloaded 2026-08-06) and 2026-10-01 (5,704,712; downloaded 2026-10-05), with feature reports at both dates (`data/snapshot/2026-08/manifest.json`, `data/snapshot/2026-10/manifest.json`). | Incorporation, due and cessation fields can carry older effective dates; the value was observed only in the dated snapshot. Download date is later than snapshot date. | Exact only at the two local snapshots. No local register state overlaps the 2012–2024 outcome window. | Intermediate changes and overwritten/corrected values are absent. Today's live/surviving population omits companies no longer in the selected snapshot. | **Prospective/current usable; historical unavailable.** Never back-cast a 2026 value from its old effective date. |
| Accounts | 153 complete monthly archives, continuous 2014-01–2026-09; v2 covers 152 months through 2026-08 and the internal extension adds September (`docs/accounts-coverage.md`, `docs/accounts-internal-202609-stage1.md`, local `data/accounts/v2-internal-202609/manifest.sqlite`). Cell provenance records source year/month, member and made-up-to date. | `period_end` / `made_up_to_date` are accounting/effective dates. `source_year`/`source_month` is the registration month in which the filing entered the bulk product. The consolidated ZIP appears after month-end, not at month-end (`docs/design-accounts-features.md` §1.2). | Exact cell-level first-seen reconstruction is possible from provenance for T >= 2014-01. Existing row-level features are a measured approximation; see below. | `latest` incorporates later restatements and leaks. `as_first_reported` keeps each cell's earliest filing, but later filings can add formerly absent cells. Non-iXBRL/PDF-only filings and absent tags remain missing. | **Historically usable at cell level; row-level approximation needs sensitivity checks.** Only source overlapping labels. |
| PSC | Complete 2026-09-25 32-part manifest (downloaded that day), plus local 2026-09-18/25 loads and feature reports (`data/psc/2026-09-25/manifest.json`, feature/load reports). | `notified_on` and `ceased_on` are effective dates. Availability is established only by the snapshot/download; an old effective date does not prove the record was known then. | Exact only at the local September 2026 snapshots. No overlap with historical outcomes. | Corrections, deleted records and intermediate statement states are not recoverable from two current snapshots. Point-in-time verification-cycle fields can decrease (`docs/data-dictionary.md`). | **Prospective/current usable; historical unavailable.** PSC regime also starts only in 2016. |
| Officers | Current API cache for 1,013 companies, fetched 2026-08-03–07; all have profile/officer/PSC resources and there are zero archived officer responses in `history/` (bounded local cache-envelope aggregate; cache behavior in [`cache.py`](../src/ukcompany/cache.py)). | `appointed_on`/`resigned_on` are effective dates; cache `fetched_at` is when this repository knew the response. Filing/registration delay for appointment changes is not retained. | A current list can describe recorded appointment history, but cannot prove what the API showed at an earlier T. | Cache code archives changed responses, but this local cohort has no officer history. Corrections/removals before the 2026 fetch are invisible. | **Not usable for historical prediction; prospectively usable if frozen repeatedly.** |
| Filing history | The fetch layer explicitly says filing history is phase 1.1 and is not implemented; no local filing-history endpoint cache exists ([`fetch.py`](../src/ukcompany/fetch.py)). | Filing/action dates would not by themselves establish API availability; no local response timestamps exist. | None. Accounts monthly archives are a separate product, not a substitute for general filing history. | Entire source history is absent. | **Unavailable; requires new implementation/data and approval.** |
| Charges | Register snapshots contain four current mortgage-count fields at 2026-08/10. The 1,013 current profiles carry only a charges link/deprecated boolean; the charges endpoint is not fetched ([`fetch.py`](../src/ukcompany/fetch.py), [`data-dictionary.md`](data-dictionary.md)). | Snapshot counts are state at snapshot T. A profile link observed in 2026 does not establish when a charge was created or satisfied. | Exact counts only at the two 2026 register snapshots. No event-level historical charge data. | Changes between snapshots and event dates are unknown; a count cannot reconstruct the sequence. | **Prospective/current counts usable; historical unavailable.** Do not substitute `n_charges > 0` for the existing link-based rule without approval. |

### Accounts point-in-time caveat

**Checked.** In `as_first_reported`, each WIDE cell selects its earliest source archive. The row's
`row_available_yyyymm` is then the **maximum** source month across selected cells
([`accounts/pivot.py`](../src/ukcompany/accounts/pivot.py),
[`accounts/ooc.py`](../src/ukcompany/accounts/ooc.py)). Existing features keep only rows whose
row-level maximum is `<= T` ([`accounts/features.py`](../src/ukcompany/accounts/features.py)).

This creates a conservative but time-varying edge case: if a later filing adds a concept missing
from the original filing, the row's maximum availability moves later. A rebuild made after that fill
can exclude the entire row from an earlier T even though a partial row was genuinely available then.
The current corpus measured 1,211/33,513,017 rows (0.0036%) whose cells span multiple archive
months (`docs/design-accounts-features.md` §1.4). Handoff 10 added 28 populated cells to existing
first-reported rows while changing zero previously populated values
([`accounts-internal-202609-stage1.md`](accounts-internal-202609-stage1.md)). The extension audit
intentionally excludes `row_available_yyyymm` from its value-change gate
([`accounts/extension_audit.py`](../src/ukcompany/accounts/extension_audit.py)).

Therefore:

- cell values from later filings do not leak into an earlier cutoff;
- current row-level eligibility can still become more conservative after a later fill;
- a historical evaluation should reconstruct selected cells with
  `source_year * 100 + source_month <= T`, or at least
  compare exact cell-level and current row-level eligibility and stop if the case-cohort difference
  exceeds the predeclared tolerance;
- registration month is not monthly ZIP publication time. A strict operational-availability
  sensitivity must lag monthly accounts by one archive publication cycle.

### Coverage is differential

**Checked current-snapshot evidence, not assumed historical constancy.** At T=2026-07, 70.38% of
live register companies had any accounts feature. Coverage was 95–99% for micro, total-exemption,
abridged and dormant categories; about 34–50% for full/group/subsidiary categories; and about zero
for Limited Partnerships, CIOs and Overseas Entities
([`design-accounts-features.md`](design-accounts-features.md#5-coverage--strongly-size-skewed-the-headline-caveat)).
The T=202609 join records the same shape in its category breakdown
(`data/join/v1-internal-202609/governed/join_manifest.json`).

Coverage also changes over time. Local archives are absent before 2014; iXBRL adoption was about
97% from 2014 after a much lower 2011–2013 regime, and employee-count tagging changes sharply from
about 24% in 2019 to 33% in 2020 and 85% in 2021
([`accounts-limitations.md`](accounts-limitations.md#coverage-continuous-2014-01-through-2026-08),
[`accounts-extractor.md`](accounts-extractor.md)). Equity missingness varies non-randomly by month.
Historical analyses must report coverage by outcome year and case type; current account category or
company type cannot be attached retrospectively without historical register data.

## 3. Outcome and cohort feasibility

### Label window and supported outcomes

**Checked local aggregate using the existing loader.** The 24.8 MB file contains 237,391 source
rows. Pre-deduplication exclusions are 5,740 bulk + 7,102 Administration-to-CVL + 736 unusable
company numbers + zero field-shifted rows = 13,578, leaving 223,813 rows. The loader then removes
3,352 subsequent rows for an already retained company, leaving 220,461 unique companies with one
retained label row each. The source has no event identifier, so 220,461 is not asserted to be a
unique-event count. Its month range is 2012-01–2024-04 (148 months). Raw retained case types are:

| raw case type | retained labels | evaluation treatment |
|---|---:|---|
| Creditors Voluntary Liquidation | 158,990 | supported adverse |
| Compulsory Liquidation | 38,007 | supported adverse |
| In Administration | 19,617 | supported adverse |
| Corporate Voluntary Arrangement | 3,646 | supported adverse |
| Administrative Receiver | 161 | currently maps to `other`; unavailable for per-type evaluation |
| Moratorium | 40 | currently maps to `other`; unavailable for per-type evaluation |

The four supported adverse groups total 220,260. For an accounts reference 12 months before the
outcome month, 165,292 supported labels fall in 2015-01–2024-04: 124,736 CVL, 25,066 compulsory,
13,436 administration and 2,054 CVA. These are label-side candidates only; accounts match and
feature availability were not scanned in this design handoff.

### Historical overlap and risk sets

- **Case-only overlap: feasible for accounts.** Accounts start in 2014, so the 165,292 supported
  outcomes from 2015-01 onward can in principle receive a 12-month-prior accounts cutoff. The
  resulting matched count is unknown until an approved bounded join is run.
- **Historical register/PSC/officer/charge overlap: absent.** Their local observation dates are in
  2026. Old effective dates inside current records do not repair this gap.
- **Historical controls: not currently defensible.** The repository cannot identify the complete
  population alive and at risk at each 2012–2024 reference date. Sampling from the 2026 surviving
  register selects on survival and excludes historical companies that later dissolved or were
  removed. An accounts-filer-only risk set would still lack historical dissolution/strike-off state
  and would inherit iXBRL selection.
- **Do not exclude cases because they are dissolved today.** Current dissolution is downstream of
  many historical insolvencies. It is a current pipeline exclusion in the old agreement report,
  not a valid historical cohort exclusion.

### Outcome timing, delay and censoring

- **Checked:** the available outcome time is month-grained `month_registered`, described by the
  existing report as insolvencies registered in 2012–2024. It is not a date of distress onset and
  not a daily event time (`validation/report.py`, local label aggregate).
- **Unavailable:** the repository has no label-source manifest, publication timestamp, revision
  history or measured registration/publication delay. File modification time is local provenance,
  not proof of source availability. A prospective study must version and hash every outcome release.
- **Right censoring:** the current file stops at 2024-04. For a 12-month horizon, historical
  references after 2023-04 lack complete follow-up in this release.
- **Competing/lost states:** dissolution, removal or conversion without a supported insolvency
  label cannot be identified historically from present data. In a prospective study these require
  repeated dated register snapshots; otherwise unlabelled companies remain unlabelled, not
  confirmed negatives.

### Candidate prospective outcome source

The concrete candidate is the updated **Insolvency Service record-level company insolvency CSV**
used by the existing validation loader, currently stored locally as
`data/labels/record-level-data.csv`. The repository identifies it as the Insolvency Service
record-level publication and preserves its required fields and exclusions
([`validation/labels.py`](../src/ukcompany/validation/labels.py),
[`AUDIT.md`](AUDIT.md#insolvency-service-agreement-validation-harness)). Link companies by the
existing normalised `company_number`; define the event month from `month_registered`; retain the
four supported adverse case groups; and apply the existing bulk, Administration-to-CVL, malformed
number and duplicate handling.

- **Last verified coverage:** the checked local file runs through 2024-04. It cannot ascertain the
  proposed 2026-11–2027-10 outcomes.
- **Source identity still to verify:** the repository does not retain the official landing URL,
  release identifier or source checksum for this file. Before acquisition, the maintainer must
  approve the canonical official publication page and confirm that a successor release preserves
  the required fields and definitions.
- **Publication lag is unverified:** one unmanifested local file cannot establish release cadence,
  delay or revision policy. A three-calendar-month lag after the horizon is a conservative planning
  assumption only, not a checked property of the publication. Implementation must measure release
  date versus maximum covered month and use explicit official coverage notes where available.

## 4. Staged evaluation feasibility

### A. Case-only lead-time analysis

**Feasible now, but accounts-only and not a rule-performance study.** This follows from the
continuous 2014-01 onward accounts archives and cell-level provenance, contrasted with the 2012-01
to 2024-04 label window (`docs/accounts-coverage.md`,
`data/accounts/v2-internal-202609/manifest.sqlite`, bounded local label aggregate).

- **Eligible population:** all companies in the four supported adverse label groups with an outcome
  month from 2015-01 through 2024-04, a valid normalised company number, and at least one accounts
  fact whose cell provenance shows availability by the selected historical cutoff. There are
  165,292 label-side candidates for the primary 12-month cutoff before accounts linkage and
  availability filtering. Never require presence in the 2026 register or exclude a case because it
  is dissolved today (bounded local label aggregate; [`validation/labels.py`](../src/ukcompany/validation/labels.py)).
- **Eligible source/features:** exact cell-level `as_first_reported` accounts values and provenance;
  latest/prior period, equity, current assets, creditors within one year, net current assets, cash,
  negative-equity/current-liability indicators, ratios and changes. Exclude current register
  `accounts_category`; treat employee measures as secondary because of the 2020–2021 tagging break.
  No register, PSC, officer, filing-history or charge value is historically reconstructable over
  this label window from the local evidence in the source matrix.
- **Reference dates:** primary T is the end of the month 12 months before `month_registered`;
  sensitivities use 6 and 24 months. At each T, use only cells with
  `source_year * 100 + source_month <= T`. Exact historical ZIP publication dates are not retained,
  so the operational-availability sensitivity must use a clearly labelled one-cycle lag
  approximation rather than claim exact download-day knowledge.
- **Useful analyses now:** report the fraction of cases with any eligible filing and each eligible
  attribute at each lead time; distributions and predeclared descriptive states among observed
  cases; paired within-case changes where two periods were already available; and coverage by
  event year and case type. This establishes whether signals were genuinely recorded before the
  event-registration month, how early, and for which subset of later cases.
- **What it cannot establish:** rule recall (no existing rules use these financial attributes),
  specificity, precision, false-positive rates, population prevalence, separation from non-cases,
  causality or population predictive performance.
- **Selection limits:** the cohort is conditional on becoming a recorded adverse case and on having
  parseable iXBRL/plain-XML accounts. Coverage differs by year, company type and filing practice;
  companies with PDF-only/non-iXBRL accounts and non-filers are absent. Historical company type,
  accounts category, alive-at-T status and competing dissolution cannot be recovered, so they must
  not be imputed from 2026 values.
- **Approval/new work:** an exact cell-cutoff feature builder or predeclared row-level sensitivity;
  no new source data is required. This is useful temporal/coverage validation, not validation of the
  existing rules.

### B. Matched historical risk-set evaluation

**Not currently feasible.** The only local register observations are the 2026-08-01 and 2026-10-01
manifests, after the label window, and the old controls were sampled from the 2026-08 active
snapshot rather than historical risk sets (`data/snapshot/2026-08/manifest.json`,
`data/snapshot/2026-10/manifest.json`, [`validation/control.py`](../src/ukcompany/validation/control.py)).

- **Required target:** companies alive, in scope and event-free at each historical T, with controls
  selected from that same T and followed over the same horizon.
- **Blockers:** no historical register population/status snapshots, no historical PSC/officer/
  charges states, no general filing history, no complete non-event/censoring information, and
  accounts-only selection is strongly differential.
- **What would make it feasible:** approved historical register snapshots or another versioned
  register-history source covering the study dates; versioned outcome releases; and explicit
  handling of dissolution/strike-off competing events. Historical PSC/officer features require
  their own snapshots, not today's records with old effective dates.

### C. Prospective evaluation from dated snapshots

**Feasible in design and recommended as the first actual rule evaluation, but follow-up data is not
yet available.** The frozen join records dated source states and hashes, while the current outcome
file stops at 2024-04 (`data/join/v1-internal-202609/governed/join_manifest.json`, bounded local
label aggregate).

- **Baseline availability:** the governed Handoff 10 join finished at
  `2026-10-10T12:33:23.902905+00:00`; use 2026-10-10 as the operational freeze/enrolment date. Its
  component reference states are earlier: register 2026-10-01, PSC 2026-09-25 and accounts
  registration month <=202609
  ([`join-internal-202609-stage2.md`](join-internal-202609-stage2.md), local join manifests). This is
  a prospective baseline only; it is not backdated to 2026-09-30 operational availability.
- **Eligible existing predictive rules:** `ACCOUNTS_OVERDUE`, `CS_OVERDUE` and `PSC_UNRESOLVED`.
  `YOUNG_COMPANY` is an informational covariate. `STATUS_INSOLVENT` is prevalent-event detection and
  should define an exclusion, not be presented as prediction.
- **Unavailable rules:** `STATUS_STRIKEOFF` (detail absent), `INSOLVENCY_ADVERSE` and
  `SOLVENT_WINDING_UP` (case resource absent), `ADDR_DISPUTE` (flags absent), and the exact
  link-based `CHARGES_OUTSTANDING` definition. Missing rules must remain unavailable, never false.
- **Population:** register-base companies active and not already in an insolvency-type state at
  baseline. Preserve `has_psc` and `has_accounts` as coverage, not signals. When the updated outcome
  source becomes available, exclude every company whose earliest supported registration month is
  2026-09 or earlier as prevalent by enrolment. Classify October 2026 separately as an ambiguous
  baseline-month exclusion: month-grained labels cannot determine which October registrations
  preceded the 10 October build, so none count as prospective predictions, but the whole month is
  not asserted to be prevalent.
- **Outcome/horizon:** first supported adverse registration during 2026-11 through 2027-10. October
  2026 is excluded as the ambiguous baseline month because month-grained outcomes cannot be ordered
  around the 10 October availability date.
- **What it can establish:** baseline per-rule firing rates, prospective case recall, and rule-specific
  event/non-event separation over a fixed horizon, subject to outcome completeness and censoring.
- **Outcome-ready date:** the 12-month event horizon ends 2027-10-31, but that is not the analysis
  date. Analysis waits for the first approved versioned release explicitly covering 2027-10 and
  its observed publication lag. Under the unverified three-month planning assumption, the earliest
  planned freeze is 2028-01-31; a later source release moves that date later.
- **Required new data/approval:** updated versioned Insolvency Service outcomes through 2027-10;
  prospective register snapshots during follow-up; a verified official source URL/release cadence;
  and approval of the outcome freeze/lag and matched-control design. No result can be run before
  those conditions are met.

## Conclusion

Existing data support (1) the already-completed current-state insolvency agreement check and (2) an
accounts-only historical case lead-time study that can begin after plan approval without new data.
That study can validate temporal reconstruction, coverage and the presence/timing of accounts
signals among later cases; it does **not** support specificity, precision or population prediction.
Historical matched controls remain unavailable. The smallest defensible evaluation of the existing
rules is the prospective design in `validation-run-plan.md`; it requires future outcomes and
register observation. No predictive claim should be made from the current 100% agreement result.
