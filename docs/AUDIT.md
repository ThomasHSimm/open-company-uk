# Audit log

Implementation notes and assumptions that need live verification against the
real Companies House API. Append-only.

## Current state (as of 2026-08-07)

The core pipeline is built and fixture-tested: strict input validation,
rate-limited fetch/cache with response provenance and archive-on-change,
derivation, the rule registry, scoring, and generated rule/data-dictionary
documentation. Paginated officer and PSC resources, PSC statements, corporate
annotations, cessation and accounting-reference-date fields, and distinct
ECCTA identity-verification versus statement-filing counts are represented.

The cache-only insolvency validation harness is also built. It uses conditional
recall for adverse labels, a recent-positive sampler, and a monthly snapshot
control stratified by SIC section and company-age band. Because the control is
unlabelled, this is a positive-unlabelled (PU) design and cannot estimate
precision. Snapshot infrastructure dynamically discovers complete part sets,
hashes them in a provenance manifest, and lazily scans full-width data with
company numbers preserved as strings. A first representative live validation
run (roughly 500 positives and 500 controls) remains outstanding. Gazette
integration and the other parked extensions are not implemented; see
`docs/TASKS.md` for their status and constraints.

## Verification pass — A + B + 1.1c (2026-08-03)

Pre-task verification of the shipped work.

1. **Diff scope.** Cumulative diff vs the first commit touches only
   derive.py / fetch.py / rules.py / score.py / cli.py / tests/ / docs/ (+
   pyproject, see below). README.md and tests/test_validate.py changes are in
   commit `57099d7` ("Inestigate ten firms output"), which predates the agent
   work (now in `37dbe0f`) — confirmed clean in the working tree, i.e. they are
   not part of the agent diff.
2. **`_fetch_paginated` cannot spin.** Two independent termination guarantees:
   an empty/absent `items` page (`page_items` falsy) breaks immediately — the
   200-with-empty-items mid-sequence case — and every non-empty iteration
   strictly grows `len(items)` toward the fixed integer `total`. Even an API that
   ignores `start_index` and re-serves page 1 terminates (over-collects one page,
   then exits). One guard, shared across all three endpoints; covered by
   `test_loop_stops_on_empty_page_when_total_overstated`.
3. **Synthetic fixtures.** All fixture and inline test names are invented
   (`SYNTHETIC …`, single letters, `ACTIVE/FORMER OWNER`). No real personal data.
   (AUDIT.md itself names real *companies* — Carillion, two SLPs — tied to public
   company numbers; that is public register metadata, not officer/PSC PII.)
4. **Live pagination vs reality.** Drove `_fetch_paginated` live against real
   old PLCs with >100 officers: BARCLAYS BANK PLC (01026167) total_results=120,
   merged 120 across 2 pages (100+20), 120 distinct, 0 dups; BARCLAYS PLC
   (00048839) total_results=102, merged 102 (100+2, a genuine partial final
   page), 0 dups. Pagination matches reality.
   **PSC endpoint 404-vs-empty (decides psc_fetch_status semantics):** the two
   endpoints are ASYMMETRIC. The PSC *list*
   (`persons-with-significant-control`) returns **200 with empty `items`** for a
   company with no PSC record (07133426, NI017846, SL027366/747) — it does NOT
   404. The *statements* endpoint returns **404** when none are filed (200 only
   for the two SLPs). Consequence: `psc_fetch_status` (read off the list
   endpoint) is `ok`/`not_fetched` in practice and essentially never
   `not_found`; "no PSC" surfaces as a 200 with `psc_n_records=0` →
   `none_reported`, handled correctly. The `not_found` branch of `derive_psc`
   remains as defensive-only.
5. **PSC_UNRESOLVED trigger codes.** Re-verified verbatim against
   companieshouse/api-enumerations `psc_descriptions.yml` (single-quoted YAML
   keys): `steps-to-find-psc-not-yet-completed`, `psc-exists-but-not-identified`,
   `psc-details-not-confirmed` all present and correctly spelled. The notorious
   misspelling (`signficant`) is in the *different* key
   `no-individual-or-entity-with-signficant-control` — reaffirming the
   don't-normalise rule.

**Test-infra fix (pyproject.toml).** Cross-module test imports (`tests.
test_client`, `tests.conftest`) failed under the bare `pytest` console script
(`ModuleNotFoundError: No module named 'tests'`) because the project root was not
on `sys.path` — only `python -m pytest` added it. Added `pythonpath = ["."]` to
`[tool.pytest.ini_options]`. Out of the 1.1c diff scope but a genuine
green-suite fix; flagged here.

**Statement-filing attribute (follow-up to the id-verification decision).** Added
`n_officers_id_statement_filed` / `n_psc_id_statement_filed` (count of
`appointment_verification_statement_date` present) as their own Tier-2
attributes; verified/due stay keyed on `identity_verified_on`; no rule keys off
them. See the resolved assumption under Phase 1.1c.

## Phase 1.1c — severity semantics + live-finding corrections (2026-08-03)

Driven by the 2026-08 live-batch findings above.

**What changed**

- **Severity semantics (docs only).** `generate_rules_md()` now states that
  severity grades the SERIOUSNESS of the recorded state, not confidence, with an
  explicit high/medium/low/info gloss; the `Rule.severity` comment mirrors it.
  `score.py summarise()` now prints the `low` bucket (between medium and info).
  **No rule's assigned severity changed.** `docs/rules.md` regenerated.
- **PSC ceased counting — correctness fix.** `derive_psc` no longer relies on
  `ceased_on` alone. Precedence: (a) top-level `active_count`/`ceased_count`;
  (b) per-item `ceased` boolean; (c) `ceased_on` presence. The list resource can
  omit ceased items, so `psc_n_records` is now the register total (active +
  ceased), not `len(items)`. A disagreement between top-level and per-item tallies
  logs a WARNING and the top-level count wins (see
  `test_top_level_counts_win_on_disagreement_and_warn`).
- **ECCTA identity verification (live now).** New per-company counts from the
  `identity_verification_details` block on officer and PSC items:
  `n_officers_id_verified` / `n_officers_id_verification_due` and the PSC pair.
  Tier 2. Verified = block present; due = `appointment_verification_statement_
  due_on` set with no `identity_verified_on`.
- **PSC extras.** `has_super_secure_pscs` (profile flag) and
  `psc_natures_of_control` (sorted, distinct, verbatim natures across ACTIVE PSC
  records). No normalisation.
- **FIELD_DOCS caveats.** Added `has_been_liquidated` ("Inconsistently present …
  absence is None (unknown), never False - do not coerce"); `psc_fetch_status`
  now records the 404 = none-filed observation.

**Key names — as observed live (data/raw/, 2026-08), not invented**

- Officer `identity_verification_details` keys seen:
  `appointment_verification_statement_due_on`, `identity_verified_on`,
  `appointment_verification_start_on` / `_end_on`,
  `anti_money_laundering_supervisory_bodies`,
  `authorised_corporate_service_provider_name`, `preferred_name`.
- PSC block additionally carries `appointment_verification_statement_date`.
- PSC list item ceased marker: boolean `ceased` (active sample had
  `ceased=False`, `ceased_on=None`); top-level `active_count` / `ceased_count`.
- PSC natures under item `natures_of_control` (list, e.g.
  `ownership-of-shares-25-to-50-percent`).
- `has_super_secure_pscs` is a **profile** top-level flag (absent from the PSC
  list resource top level).

**Assumptions needing live verification**

- **"Completed verification" = `identity_verified_on`** (decided). `*_id_
  verification_due` treats verification as complete only when `identity_verified_
  on` is set. The distinct "a statement was filed" signal
  (`appointment_verification_statement_date`) is now captured as its OWN
  attribute — `n_officers_id_statement_filed` / `n_psc_id_statement_filed` — and
  deliberately does NOT clear the `due` count. Confirmed live on 07083592 (PSC:
  statement filed, `identity_verified_on` absent → statement_filed=1 AND due=1).
  No rule keys off any of these counts.
- **id_verified counts block presence, not a verified identity.** Per the task's
  definition; it measures "inside the IDV regime", not "identity confirmed".
- Counts run over ALL list items (active + resigned/ceased), mirroring the
  officer/PSC item counts; verification obligations really attach to live
  appointments, so revisit if a per-appointment-state split is wanted.
- **PSC-statements 200-response shape remains live-unverified.** Every
  psc-statements call in the 2026-08 batch was either a 404 (E&W no-statement
  companies) or an SLP `statement_only` 200 whose items we read; the full shape
  of a rich 200 statements response (multiple item fields, ceased statements) has
  not been seen live. `active_psc_statement_codes` assumes `items[].statement`
  and `items[].ceased_on`.

## Live batch verification (2026-08-03)

Ran `ukcompany run --input data/company_test_data.csv` against the live API.
Grew the batch to **15 companies** over three runs (all resolved, 0 not-found):
the 10-company baseline, then NI017846 (liquidation), then 07133426 / 14659348
(insolvency-linked) and SL027366 / SL027747 (PSC statements). The first two
sub-sections below describe the 11-company state; "Extended batch" covers the
final 15. Final flags: 26 (8 high, 16 medium, 2 info).

**Batch composition.** **1 in liquidation** (NI017846, PLANNED MEDIA
COMMUNICATIONS LIMITED), **2 dissolved** (NI016906, NI050592, excluded), **8
active**. Flags: 4× high (3 `STATUS_STRIKEOFF` + 1 `STATUS_INSOLVENT`), 10×
medium (overdue accounts/CS), 2× info (`CHARGES_OUTSTANDING`, `YOUNG_COMPANY`).
No `PSC_UNRESOLVED` (see Q3).

**Key finding — a `liquidation` company with no insolvency link.** NI017846 is
`company_status=liquidation` and correctly fired `STATUS_INSOLVENT` (high) from
status alone — but it has **`links.insolvency=None` and `has_insolvency_history`
/ `has_been_liquidated` both `False`**. So:

- The insolvency **resource was still not fetched** (fetch is gated on
  `links.insolvency`). Even a genuine liquidation company — at least this NI one
  — does not necessarily expose the resource, so picking "a liquidation company"
  is **not** sufficient to exercise the insolvency shape. Q2's shape evidence
  therefore still rests on the targeted Carillion fetch below.
- `INSOLVENCY_ADVERSE` **did not fire**: its "indicated but uncached" fallback
  keys off `has_insolvency_link OR has_insolvency_history OR has_been_liquidated`,
  all absent here. This is a real coverage gap — for such a company the only
  insolvency signal is `company_status`, and case-type classification (adverse vs
  solvent MVL) is impossible without the resource. `_status_insolvent` treats it
  as adverse-by-default (fires unless cached cases prove solvent), which is the
  correct conservative outcome, but the adverse/solvent distinction is
  unavailable. Consider having `_insolvency_adverse` also treat a bare
  `company_status` in `INSOLVENT_STATUSES` as "indicated, unclassified".
- Its accounts/CS deadlines are extreme (`accounts next_due=1991-07-30`,
  `CS next_due=2017-01-12`) — a long-dormant NI liquidation; overdue flags fire
  as expected, and `has_charges=True` → `CHARGES_OUTSTANDING` (info).

### Extended batch — 15 companies (both uncovered paths now exercised)

Added companies to close the two live-coverage gaps above.

**Insolvency resource — now covered live.** 07133426 and 14659348 (both
`liquidation`, both with `links.insolvency=True` / `has_insolvency_history=
True`) fetched the insolvency resource and fired **both** `STATUS_INSOLVENT`
**and** `INSOLVENCY_ADVERSE` (high) with real case-level evidence (`1 case(s),
adverse types: compulsory-liquidation`). This is the first live exercise of
`derive_insolvency` + `INSOLVENCY_ADVERSE` end to end, and it confirms the
Carillion shape finding on ordinary E&W companies. NB the distinction from
NI017846: liquidation status fires `STATUS_INSOLVENT` regardless, but only a
present `links.insolvency` yields the case-classification (`INSOLVENCY_ADVERSE`).

**PSC statements — now covered live, and a real gap found.** Finding a company
with an active PSC statement took a scan: **very recent incorporations (2025-26)
had none** — post-ECCTA, PSC is confirmed at formation, so
`steps-to-find-psc-not-yet-completed` is now rare there. The active statements
that exist in volume are on **Scottish Limited Partnerships (SL prefix)** and use
the **`-partnership` variants**:

- SL027366 (NAUTIS ENTERPRISE LP) → `psc-exists-but-not-identified-partnership`
- SL027747 (MASTERTON IMPEX LP) → `steps-to-find-psc-not-yet-completed-partnership`

Both derive correctly to `psc_information_state=statement_only` with the verbatim
code preserved. **But neither fired `PSC_UNRESOLVED`** — the rule's trigger set is
only the three non-`-partnership` forms. This is a substantive coverage gap:
Scottish Limited Partnerships are historically the highest-risk vehicle for
concealed ownership, and the `-partnership` statements encode *exactly* the same
unresolved-beneficial-owner condition. `psc_descriptions.yml` carries all six
constants:

```
steps-to-find-psc-not-yet-completed[-partnership]
psc-exists-but-not-identified[-partnership]
psc-details-not-confirmed[-partnership]
```

**Resolved.** The three `-partnership` variants were added verbatim to
`PSC_UNRESOLVED_STATEMENT_CODES` (kept as distinct constants; the register keeps
the two forms distinct). This completes the existing rule rather than adding a
new one. On re-run, SL027366 and SL027747 now fire `PSC_UNRESOLVED` (low) —
`active PSC statement(s): psc-exists-but-not-identified-partnership` /
`…steps-to-find-psc-not-yet-completed-partnership`. Final batch flags: **28**
(8 high, 16 medium, 2 info + 2 low PSC). Rule doc regenerated; test added
(`test_partnership_variant_fires_rule`).

**Bonus finding.** Both SL partnerships also fired `ADDR_DISPUTE`
(`undeliverable_registered_office_address`) — the classic SLP shell-address
pattern, corroborating the PSC-opacity signal. Good sign the address flags carry
weight for this category.

### Q1 — Are the deprecated booleans still returned/populated?

**Yes — the fallback paths remain load-bearing.**

- `has_charges` and `has_insolvency_history`: returned on **all 10** profiles
  (real booleans, all `False` this batch).
- `has_been_liquidated`: **inconsistently present** — returned (`False`) on 3
  companies (07083592 + both dissolved), **absent** on the other 6 actives. So
  code must keep treating its absence as unknown, not `False`.
- `accounts.overdue` (deprecated): still returned **and populated**, and matched
  `accounts.next_accounts.overdue` **exactly** in every case. The deprecated
  `accounts.next_due` / `accounts.next_made_up_to` are also still present.
- Verdict: the `_first_not_none(next_accounts…, accounts…)` fallbacks and the
  deprecated-boolean fallbacks in `rules.py` are still exercised by live data and
  should **not** be removed. New and deprecated fields currently agree.

### Q2 — Does the insolvency resource match the fixture?

The batch had no insolvency resource, so this was verified with a **targeted
live fetch of CARILLION PLC (03782379, status `liquidation`)**:

- `links.insolvency` present; `/insolvency` returns HTTP 200.
- Live shape: top-level `cases` (+ `etag`, `status`); each case has
  `type`, `dates`, `number`, `practitioners`. `dates` is a list of
  `{"type": …, "date": …}` objects (e.g. `petitioned-on`, `wound-up-on`).
- **Matches `tests/fixtures/insolvency_07654321.json`** on the two shapes the
  logic depends on: `cases[].type` (hyphenated enum, e.g.
  `compulsory-liquidation`) and `cases[].dates[]` as `{type, date}`. `derive_
  insolvency` reads only `cases[].type`, so it is robust to the extra live keys;
  the MVL/solvent-by-type classification is valid against live data.
- The fixture omits the live `number` / `practitioners` case keys and the
  top-level `etag`/`status` — harmless (nothing reads them), but the fixture
  could add them for realism.
- **Coverage caveat:** as NI017846 showed, `company_status=liquidation` does not
  imply `links.insolvency` exists. To get the insolvency *resource* into a batch
  run, the test set needs a company that actually carries the link (Carillion
  03782379 does) — not merely one in a liquidation status.

### Q3 — Live fields `derive.py` drops that are worth keeping

**Correctness risks found (beyond "nice to keep"):**

- **PSC ceased detection.** Live PSC list items mark ceased via a **`ceased`
  boolean** (the active item had `ceased=False`, `ceased_on=None`) and the list
  carries authoritative top-level `active_count` / `ceased_count`. `derive_psc`
  currently counts `psc_n_ceased` by **`ceased_on` presence only**. No ceased PSC
  appeared in the batch to confirm whether a ceased list item also carries
  `ceased_on` (a date) or *only* `ceased: true`; if the latter, `psc_n_ceased`
  and the active-record count undercount. **Recommend** honouring the `ceased`
  boolean and/or sourcing counts from top-level `active_count`/`ceased_count`,
  then verifying on a company with a ceased PSC. (Extends the Phase-1.1b
  "active vs resigned/ceased" open item.)
- **PSC statements never exercised.** `psc_statements` returned **404 for all
  10** companies. So `active_psc_statement_codes`, the `statement_only`/`identified`
  branches of `psc_information_state`, and the `PSC_UNRESOLVED` rule got **no
  live coverage**, and the statements resource shape is still unverified against
  live data. Need a company with an active PSC statement in the test set.

**Fields present live but dropped — worth capturing:**

- **`identity_verification_details`** on **both officers and PSC items** — ECCTA
  identity verification is now **live** in responses (`appointment_verification_
  statement_due_on` / `…_date`). This is exactly the mid-rollout signal the
  Tier-2 officer/PSC notes anticipated; present on the active officer, absent on
  resigned ones. **Strong keep** — future rule material (e.g. verification
  overdue).
- **`has_super_secure_pscs`** (profile) — protected PSCs are legally withheld;
  interacts with `psc_information_state` (a company can legitimately have no
  visible PSC record because of this). Keep to avoid misreading as `none_reported`.
- **Top-level counts** — PSC `active_count`/`ceased_count`, officers
  `active_count`/`resigned_count`/`inactive_count`: authoritative, cheaper than
  deriving, and a cross-check on the pagination merge.
- **`natures_of_control`** (PSC item) — kind/level of control
  (`ownership-of-shares-75-to-100-percent`, etc.); useful attribute, currently
  dropped.
- Minor: `last_full_members_list_date` (profile).
- **Correctly dropped (GDPR — keep dropping):** officer/PSC `address`,
  `date_of_birth`, `name`, `person_number`. The plan's "never ship officer PII"
  rule is being honoured.

**Data quirk.** The two dissolved NI companies carry a legacy top-level
`status: "active"` **alongside** `company_status: "dissolved"`. `derive_profile`
correctly keys off `company_status`; the bare top-level `status` is stale and
must never be used.

## Phase 1.1a — officers endpoint (pagination + churn attributes)

**What was implemented**

- `fetch.py`: added the `officers` endpoint (`/company/{number}/officers`) with
  a dedicated `_fetch_officers` that pages on `start_index` (items_per_page
  capped at 100) until every officer is collected, then writes **one** merged
  cache envelope per company (endpoint `officers`) with the full list under
  `data["items"]` and `data["total_results"]` preserved. `start_index` advances
  by the number of items collected so far, so a short final page cannot leave a
  gap, and an empty page stops the loop even if `total_results` is overstated.
  Officers are now fetched for every found company in `fetch_companies`; 404s are
  cached like other endpoints; a fresh cache short-circuits with no network.
- `derive.py`: added `derive_officers(cached)` producing `n_officers_total`,
  `n_officers_active`, `n_officers_resigned`, `n_appointments_last_24m`,
  `n_resignations_last_24m`, `officer_churn_24m`. The 24-month windows are
  measured against the response's `fetched_at` (as `age_months` is), never
  `datetime.now`, so a re-derive months later reproduces the original values.
  Wired into `derive_all` via a new `officers_by_number` join.
- `cli.py`: `cmd_run` reads the cached officers resource per number and passes it
  to `derive_all`.
- All six attributes registered in `FIELD_DOCS` at **tier 2** (filed-but-
  constrained: officer identities historically unverified, ECCTA identity
  verification mid-rollout 2025-2026); `docs/data-dictionary.md` regenerated.
- No rules added or changed (`rules.py` untouched) — attributes only, per task.
- Tests (`tests/test_officers.py`, all synthetic, invented names only): drive the
  real pagination loop through a fake client with a 123-officer company split
  100 + 23 (exercises the partial final page), assert the merge is complete with
  no duplication/gap, churn counted against a fixed `fetched_at`, missing
  `appointed_on` tolerated, empty list tolerated, 404 cached, and the loop stops
  on an overstated `total_results`.

**Assumptions needing live verification**

- **Response shape.** Assumed the officers list response carries `items` (list),
  `total_results` (int), `items_per_page`, and `start_index` at the top level,
  and that each item may carry `appointed_on` / `resigned_on` as ISO `YYYY-MM-DD`
  strings. Older/agent-filed records are assumed to omit these dates — tolerated,
  never required.
- **Pagination contract.** Assumed `items_per_page` is honoured up to 100 and
  that requesting `start_index` beyond the end returns an empty `items` list
  rather than an error. The empty-page break guards against `total_results`
  being larger than the number of items the API actually serves.
- **Active vs resigned.** Treated absence of `resigned_on` as "active". If the
  live API instead signals resignation only via a status/role field on some
  records, `n_officers_active` / `n_officers_resigned` would need revisiting.
- **`total_results` semantics.** Assumed it counts total appointments (active +
  resigned), matching `len(items)` after a complete merge — not distinct persons.

## Phase 1.1b — PSC list + statements as separate fields

**What was implemented**

- `fetch.py`: generalised the officers pagination into `_fetch_paginated`
  (`_fetch_officers` is now a thin wrapper over it) and added two endpoints,
  `psc` and `psc_statements`, cached separately under the existing envelope.
  Both are fetched for every found company; a 404 is cached as a legitimate
  "none filed", never an error.
- `derive.py`: `derive_psc(psc, statements)` producing five SEPARATE fields (not
  one enum): `psc_fetch_status` (ok/not_found/not_fetched — pipeline state,
  documented as never a company signal), `psc_n_records`, `psc_n_ceased`,
  `active_psc_statement_codes` (comma-joined **verbatim** `statement` values with
  no `ceased_on`), and derived `psc_information_state`
  (identified/statement_only/none_reported/unknown). Joined into `derive_all` via
  `psc_by_number` / `psc_statements_by_number`. All five registered in
  `FIELD_DOCS`.
- `rules.py`: one new rule, `PSC_UNRESOLVED` (severity **low**, tier 1), firing
  when `active_psc_statement_codes` contains any of
  `steps-to-find-psc-not-yet-completed`, `psc-exists-but-not-identified` or
  `psc-details-not-confirmed`. The three constants were verified verbatim against
  `companieshouse/api-enumerations/psc_descriptions.yml` (checked 2026-08); they
  are correctly spelled upstream. No existing rule touched. `docs/rules.md` and
  `docs/data-dictionary.md` regenerated.
- Tests (`tests/test_psc.py`, synthetic): identified PSC, statement-only firing
  the rule, 404-on-both, not-fetched → unknown, ceased statement ignored, a
  verbatim-preservation test (a deliberately misspelled constant survives derive
  byte-for-byte), and an assertion that `psc_fetch_status` never appears in any
  flag evidence.

**Deviation from the prompt's stated exit diff.** The prompt listed the allowed
diff as fetch.py, derive.py, rules.py, tests/ and generated docs — it omitted
`cli.py`. `cmd_run` had to be extended (3 lines) to read the two cached PSC
resources and pass them to `derive_all`; without it the fetched PSC data would
never reach `companies.csv` and the feature would be inert. One existing test
(`test_registry_metadata_complete`) was updated to admit `low` as a valid
severity (a new severity level, not a change to any existing rule).

**Assumptions needing live verification**

- **Response shapes.** Assumed the PSC list carries `items[]` with `ceased_on`
  (presence ⇒ ceased) and the statements resource carries `items[].statement`
  (the enum constant) plus optional `ceased_on`. `.get()` throughout.
- **404 meaning.** Treated a 404 on the PSC list as "none filed" (→
  `psc_n_records = 0`, state `none_reported` when statements also empty), distinct
  from a resource we never fetched (`not_fetched` → counts `None`, state
  `unknown`). Needs confirmation that CH really 404s (rather than 200 with an
  empty list) for companies with no PSC record.
- **Statement constant set.** Only the three trigger constants were verified
  against the live enumerations file. The wider material set named in the plan
  (no-response-to-notice, failure-to-confirm-changed-details, restrictions
  notices, etc.) is not yet matched by any rule and should be re-checked verbatim
  before rules key off them — some official constants are misspelled upstream and
  must not be normalised.
- **`psc-details-not-confirmed`.** Assumed this is the active-statement form used
  for an unconfirmed PSC. If the live data instead uses a variant spelling for
  the individual-vs-entity or partnership cases, the trigger tuple needs the
  extra literals added (verbatim).
## Insolvency Service agreement-validation harness

`ukcompany validate --labels <csv> [--control <csv>] [--out <path>]` loads the
Insolvency Service record-level publication, removes bulk cases and
Administration-to-CVL duplicates as directed by its README, normalises company
numbers, and evaluates the existing derive-and-score pipeline solely from the
existing raw cache. It has no fetch path and does not alter rules, severities,
or company attributes. Reports default under gitignored `data/` because they
contain company numbers.

The headline recall is deliberately conditional recall among companies still
assessable in the current Companies House data:
`flagged_adverse / (flagged_adverse + missed_genuine)`. Cached 404/purged
companies and positives whose current status has moved back to normal are
timing/data-availability facts rather than demonstrated pipeline misses, so
they are excluded, as are records never fetched. Every excluded bucket is
reported beside the measure so this conditional denominator cannot be mistaken
for unconditional historical recall. The publication is statistical data, not
ground truth about an individual company's insolvency, and the harness reports
agreement between datasets on adverse cases only; solvent winding-ups are not
present in the labels.

**Bulk encoding and malformed-number correction (2026-08 inspection).** The
237,392-row CSV contains `is_bulk` values `Y` (5,740 rows), `NA` (51), and blank
(the large majority), with no `N` values. Label loading therefore excludes only
an explicit `Y`; the earlier allow-`N` filter would have dropped every positive
and produced meaningless recall without raising an error. Separately, 599 of
237,392 company numbers are malformed (including legacy suffix forms, trailing
letters, embedded spaces, and O/0 transcription errors). They are quarantined
verbatim in the reported unusable bucket. The loader does not strip suffixes or
guess character substitutions, because a speculative repair could join to the
wrong company.

## Phase 2 — Free Company Data Product snapshot infrastructure

Added `ukcompany.snapshot` as general, validation-independent infrastructure.
It discovers the current `BasicCompanyData-YYYY-MM-01-partN_M.zip` set from the
Companies House landing page, rejects missing or inconsistent part sets,
downloads archives atomically into a dated cache, and records source URLs,
download time, sizes, SHA-256 hashes, and total rows in a JSON manifest. The CLI
exposes `ukcompany snapshot fetch` and `ukcompany snapshot info`; no live bulk
download was run during implementation, so the live August 2026 part count
remains to be recorded by the operator's first fetch.

ZIP contents are extracted on demand to a cached path and scanned full-width as
a Polars `LazyFrame`; the loader itself never collects the population. Source
column names remain verbatim. `CompanyNumber` is explicitly forced to Polars
string type so leading-zero English/Welsh identifiers and prefixed identifiers
survive unchanged. Polars is a `snapshot` optional extra and is imported only
inside snapshot operations, so the core install and pipeline do not depend on
it. The source is Companies House's Free Company Data Product, licensed under
the Open Government Licence; the landing-page URL is retained in every manifest
for attribution and provenance.

## Stratified snapshot control for the validation harness (F-v2b)

Added `ukcompany.validation.control` and wired it into `validate`. The control is
now DRAWN from the cached snapshot rather than supplied ad hoc, so it mirrors the
insolvent set's structural distribution instead of being a raw random draw.

**Stratification design.** A raw random control measures how often flags fire in
the population; a stratified control measures whether flags still separate
companies that are structurally *similar* to the insolvent set — removing the
confound that insolvent companies skew young/particular-sector while a random
control skews old/other-sector (a flag could then "separate" by proxying sector
or age rather than distress). Positives are distributed over (SIC section ×
coarse age band); the control is drawn to mirror that distribution.

**Pre-distress-confounders-only rule (the crux).** Stratification touches ONLY
pre-distress structural confounders: SIC section (SIC-2007 section letter) and a
coarse age band (`<2y / 2-5y / 5-10y / 10y+ / UNKNOWN`). Nothing downstream of
distress — `company_status`, accounts, insolvency, charges — is ever a
stratification or matching dimension; matching on a distress variable would
silently neuter the test. `CompanyStatus` is used in one place only, as an
ELIGIBILITY filter defining the sampling frame (only `active` companies; a
control of already-dissolved companies is not a control). That is a frame
definition, not a stratum. Age is reported as a covariate (flag-rate broken down
by age band) and only coarsely banded, never tightly matched.

**One SIC mapping, both sides.** `sic_section_from_code` (in `labels.py`) is a
fixed published SIC-2007 division→section lookup (e.g. 41–43→F construction,
47→G retail, 62→J information & communication — NOT C). The label side derives
each positive's section from the raw `sic07_1_digit` code; the snapshot side
(`snapshot_sic_section`) parses the leading numeric out of the
`"62012 - label"` SIC text and routes it through the SAME helper, so both
cohorts are sectioned identically. The `draw_control` Polars path builds its
division→section lookup from the same helper.

**Determinism.** The draw is deterministic given `--seed`: per stratum, rows are
ordered by a seeded hash of the company number and the top-k taken, k =
round(proportion × n). Same seed + same snapshot ⇒ same control. Under-filled
strata (fewer eligible companies than target) are visible in the achieved-vs-
target table.

**Age reference.** Age bands are computed against the snapshot month (the first
of that month), applied identically to positives and to the snapshot frame —
never "now". Day thresholds (730 / 1826 / 3653) are shared by the Python label
side and the Polars snapshot side so both band identically. NEEDS LIVE
VERIFICATION: the real Insolvency Service `month_registered` encoding — the
parser accepts `YYYY-MM`, `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/YYYY` and bands
anything else UNKNOWN; confirm the publication's actual format so positives are
not silently all-UNKNOWN. Likewise `sic07_1_digit` is assumed to carry a usable
1-or-2-digit division code; if the real column is a single digit, section
resolution on the label side is coarser than the snapshot side.

**Real-snapshot column quirk.** The real CH bulk header has leading spaces on
several names (e.g. `" CompanyNumber"`), unlike the clean fixtures, and the
loader's dtype override (keyed on the un-spaced name) then misses. `draw_control`
strips surrounding whitespace from column names lazily (schema only) and casts
the company-number column to string, so leading-zero and prefixed identifiers
survive. Verified against the operator's cached `data/snapshot/2026-08`.

**Two-step, cache-only flow (load-bearing).** The harness is cache-only and MUST
NOT fetch. `draw_control` produces NUMBERS only; the CLI writes them to a CSV
(`--control-out`, default `data/control-numbers.csv`) with a `.strata.json`
sidecar (target/achieved counts, frame description, snapshot month) and prints
the two-step instruction. The operator fetches the control profiles
(`ukcompany run --input data/control-numbers.csv`) and re-runs
`validate --control data/control-numbers.csv`. The strata columns and sidecar let
the re-run report the target-vs-achieved distribution and the by-age-band
flag-rate without re-touching the snapshot. `--control-from-snapshot` and the
existing `--control <csv>` are mutually exclusive; `--control <csv>` still
accepts a plain single-column list (section unknown / band UNKNOWN).

**PU / "assumed negative" framing.** No negative labels exist — the publication
lists only adverse cases. The control is therefore a positive-unlabelled,
*assumed-not-labelled-negative* cohort, not a confirmed non-distressed set. The
report states this in the body: the control figure is a flag-RATE conditional on
the sampling frame, NOT precision, and must not be read as a false-positive rate
against ground truth.

**Scope.** Diff limited to `src/ukcompany/validation/` (labels.py, control.py
new, evaluate.py, report.py), `cli.py`, `tests/test_control.py`, and this file.
`control.py` is evaluation code and registers nothing in FIELD_DOCS; no rules,
severities, or scoring changed, so `docs/rules.md` and `docs/data-dictionary.md`
did not need regeneration.

## Real-file quirk fixes (F-v2c)

Two tightly-scoped fixes for real-file quirks, done before any real validation
run because both are silent-failure bugs (no error, wrong data).

**Fix 1 — snapshot loader: leading-space headers defeated the dtype override
(present since F-v2a).** The real CH bulk file has leading whitespace on several
header names; the company-number column is literally `" CompanyNumber"`. The
loader's `schema_overrides={"CompanyNumber": pl.String}` keyed on the un-spaced
name and therefore NEVER MATCHED the real file, so Polars type-INFERRED
CompanyNumber as int and silently stripped leading zeros on every consumer of
`scan()` since F-v2a. Fixed in `snapshot/loader.py`: `scan()` now peeks at the
header row, applies the string override on the RAW (possibly space-prefixed)
name so it actually fires, then strips whitespace from all column names so
downstream sees `CompanyNumber` and the COLUMNS mapping resolves. Verified
against the operator's cached `data/snapshot/2026-08`: `columns()` now returns
`CompanyNumber` (no leading space), and `00944342` round-trips string-typed with
its leading zero intact. The synthetic snapshot fixtures were updated to use
leading-space headers (`" CompanyNumber"`, etc.) mirroring the real file, so the
existing dtype/leading-zero test now exercises the whitespace path. The local
strip+cast workaround added to `control.py` in F-v2b was removed - the loader now
guarantees clean names and a string CompanyNumber for all consumers.

**Fix 2 — labels: field-shifted-row quarantine.** An unescaped comma in a text
field (e.g. company_name) would shift every later column one place right; the
tell is a non-date value (a case_type or register location) landing in
month_registered, giving that row a WRONG case_type and SIC. `labels.py` now
quarantines such rows: after bulk / Administration-to-CVL / number-normalisation
handling, when the publication carries month_registered, a value that is not a
bare `^\d{4}-\d{2}$` month routes the row to a new `unusable_shifted` bucket
(count + a small sample of offending values) and it never becomes a label. Rows
are quarantined, never repaired (repair = guessing where the comma was = silent
mis-banding). The count is surfaced in the report's label-loading line. The gate
only fires when the month_registered column is present, so older/other
publications lacking it are unaffected.

**Empirical finding on the current download (NEEDS-NOTING, not a defect).** The
premise was ~365/237k field-shifted rows. Loading the actual downloaded file
(`record-level-data.csv`, header:
`company_number, company_name, register_location, case_type, month_registered,
sic07_1_digit..sic07_5_digit, is_bulk`; 237,391 rows) found
`unusable_shifted == 0`: every row is exactly 11 columns (0 extra, 0 short) and
month_registered is 100% well-formed `YYYY-MM`. This file properly quotes its
internal commas, so `csv.DictReader` absorbs them and no shift occurs. The
quarantine gate is therefore correct and defensive but catches nothing in this
version; the ~365 figure does not reproduce here. Retained regardless, since a
future/alternate export could be unquoted. Also confirmed on this file: retained
labels 220,461; dropped_bulk 5,740; Administration-to-CVL 7,102; unusable numbers
736; duplicates 3,352; and the UNKNOWN age band is 0 of 220,461 (month_registered
parses cleanly for every retained label, and sic07_1_digit sections without
falling to unknown at a meaningful rate) - so the still-open sic07_1_digit
encoding question does NOT bite on this file.

**Scope.** Diff limited to `snapshot/loader.py`, `validation/labels.py`,
`validation/control.py` (workaround removal only), `validation/report.py` (one
line), the snapshot fixtures, `tests/`, and this file. No scoring, rules,
severities, FIELD_DOCS, or stratification logic changed.

## Positives sampling — the missing symmetric step (F-v2d)

The harness could sample a stratified control but had no equivalent for
POSITIVES, so every run's recall side was null (all 220k labels "not fetched").
Added `validation/sample.py` and wired `ukcompany validate
--write-positives-sample <path>` to close the asymmetry.

**Recent-adverse rationale.** The label file has ~220k usable positives spanning
2012-2024. Fetching all is infeasible (220k API calls) and pointless — old
positives are mostly dissolved-and-purged (404) or recovered, so they land in the
excluded/not-assessable buckets, never in recall. The meaningful recall test is a
few hundred RECENT adverse positives the API can still assess, plus the control.
`sample_positives` draws eligible = adverse `case_type` (kept:
compulsory_liquidation, creditors_voluntary_liquidation, administration,
corporate_voluntary_arrangement; `other`/non-adverse guarded out) AND a usable
`month_registered` >= `--positives-since` (default 2023-01; positives lacking a
usable month are excluded). Up to `--positives-n` (default 500) are taken; if
more eligible than N, a seeded random sample (`--seed`, default 1) — deterministic
and reproducible; if fewer, all are taken and the shortfall is reported.

**Sampling method (documented choice).** A simple seeded random sample, NOT
case_type-stratified — deliberately not over-built for v1. The command prints the
composition (count per case_type, count per year) so the operator sees the spread
before fetching. Verified on the real file: `--positives-n 500 --positives-since
2023-01 --seed 1` → 500 of 34,505 eligible, spread creditors_voluntary_liquidation
402 / compulsory_liquidation 66 / administration 30 / corporate_voluntary_
arrangement 2, years 2023=373 / 2024=127 (all >= the since-date, confirming the
recency filter).

**Cache-only preserved.** Like the control, this WRITES NUMBERS only — a
`company_number` CSV consumable by `ukcompany run --input` (asserted in tests) —
and then EXITS before the meaningless unfetched evaluation. No fetch path added.
`--write-positives-sample` is symmetric to `--control-from-snapshot` and usable in
the same invocation: when both are given, the control is drawn and the positives
sampled in one call, then it exits. `--positives-since`/`month_registered` here is
the insolvency-registration month from the publication (recency of the adverse
event), the same retained field the control stratification uses.

**Full operator flow now that both sides can be sampled.**
```
# 1. draw BOTH samples (numbers only, no fetch)
ukcompany validate --labels record-level-data.csv \
    --control-from-snapshot --control-n 500 --seed 1 \
    --write-positives-sample data/positives-sample.csv \
    --positives-n 500 --positives-since 2023-01
# 2. fetch both (the only step that hits the API)
ukcompany run --input data/positives-sample.csv
ukcompany run --input data/control-numbers.csv
# 3. the real evaluation, over a real recall denominator
ukcompany validate --labels record-level-data.csv --control data/control-numbers.csv
```

**Scope.** Diff limited to `validation/sample.py` (new), `validation/__init__.py`
(exports), `cli.py` (args + sampling branch), `tests/test_positives_sample.py`,
one line in `tests/test_insolvency_validation.py` (aligned with the maintainer's
switch of the label SIC source to `sic07_2_digit`), and this file. No scoring,
rules, severities, FIELD_DOCS, stratification, or the existing recall/control
evaluation changed.

## Documentation and Quarto baseline (2026-08-07)

Added `docs/TASKS.md` as the durable task and decision register, including the
outstanding real validation run, specified Gazette work, parked feature
classes, rejected sources, and known methodological limits. Added a minimal
Quarto website skeleton under `docs/site/` covering methodology, validation,
and limitations without publishing or fabricating results. Refreshed README
features, status, and CLI examples to reflect the existing validation harness,
snapshot loader, officer/PSC coverage, and ECCTA fields.

Regenerated `docs/rules.md` with `ukcompany rules-doc` and
`docs/data-dictionary.md` with `ukcompany data-dict`; both matched their checked-
in versions exactly. No rules, severities, `FIELD_DOCS`, scoring, or pipeline
logic changed. CI publishing for the Quarto site remains a ready-to-build task.
Verification: `pytest` passed 96 tests with the configured live test deselected;
`ruff check .` passed; and `quarto render docs/site` produced the site successfully.

## Validation reconciliation fix and disposition reframe (2026-08-07)

The first representative run exposed two correctness defects. Validation called
`score_company()` directly and therefore bypassed `score_all()`'s dissolved/closed exclusion
gate; it also evaluated every labelled number present in the shared cache rather than the
explicitly sampled cohort. The 500-company sample consequently credited 297 excluded
companies as adverse hits, called one excluded company a genuine miss, and admitted one older
cached positive, producing an invalid 500/501 headline.

Validation now classifies `excluded_status` before examining rule IDs and requires
`--positives <csv>` in evaluation mode. Numbers absent from retained labels or invalid in the
positive file fail clearly. The report leads with the full current-pipeline disposition
(excluded, flagged, missed, unavailable) and treats conditional recall among screenable
companies as secondary. It also states that label/register agreement on an already-filed
insolvency event is expected and is not predictive validation. No scoring rule, severity,
`FIELD_DOCS`, fetch, derive, or production scoring behaviour changed.
Verification passed with 97 non-live tests (one live test deselected), `ruff check .`, and
`git diff --check`. The corrected real 500-company report reconciles to 298 excluded, 202
flagged adverse, zero genuine misses, and zero unavailable/not-fetched positives; conditional
recall on the 202 screenable companies is 100%, with the same-event caveat above.

## PSC bulk snapshot recon (2026-09-18)

Executed docs/recon-psc.md over ALL 32 parts of the PSC snapshot. New files:
`scripts/recon_psc.py`, `docs/recon-psc.md` (brief + measured Results), generated
`docs/recon-psc-results.json` and `docs/recon-psc-results.md`. No package, rules,
severities, FIELD_DOCS, or test changes.

**Snapshot substitution (NEEDS-NOTING).** The brief's prior evidence used snapshot
2026-09-11, which Companies House no longer serves (only the current day's snapshot is
published). All 32 parts of 2026-09-18 were downloaded (~13 GB extracted, in
`~/Downloads/psc-snapshot-2026-09-18/`); the staged single 09-11 part was left untouched
and unused. The script refuses to run over mixed snapshot dates or an incomplete part set.

**Headline findings.** 15,952,486 records, 0 bad lines, 404 s. Statement records DO exist
in the product (922,564; parts 31–32 only; part 32 holds no PSC records at all, just
statements + 108 exemptions + one `totals#` trailer) — the prior "no statements" finding
was an artifact of probing part 2. Ceased records retained (16.6%, effectively all
2016–2026), so point-in-time reconstruction is feasible from regime start. Product spans
10,917,257 companies (~2× the live register) — it retains non-live companies. Person-key
connectivity overall is 28.8% of keys on ≥2 records (vs 3.7% measured within one part).
Partitioning: positional slices of a non-random internal ordering; per-part rates unusable.

**Documented choices (recorded in the JSON `normalisation` block).** UK country value set;
postcode raw vs normalised regexes; registration-number resolution = strip/upper direct
lookup plus zero-pad-to-8 for digit-only values; "active" = no `ceased_on` and `ceased`
flag not true; crosstab "ceased" = `ceased_on` presence; person key =
(forename, surname, DOB year, DOB month) hashed blake2b-64 in memory only, never persisted.
Join base is BasicCompanyData 2026-08-01 vs PSC 2026-09-18 (~7-week skew) and excludes
dissolved companies — both depress the reported join rates; treat 54.2%/77.9% as lower
bounds for a same-date join.

**Privacy check.** Generated md greps clean for forename/surname/address_line/
date_of_birth. In the JSON the only hits are required key-NAME presence counters in
`data_keys` and one methodology string; no personal values in any output.

**Verification.** `ruff check` clean; full `pytest` 136 passed, 1 live deselected. Ran
concurrently with the accounts Stage 1 production extraction (separate task; writes only
under `data/accounts/`).

## Accounts pipeline consolidation — memory-bounded downstream, disposable store, URL fix (2026-09-21)

Executed the build prompt's six decisions against the real 30-archive corpus (469,072,180
observations, 221 GB scratch store, since verified and left for human go/no-go on
deletion). Diffs: `extract.py`, `backfill.py`, `pivot.py`, `qa.py`, `inventory.py`,
`cli.py`, plus new tests. No rules, severities, or scoring changed.

**Immediate actions.** Stopped the in-flight full-store `PRAGMA integrity_check` (would
have scanned 221 GB of scratch bytes that are not the deliverable). Added
`extract.verify_monthly_parquet`/`verify_all_monthly_parquets` and a new `ukcompany-accounts
verify` command comparing each manifest's `observation_count` against the actual archived
Parquet row count — the real completeness check after the unclean reboot, and the
permanent replacement for a full-store scan going forward (important once Decision 2 makes
the store disposable). Result: **30 of 30 archives verified, all matched.**

**Decision 1 (BLOCKING) — memory-bounded pivot/QA/inventory.** `pivot_parquet`/`write_qa`
previously called `pl.read_parquet`/eager reads over the full corpus; this is what caused
the mid-task reboot (a bare re-run of the naive eager pivot was independently confirmed to
get OOM-killed at ~30 GB RSS, taking VS Code's shared-process and extension host down with
it — same cgroup). Root-caused empirically, not by inference:
- A pure lazy `pl.scan_parquet(glob) + filters + collect(engine="streaming")` plan for
  pivot's mapped-cell reduction still measured >20 GB RSS. Diagnosis: Polars' streaming
  engine did not keep the `join` + `sort/unique(maintain_order=True)` chain bounded across
  a 30-file multi-scan; explicit column projection helped only marginally.
- Fix actually adopted: process one monthly Parquet at a time, reducing each to its small
  mapped-cell/target-concept slice before ever touching the next file (`pivot_long_over_parts`
  in `pivot.py`, `member_histogram_over_parts`/`total_component_reconciliation_over_parts`
  in `qa.py`). For reconciliation specifically, `SOURCE_KEYS` includes `source_archive`, so
  the total-vs-component join is provably file-local — it can never match across files —
  which is what makes a per-file join-then-concat exact, not an approximation.
- All three CLI commands (`pivot`, `qa`, `inventory`) now report peak RSS
  (`pivot.track_peak_rss`, a `resource.getrusage` high-water-mark reader — exact for a
  one-shot CLI process, no sampling needed).
- **Measured on the real 30-archive corpus, each run in an isolated `systemd-run --scope
  -p MemoryMax=` cgroup** (adopted after two more OOM kills during tuning — cgroup memory
  limits cap real resident memory and confine a kill to that scope, unlike `ulimit -v`,
  which was found to produce false failures from Rust/Polars allocator address-space
  reservations unrelated to actual usage):
  - `pivot --mode as_first_reported`: **24.4 GB peak**, wide 8,147,294 rows.
  - `qa`: **15.2 GB peak**.
  - `inventory` (2,592 concepts, up from the 494 validated at slim-table scale): **9.2 GB
    peak**.
  - Only `qa` and `inventory` land under the brief's ~15 GB aspirational target; `pivot`
    exceeds it (24.4 GB) despite the per-file rework, because even the mapped/GBP/
    is_current-filtered cross-month cell set is ~47M rows and Polars' multi-column sort
    over that (three string sort keys) measured ~2.2× its input as a hard floor — tested
    and rejected: categorical-encoding the sort keys (made it worse, +1.5 GB just for the
    cast) and a conflict-set/anti-join split (near-zero true duplication in this corpus, so
    it doesn't shrink the sort's input). All three commands complete safely with real
    headroom under the machine's ~30 GB when run in an isolated cgroup; recommend this as
    the standing invocation pattern for future full-history runs (see below).
  - `inventory`'s per-concept `companies` (distinct-company) count is a **documented lower
    bound at full 2,592-concept scale**: the exact cross-file distinct-company set measured
    338M+ (concept, company) pairs before dedup (bigger than pivot's problem, because
    inventory keeps every concept and every currency, not just 9 WIDE-mapped ones); an
    incremental anti-join to drop already-seen pairs was tested and still trended toward
    ~250-300M rows by extrapolation. Reported value is the max companies-per-concept seen
    in any *single* archive (always ≤ the true value), computed cheaply
    (`group_by(concept).agg(n_unique).max()` per file) and flagged as such in both the
    dataclass (`companies_are_lower_bound`) and the rendered report.
- `inventory.py` gained a fully independent Parquet-based path
  (`build_concept_inventory_from_parts`/`write_concept_inventory_from_parts`) alongside the
  unchanged, still-tested SQLite path (`build_concept_inventory`); `ukcompany-accounts
  inventory` now defaults to `--long` (Parquets) and only uses `--store` when explicitly
  given, since Decision 2 means a store may not exist to query.

**Decision 4 — numeric/non-numeric split and employee GBP anomaly (real findings, not
placeholders).** Corpus-wide: **211,964,906 numeric (45.2%) / 257,107,274 non-numeric
(54.8%)** — the input to the `numeric-only` scope dial; not switched here, per instruction.
Employee-count GBP-unit anomaly: **2,871,233** `AverageNumberEmployeesDuringPeriod` facts
resolved to a GBP unit instead of a plain count — median value **1.0**, only 95 facts at or
above the 100,000 "clearly monetary" threshold. This closely matches the build brief's own
prior estimate ("~a quarter of employee coverage") — 2.87M of ~9.8M total employee records
is ~29%. The pivot does not filter employee facts by currency regardless of this finding
(unchanged, per instruction).

**Decision 2 — disposable per-month scratch store, opt-in.** Added
`extract.process_archive_disposable` (extracts one archive into a throwaway
`.{archive}.scratch.sqlite`, exports its Parquet, copies only the small
`processed_archives` manifest row into the caller's persistent connection, then deletes the
scratch files) and threaded a `disposable_store: bool = False` /
`--disposable-store` flag through `run_backfill` / `ukcompany-accounts run`. Default stays
monolithic (unchanged behaviour, all existing tests pass unmodified) to avoid a breaking
change to the tested contract; disposable mode is the documented recommendation for future
full-history runs. Known, documented trade-off: once a month's scratch store is discarded,
that month cannot be re-exported at a different `scope`/`kinds` without re-extracting from
the ZIP — the existing "skip complete, re-export on scope change" branch does not apply in
this mode, so `cmd_run` prints an explicit note that observation-level extraction-report
stats are not populated (manifest-only) and points at `inventory` (Parquet-based) instead.
Verified with a new test asserting `observations` never accumulates under disposable mode
and that a second run resumes purely from the manifest (mocked `fetch_archive` raises if
called for an already-complete month).

**Decision 3 — download URL, corrected via live probing, not the brief's assumption.** The
Companies House download host actually splits monthly archives across **two** live
locations, confirmed by direct HTTP probing (not previously exercised — all 30 archives
this session were manually staged, never fetched by this code):
`download.companieshouse.gov.uk/Accounts_Monthly_Data-{Month}{Year}.zip` (root) 200s for a
rolling recent window (confirmed 2022-08 through 2026-08, 404s for 2016/2010), while
`.../archive/...` 200s for older months (confirmed 2010, 2016, 2022-01) and 404s for the
newest (2025-08, 2026-07/08). The brief's premise — "root is correct, `/archive/` is wrong"
— does not hold; **both are needed**, and the pre-existing code hardcoded `/archive/` for
every request, meaning it would have silently 404'd on every recent month. Fixed:
`fetch_archive` now tries `base_url` (now defaulting to the root) and falls back to
`historic_base_url` (`/archive/`, still the default fallback) on a 404, so the boundary
between the two live locations — which shifts monthly — never has to be hardcoded or
guessed. All 12 existing tests that pass a local `base_url` were updated to also pass
`historic_base_url=None`, since the prior default would otherwise have made every 404 in a
test fall through to a live network call — caught before it shipped by a genuine test hang
against the real server, not by inspection.

**Decision 5 — verified at full 2,592-concept scale (this session's inventory rewrite).**
Read-correctness audit numbers are corpus-wide via `inventory`: zero non-numeric facts
carrying a `numeric_value`, only 1 concept (`MissingUnit`-style single-archive case; see
`docs/accounts-concept-inventory.md` for the live numbers) with a numeric-unit gap at this
scale — full anomaly tables (mixed kind, incompatible units, mixed context, name/kind
mismatch) regenerated from the real corpus, not the 494-concept sample.

**Decision 6 — restatement metrics, scope reduced from 2022-2023 to a 6-month window
(documented, not silent).** Added `qa.restatement_metrics_over_parts` /
`render_restatement_report` / `ukcompany-accounts restatement`, which requires an explicit
`--scope-label` naming the continuous range used (never let it default to something that
could be mistaken for a full-archive claim). The full 2022-2023 (24-file, ~90M-row target-
concept) span was attempted and measured to exceed 25 GB even after isolating the
restatement key-count group-by into its own function (freed before the two pivot calls);
root cause is the same as the `inventory` companies problem — grouping by a key
(`company, period_end, concept, dimension, member`) whose cardinality approaches the row
count requires a hash table sized close to the full row count, which is not the same
"few-groups" shape as the other per-file reductions in this session. Reduced to a
genuinely-continuous **2022-01 through 2022-06** window, which measured **14.9 GB peak**
end-to-end (key-count pass + both pivot modes). Real result at that scope:
`docs/accounts-restatement-2022-h1.md` — restatement rate **0.04%** overall (0.01%-0.06% by
concept), and a materially larger finding: `latest` WIDE non-null cell counts run
**~1.8-1.9× `as_first_reported`'s** across every mapped column (e.g. Equity 2,567,529 vs
1,394,991) — i.e., choosing `as_first_reported` for predictive publication (as the existing
docs already mandate) roughly halves usable cell coverage relative to `latest`, which the
human should weigh alongside the look-ahead risk `latest` carries. The full 2022-2023
computation remains a flagged follow-up (needs either a bigger machine, an out-of-core
group-by, or a smarter incremental key-elimination algorithm — the anti-join approach
tried for `inventory`'s companies problem does not obviously transfer, since restatement
keys are drawn from a much larger key space to begin with).

**Safety practice adopted mid-session.** After the pivot rewrite's first (still-buggy)
version reproduced the original OOM and took down VS Code's shared-process/extension host
a second time, every further full-corpus experiment in this session ran inside
`systemd-run --user --scope -p MemoryMax=<N>G -p MemorySwapMax=0`, which caps real resident
memory (unlike `ulimit -v`, which measures virtual address space and produced false
failures from allocator reservations) and confines any OOM kill to that one scope rather
than triggering a system-wide sweep. Recommend this as the standing invocation pattern for
`pivot`/`qa`/`inventory`/`restatement` on full-history-scale corpora going forward,
regardless of the peak-memory numbers reported above, until a smaller machine's actual
budget is known.

**Not done / explicitly flagged, not decided.** Per the build prompt's "flag, don't
decide": did NOT switch `accounts.kinds` to `numeric-only` (Decision 4's split is the
input, not the decision). Did NOT fetch any month outside the existing 30-archive sample
(Decision 3's fix makes future fetches correct; no new download range was requested or
run). Did NOT delete the 221 GB scratch store — `verify` confirms the Parquets are safe to
treat as the archive, but deletion is left to the human's explicit go/no-go as instructed.

**Verification.** `ruff check .` clean; full `pytest` 138 passed, 1 live deselected
(including a new disposable-store resumability test and a new restatement-metrics test
with tiny synthetic Parquet fixtures). All full-scale numbers above are from real runs
against the actual 30-archive corpus, not estimates.

## Close the accounts import chapter — retracted figure, real restatement rate, approximate companies, limitations note (2026-09-21)

Small, bounded follow-up per the build prompt of the same name. No extraction, `scope`,
`kinds`, or pivot changes; no full-history run. Diffs: `qa.py`, `inventory.py`, `cli.py`,
tests, plus docs. `ruff check .` clean; full `pytest` 139 passed, 1 live deselected.

**Retraction.** The 0.04% restatement figure from the previous session
(`docs/accounts-restatement-2022-h1.md`, a Jan–Jun 2022 window) is **wrong and deleted, not
merely superseded**: a period and its later comparative are ~12 months apart, so a 6-month
window structurally cannot contain a restatement — it measured a near-empty population,
not restatement behaviour. Do not cite it; the file is removed.

**Real 2022–2023 restatement rate, via a month-ordered running tally, not a group-by.**
The previous group-by approach (grouping by a nearly-row-cardinality key) was confirmed to
exceed 25 GB even isolated in its own function — the same failure shape as `inventory`'s
companies problem. Replaced entirely: `qa.restatement_rate_over_parts` processes the 24
continuous 2022–2023 archives oldest-to-newest, holding only a plain Python dict of
first-seen values keyed `(company, period_end, concept)` (state proportional to distinct
keys, not raw fact-row count). Matches the panel check's definition
(`docs/panel-check.md`): non-dimensional (`dimension IS NULL`), `status == 'selected'`,
numeric, the nine target concepts. Measured **17.8 GB peak** (above the brief's "a few GB"
estimate — Python dict/tuple/string object overhead is heavier than raw data volume; still
comfortably run in an isolated cgroup) — DuckDB fallback was not needed. Real result:
**49,159,979 distinct keys, 13,553,889 repeated, 7.93% disagree** — closely matching the
independent legacy panel check's 7.94%, which validates both pipelines. `Creditors`
repeated-key count (106,740) is far below the panel check's 1,393,444 because the panel
check's legacy pipeline promoted a single non-conflicting *dimensional* value as a total
substitute ("legacy dimensional fallback"); this computation strictly requires
`dimension IS NULL`, matching the task's literal definition and the archive's documented
~4% genuine non-dimensional Creditors rate — noted directly in
`docs/accounts-restatement-2022-2023.md` so the discrepancy isn't read as an error. CLI:
`ukcompany-accounts restatement` no longer touches the pivot machinery at all (dropped the
`as_first_reported`-vs-`latest` WIDE cell-count comparison along with the old
group-by-based function, since it required running the pivot twice and was not asked for
in this task — out of scope per the brief's explicit "does not... rewrite the pivot").

**Inventory `companies`: `approx_n_unique`, not a lower bound.** The prior lower-bound
approach (max companies-per-concept seen in any single archive, from a per-file loop) is
replaced by `pl.approx_n_unique` (HyperLogLog, ~2% typical error, fixed sketch size per
group) folded directly into the existing cheap `group_by("concept")` pass — measured
**2 s / ~2 GB** for the full 2,592-concept corpus, eliminating the whole per-file
`companies_parts` loop this required before. `ConceptInventory.companies_are_approximate`
replaces `companies_are_lower_bound`; the rendered report's caveat updated to match. Full
real re-run: **8.4 GB peak** (down from 9.2 GB under the old approach, and simpler code).

**Limitations note committed.** `docs/accounts-limitations.md` (new) — the chapter's
close-out: what the archive keeps (all-fact, every concept, as-read, verified no coerced
non-numeric values), what's validated (nine core concepts only) vs. captured-but-unvalidated
(~2,580 concepts), the non-numeric text retention rationale (~15.35 GB logical, kept
because most boilerplate compresses well), the coverage-sample caveat (continuous
2022–2023 plus six lone months), and the known downstream-handled quirks (employee
GBP-unit anomaly, 2020→2021 reporting-regime break, Creditors dimensionality, restatement
rate). Also records what was kept/skipped/deferred this chapter, matching the brief's own
framing.

**Verification.** All full-scale numbers above are from real runs against the actual
30-archive corpus, each in an isolated `systemd-run --scope -p MemoryMax=` cgroup per the
practice adopted in the previous session. `ruff check .` clean; `pytest` 139 passed
(3 new/changed tests: inventory's parts-based approx-companies test, the restatement
running-tally test replacing the old group-by test).

**Flag, don't decide (unchanged).** numeric-only vs all-fact, fetch range, and the 221 GB
store deletion remain human/later calls; none were touched.

## Full-history accounts backfill (2026-09-23)

Executed the "full-history accounts backfill" build prompt: extend the 30-archive sample to
continuous full history with bounded disk throughout, then recompute snapshot and
longitudinal outputs out-of-core so they don't OOM at full scale. Diffs: `backfill.py`
(tests only — logic was already correct), `extract.py` (`export_manifest`), `cli.py`
(`export-manifest` command; `--engine`/`--duckdb-memory-gb` on `pivot`/`restatement`/`qa`),
new `ooc.py` (DuckDB out-of-core engine), new `scripts/parser_agreement_audit.py`,
`config/settings.yaml` (bug fix, see below), tests, docs. No rules, severities, or scoring
touched — not applicable to this pipeline.

### Pre-flight gates

**Gate 1 — URL fallback correctness.** Read (not modified) `fetch_archive`/`_fetch_from_url`:
the two-location fallback added in the prior chapter was already correct — `base_url` tried
first, `historic_base_url` only on an ABSENT (404) result, never on other error types. Only a
dedicated test was missing; added `test_fetch_archive_falls_back_to_historic_url_on_404` and
`test_fetch_archive_reports_absent_only_after_both_paths_404` to
`tests/test_accounts_backfill.py`.

**Gate 1 corollary — a real, launch-blocking bug found by checking the gate, not by a
crash.** `config/settings.yaml`'s `accounts.base_url` was still `https://download.
companieshouse.gov.uk/archive` — the pre-two-location value. Since this exactly matched
`HISTORIC_BASE_URL`, `fetch_archive`'s own dedup guard (`if historic_base_url.rstrip('/') !=
base_url.rstrip('/')`) would have silently skipped adding the historic candidate as a second
attempt, meaning *any* month only available at the root path (essentially all recent months)
would have been wrongly reported ABSENT. Fixed: `base_url` set to the bare root; verified via
`load_accounts_settings()` that the two URLs were distinct before the real run launched.

**Gate 2 — manifest survives store deletion.** Added `extract.export_manifest(source,
destination)`, reusing the existing `_MANIFEST_COLUMNS`/upsert pattern. Ran it for real
against the live 221 GB store before deletion (30 manifest rows copied to
`data/accounts/manifest.sqlite`), then re-verified via `ukcompany-accounts verify` (30/30
passed) before deleting the store. Added a regression test,
`test_exported_manifest_alone_skips_already_complete_months`, which mocks `fetch_archive` to
raise if called, proving a second run against *only* the exported manifest file (no store)
correctly skips already-complete months.

**Gate 3 — disk reclaim.** With the manifest safely exported and re-verified, deleted the
221 GB `data/accounts/accounts.sqlite` (+ `-wal`/`-shm`) after explicit human confirmation,
freeing headroom for the full-history run (`--disposable-store` was used throughout, so no
new monolithic store was ever created in its place).

**Gate 4 — effective start year, decided from live evidence, not assumed.** Companies House
technically serves monthly archives back to 2010, but iXBRL adoption was gradual: live
probing found 0% iXBRL in 2010, rising through roughly 3%–56% across 2011–2013, reaching
~97% by 2014. Presented this curve to the human via a direct question; **2014 was chosen as
the effective start year** — pre-2014 months are left unfetched, not because the server
lacks them but because they would need a distinct, much-lower-fill-rate validation pass this
chapter did not do.

**Gate 4 corollary — parser-agreement audit** (`scripts/parser_agreement_audit.py`, new).
Independently re-parses a sample of real filings with `lxml.etree.XMLParser(recover=True,
huge_tree=True)` and compares the resulting (concept, contextRef, text) fact set against the
production regex (`IX_FACT_RE`) — the risk being facts the regex silently never finds at all
on early-year filing-software markup it was never tuned against (the extraction invariant
`facts_seen == accounted` only proves nothing is lost *after* a fact is found). Ran against
real downloaded archives: 2013 (300 filings) → 98.0% exact agreement; 2022 (200–500 filings)
→ 82.5%. **Zero disagreements in either sample involved any of the nine target concepts.**
All disagreements were either CRLF/LF line-ending normalisation (benign) or a confirmed
regex limitation: a non-greedy `(.*?)</\s*ix:\1\s*>` match on an outer `ix:nonNumeric`
element terminates early when a same-named element is nested inside it (e.g. a date fact
embedded mid-narrative), truncating the outer element's captured text — confined to
non-numeric narrative concepts, not fixed (out of scope; flagged for future non-numeric-
concept work). One implementation bug caught and fixed while building the audit tool itself:
the lxml-side text extraction originally used `" ".join(text.split())`, which collapses all
internal whitespace and produced false-positive "disagreements" on every multi-line
narrative fact; corrected to mirror `core.py`'s own `text_content()` exactly (only replace
nbsp, strip ends).

### Two OOM incidents during development

**Incident 1 (my fault).** Ran an unbounded (no cgroup) diagnostic script comparing an
in-development `pivot_duckdb` against the real corpus *while* the legitimate backfill ran in
the background. It OOM'd at ~26.6 GB anon-rss, and because neither process was cgroup-
isolated, the kernel OOM-killer took down the entire shared VS Code cgroup as collateral,
killing both the diagnostic script and the legitimate backfill task. Root-caused via
`journalctl -k` (confirmed no reboot), disclosed directly when asked, and the backfill was
immediately resumed under a properly-tracked background task — it correctly skipped the
already-completed months via the persistent manifest. This is what hardened the standing
practice (carried over from the prior chapter, reinforced here): every full-scale operation
from this point on ran inside `systemd-run --user --scope -p MemoryMax=<N>G -p
MemorySwapMax=0`.

**Incident 2 (contained, not my process's fault — the cgroup did its job).** The full-scale
concept inventory first OOM'd at a 15 GB cap; retried at 25 GB and succeeded at 17.5 GB peak.
No collateral damage — confined entirely to its own scope, confirming the cgroup isolation
practice actually works as intended (contrast with Incident 1, where the same OOM shape
*without* isolation took down an unrelated process).

**March 2014 orphaned ZIP (an accepted design trade-off, not a bug).** Incident 1 struck in
the narrow window after `March2014.zip` had fully downloaded and verified but before
extraction/export and ZIP deletion completed. On resume, `fetch_archive`'s
"already-present, valid ZIP → `DOWNLOADED`, `downloaded_this_run=False`" short-circuit
correctly-but-conservatively treated it as not-downloaded-by-this-invocation (the same logic
that protects genuinely user-staged files from deletion — see
`test_manually_staged_archive_is_extracted_but_never_deleted`). Recorded as
`COMPLETED_KEPT` instead of `COMPLETED_DELETED`, leaving a 687 MB ZIP on disk. Verified the
archive's Parquet was complete and correct before manually deleting the orphaned file; no
code change made for this — it's the known, accepted cost of the safety check.

### The full backfill run

`ukcompany-accounts run --from 2014-01 --to 2026-08 --disposable-store`, resumed once after
Incident 1. **Result: 152/152 months present and manifest-complete, 0 absent, 0 failed,
effective covered span `2014-01` through `2026-08`** (`docs/accounts-coverage.md`).
Re-verified end to end: `ukcompany-accounts verify` → 152/152 archives' manifest observation
counts matched their archived Parquet row counts (`docs/accounts-verification.md`).

### Out-of-core engine (`src/ukcompany/accounts/ooc.py`, new)

The sample-scale implementations do not scale to full history: the Python-dict restatement
tally needed 17.8 GB over 24 months, and the sort-based pivot needed ~24.4 GB over 30
archives — both would exceed this ~30 GB machine well before 152 archives. Added DuckDB-based
`restatement_rate_duckdb`, `pivot_duckdb`, `member_histogram_duckdb`,
`total_component_reconciliation_duckdb`, `write_qa_duckdb`, wired in **additively** behind a
new `--engine {polars/python, duckdb}` flag on `pivot`/`restatement`/`qa` — the Polars/Python
engines are unchanged and remain the default. Each DuckDB function is validated against its
Polars/Python counterpart with an exact-equivalence test on synthetic data before being
trusted at full scale.

**Design decisions that only emerged after getting them wrong first:**

1. **A dedicated, explicitly-bounded connection is required.** DuckDB's implicit default
   connection's `memory_limit` is a large fraction of system RAM — an unconfigured
   connection does not meaningfully spill to disk until it has already consumed most of the
   machine. `_connect()` creates its own `duckdb.connect(":memory:")` and explicitly sets
   `SET memory_limit` and `SET temp_directory` — without this, the pivot query still OOM'd
   under a 20 GB cgroup cap despite DuckDB's out-of-core design.
2. **OR-based joins defeat the hash-join planner.** The first `pivot_duckdb` joined the
   mapping table to facts via one condition with an `OR` between the totals-shape and the
   members-shape. This forced a much more expensive join plan that OOM'd even at 20 GB.
   Fixed by splitting into two CTEs (`totals_cte`, `members_cte`), each a clean equi-join,
   combined via `UNION ALL` — mirroring how `pivot.py`'s own `_mapped_cells()` already
   handles the same distinction at sample scale. Empty totals/members lists are handled by a
   never-matching sentinel VALUES row rather than conditional branching, so both CTEs always
   have the same shape.
3. **`memory_limit` bounds DuckDB's own operators, not the Python-side result handoff.**
   Even after fixes 1–2, materialising `pivot_duckdb`'s ~47M-row provenance table via `.pl()`
   still OOM'd (safely contained in a cgroup, no collateral damage this time) — DuckDB's
   memory accounting covers joins/sorts/window functions internally, but converting a query
   *result* to Arrow/Polars happens after that accounting and needs memory proportional to
   the result size regardless of the PRAGMA. Fixed by writing directly via `COPY (query) TO
   'path.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)`, which streams through DuckDB's own
   writer instead of ever fully materialising the result in Python memory. `member_histogram_
   duckdb` and `restatement_rate_duckdb` return small (≤9-row / few-hundred-row) results, so
   `.pl()`/`.fetchall()` stays safe there; `total_component_reconciliation_duckdb`
   deliberately aggregates the summary *inside* the same SQL statement so the large row-level
   comparisons table (as big as the mapped-cell corpus) never crosses into Python at all —
   `write_qa`'s own caller already discards that table unused, so nothing is lost.

**Two further correctness bugs found from a suspicious real-corpus result, not from a
crash** — caught before being reported as fact, both now covered by regression tests that
fail without the fix:

4. **Reconciliation silently summed across parallel dimensional axes.** The first full-scale
   QA run reported an exact 0.0% agreement rate for five of nine concepts — implausible on
   its face. Root cause: `total_component_reconciliation_duckdb`'s `components` CTE grouped
   by `SOURCE_KEYS` only, omitting `dimension`, so a concept reported against *two*
   independent dimensional splits (e.g. Creditors' maturity split *and* its
   financial-instrument-type split) had both splits' members summed together into one
   inflated `component_sum` instead of being compared to the total separately — exactly the
   behaviour `qa.total_component_reconciliation`'s own
   `test_component_reconciliation_keeps_parallel_dimensions_separate` test exists to prevent,
   which the DuckDB equivalence test hadn't yet exercised. Fixed by adding `dimension` to the
   `components` CTE's `SELECT`/`GROUP BY` (matching the Polars original exactly; the join
   itself correctly stays `SOURCE_KEYS`-only, so one total can still independently match each
   parallel dimension's component sum). `test_qa_duckdb_matches_polars_qa` extended with a
   second parallel-axis case; confirmed it fails on the pre-fix code
   (`{'comparisons': 1, 'agreements': 0}` vs expected `{'comparisons': 2, 'agreements': 2}`).
5. **`agreement_rate` silently rounded to 0% or 100%.** Even after fix 4, the *rate* column
   was still wrong in a way the row-level counts weren't: Debtors showed "100.0%" despite
   1,230,885/1,363,539 ≈ 90.3% actual agreement; CashBankOnHand showed "0.0%" despite
   8,696/22,649 ≈ 38.4%. Root cause: DuckDB's `SUM(CASE WHEN agrees THEN 1 ELSE 0 END)`
   returns a HUGEINT, which round-trips through Arrow into a Polars Decimal(scale=0) column;
   dividing that by an Int64 `comparisons` column in Polars performed decimal arithmetic at
   scale 0, rounding every fractional rate to the nearest whole number (0 or 1) before it was
   ever formatted as a percentage. Every affected concept's displayed rate matched this
   rounding exactly (verified by hand for all nine). Fixed by explicitly casting both operands
   to `Float64` before dividing. Neither the original nor the parallel-axis-extended test
   caught this, because every synthetic scenario's true rate happened to be exactly 0 or 1;
   added a third, deliberately *disagreeing* comparison to the test fixture so the true rate
   is a genuine fraction (2/3) — confirmed this catches the bug
   (`Decimal('1')` vs expected `0.6666666666666666` without the cast).

Neither bug affected `restatement_rate_duckdb` (its rate is computed in pure Python from
`.fetchall()` ints, never routed through a Polars Decimal column) or `pivot_duckdb` (no
division/rate computation at all).

### Full-scale outputs, all run against the real, complete 152-archive corpus

Each run in its own `systemd-run --user --scope -p MemoryMax=<N>G -p MemorySwapMax=0` cgroup,
per the standing practice from the prior chapter and Incident 1 above.

- **Inventory** (`docs/accounts-concept-inventory.md`): 4,455 concepts, 1,968,393,998
  observations — numeric 903,014,823 (45.9%) / non-numeric 1,065,379,175 (54.1%). Employee
  GBP-unit anomaly: 7,751,582 facts (median 1.0, only 281 ≥100,000). Read-correctness: 0
  non-numeric facts with a coerced numeric value; **36,119 numeric facts with a
  missing/unresolved unit — a new finding not present at 30-archive scale** (see
  `docs/accounts-limitations.md` for the per-concept breakdown and why it's flagged rather
  than fixed here). Peak memory: retried from a 15 GB cap to 25 GB, actual peak 17.5 GB.
- **QA** (`docs/accounts-qa.md`, `docs/accounts-member-frequency.csv`,
  `docs/accounts-component-reconciliation.csv`), via `--engine duckdb`, after both bug fixes
  above: peak 13.4 GB. Real reconciliation rates: `AverageNumberEmployeesDuringPeriod` 50.3%,
  `CashBankOnHand` 38.4%, `Creditors` 22.1%, `CurrentAssets` 49.9%, `Debtors` 90.3%, `Equity`
  94.0%, `NetCurrentAssetsLiabilities` 40.2%, `PropertyPlantEquipment` 93.6%,
  `TotalAssetsLessCurrentLiabilities` 38.1%.
- **Restatement** (`docs/accounts-restatement-2014-2026.md`), via `--engine duckdb`, scoped
  to the whole continuous 2014–2026 span (no longer fragmented into sub-ranges, since the
  full run closed every gap): 178,916,771 distinct keys, 115,847,972 repeated, 10,740,756
  disagree — **9.27%**, close to but somewhat above the 2022–2023-only cross-check (7.93%,
  itself matching the independent panel check's 7.94%). Peak memory: 13.7 GB.
- **Pivot** (`data/accounts/accounts-wide-{as_first_reported,latest}.parquet` +
  `accounts-wide-provenance-{as_first_reported,latest}.parquet`), via `--engine duckdb`, both
  modes: `as_first_reported` 33,512,909 WIDE rows / 180,386,377 provenance rows (13.8 GB
  peak); `latest` 36,709,276 WIDE rows / 206,062,454 provenance rows (14.5 GB peak). The
  mode-to-mode cell-count gap observed at 30-archive/2022-H1 scale (~1.8–1.9×) narrows to
  ~1.10–1.14× at full scale — noted in `docs/accounts-limitations.md` as a scale-dependent
  characteristic, not investigated further.

### Verification

`ruff check .` clean; full `pytest` 145 passed, 1 live deselected (new: two Gate-1 tests, one
Gate-2 manifest-export test, `test_restatement_rate_duckdb_matches_python_tally`,
`test_pivot_duckdb_matches_polars_pivot`, `test_qa_duckdb_matches_polars_qa` — the last
extended twice in response to the two reconciliation bugs above, each extension confirmed to
fail on the pre-fix code before being confirmed to pass on the fix).

**Staged test gate (a), closed out live (2026-09-23, post-hoc).** The full run itself
live-exercised the "recent" half (2026-07/2026-08 downloaded and verified for real), but
every requested month in `2014-01..2026-08` came back present, so the "genuinely absent
month → `ABSENT`, not silently skipped" path had only been covered by a synthetic-server
unit test. Closed by probing `fetch_archive` live against two months from before Companies
House's earliest bulk archives (January 2005, June 2003): both correctly returned `ABSENT`
after 404s at *both* the root and `/archive/` locations (confirmed by the reported error
naming the second-tried, historic URL), and left nothing on disk. No code change; this was
a verification-only gap.

### Flag, don't decide

Per the build prompt's own framing: the 2010–2013 iXBRL-adoption gap is presented as
evidence, not resolved — 2014 was the human's choice, not an inferred one. The nested-
same-tag-name regex limitation and the 36,119 numeric-unit-gap finding are documented, not
fixed (both are outside this chapter's stated scope and neither touches the nine validated
target concepts meaningfully). numeric-only vs all-fact remains unchanged (all-fact was
already decided previously). No publishing/Kaggle step was touched.
