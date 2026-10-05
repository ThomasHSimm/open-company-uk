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

## Finish the accounts chapter — publishable Kaggle dataset (2026-09-24)

Turned the completed archive into a `kaggle/` and `kaggle-long/` staging pair ready for the
human to upload. No re-extraction, no backfill rerun, no out-of-core-engine change beyond
what the tasks below needed. Diffs: `ooc.py` (four new functions), `pivot.py` (one-line
correctness fix, see below), `cli.py` (`build-public-long` command,
`--employee-gbp-cutoff` on `pivot`), new `public_long.py`, new
`scripts/kaggle_staging_guard.py`, `config/accounts-wide-columns.json`, tests, docs, and the
`kaggle/`/`kaggle-long/` staging folders themselves (gitignored, not part of the code diff).
`ruff check .` clean; full `pytest` 159 passed, 1 live deselected throughout (new: Creditors
bucketing test, employee-distribution test, employee-cutoff pivot test,
restatement-by-year test, null-shadowing regression test on both engines, `public_long`
build tests ×2, staging-guard tests ×7).

**Task 1 — Creditors maturity columns, added.** Built
`ooc.creditors_maturity_reconciliation_duckdb`, run over the full corpus (20 GB cgroup cap):
of 3,998 filings with both a Creditors total and a maturity-dimension component, `sign_flip`
was **zero**, `other` was 20.6%, and — investigated further because 20.6% looked too large to
wave through — 92% of the "complete axis" `other` cases turned out to be explained by the
total equalling exactly one maturity bucket (mostly `WithinOneYear`, 80.3% of the 833 such
cases) rather than a genuine sum. Since `sign_flip` is unambiguously negligible and
disagreements are dominated by `incomplete_axis` (79.1%) with the rest independently
explained (not implicating the member values), the decision rule's condition is met:
`creditors_within_one_year`/`creditors_after_one_year` added to
`config/accounts-wide-columns.json`. Full writeup, including the borderline judgment on
whether the "other" finding should have blocked publication:
`docs/accounts-creditors-maturity-reconciliation.md`.

**Task 2 — employee GBP-unit cut-off, human-approved at 250.** Built
`ooc.employee_unit_distribution_duckdb`; compared GBP-tagged (7,715,981 facts) against
`pure`-tagged (28,007,617 facts) non-dimensional employee-fact distributions. Presented four
candidate cut-offs (p99=54, p99.9=250, p99.99=2,342.5, and the prior ad-hoc 100,000) with
their kept/nulled splits via `AskUserQuestion`, rather than picking one — this is explicitly
a "flag, don't decide" item in the brief. **Human chose 250** (the brief's own example
method, p99.9 of `pure`). `pivot_duckdb` gained an `employee_gbp_cutoff` parameter: nulls a
GBP-tagged employee value above the cutoff and sets a new `employees_unit_anomaly` WIDE
column (1 = winning fact was GBP-tagged, kept or nulled; 0 = other unit; null = no employee
fact selected). Stage 1/LONG untouched — WIDE-only. Full derivation:
`docs/accounts-employee-unit-cutoff.md`.

**Two real bugs found and fixed while building the cutoff feature, before running anything
at scale:**

1. **`_NEVER_MATCHES` sentinel embedded a NUL byte in a SQL string literal.** Building a test
   with an empty `mapping.members` list (the first time any test had exercised that path
   through `pivot_duckdb`) hit `_duckdb.ParserException: unterminated quoted string` — the
   sentinel `"'\x00never-matches\x00'"` used to keep the totals/members `UNION ALL` shape
   consistent when a mapping list is empty was never actually exercised end-to-end before
   (every prior test used a mapping with both totals and members non-empty). Fixed by
   replacing it with a plain ASCII placeholder string
   (`'__never-matches-a-real-concept-name__'`) that can never collide with a real XBRL
   concept/dimension/member name.
2. **A blank/dash source fact could shadow a real value from a different filing.** Verifying
   "provenance matches WIDE one-to-one" (a stated Task 3 requirement, not just a bug hunt)
   found 10,382 provenance rows for `Creditors` alone with no matching non-null WIDE cell,
   traced to `raw_value='-'`/`numeric_value=NULL` facts (a real, legitimate Stage 1 shape,
   not corrupted data) winning the source-ranking and blocking a usable value elsewhere —
   present in **both** `pivot.pivot_long` (the sample-scale reference) and
   `ooc.pivot_duckdb`, since neither ever excluded `numeric_value IS NULL` from the candidate
   pool. Fixed in both engines (kept them equivalent, since the existing `pivot_duckdb`-vs-
   `pivot_long` tests depend on it), covered by a new regression test exercising both. This
   is a genuine improvement to what gets published, not just a bookkeeping fix — it changes
   which value wins a cell, not just which one gets reported as its provenance.

**Task 3 — WIDE rebuilt, both modes, full corpus, verified.** `as_first_reported`: 33,461,467
rows (was 33,512,909 pre-chapter; net effect of the two Creditors columns plus the
null-shadowing fix, both increasing and decreasing row count for different reasons — see
`docs/accounts-wide-rebuild-verification.md`); `latest`: 36,623,698 rows. Every mapped column
now has **zero** provenance-vs-WIDE gap except `AverageNumberEmployeesDuringPeriod` (1,225
rows in `as_first_reported`), which is exactly the intended cut-off nulling, not a defect.
Company numbers confirmed `VARCHAR` with leading zeros intact; zero published monetary cells
trace to a source fact with a missing/unresolved unit. One retry needed: the `latest`-mode
rebuild first OOM'd inside DuckDB's own 12 GB internal limit (not the 20 GB cgroup cap) —
resolved by raising `--duckdb-memory-gb` to 16–18 with a 24 GB cgroup cap, succeeding at
17.6–21.1 GB peak.

**Task 4 — restatement by year.** Added `ooc.restatement_rate_by_year_duckdb`, grouped by
year of first filing rather than concept. Guarded the divide-by-zero case (a year with zero
repeated keys) with an explicit `pl.when(...).otherwise(0.0)`, mirroring
`RestatementRateResult.disagreement_rate`'s existing Python-level guard — without it, a year
with no repeats yet (e.g. the still-open 2026) would divide 0.0/0.0 to `NaN`. Real result:
7.9–10% for most years, but 2016–2017 restate distinctly more (13–15%) — see
`docs/accounts-restatement-by-year.md`. Not investigated further which of "less-settled
early filer-software conventions" or "longer time-to-restate window" (or both) drives the
bump.

**Task 5b — public LONG, denylist/allowlist approved before staging.** Built the numeric
denylist by pattern-matching concept names
(`director|officer|keymanagement|related.?party|remuneration`, plus `trustee` added by hand
after a second pass) against the concept inventory: 95 concepts, 8,697,598 observations
(0.44% of numeric data). Built the non-numeric allowlist strictly from the brief's six named
categories: 17 structured concepts (dates, registered number, filing software, dormant/
trading/audited/legal-form/accounts-type flags), 297,568,003 observations; everything else
non-numeric dropped, including `EntityCurrentLegalOrRegisteredName` explicitly. Presented
both lists with three flagged borderline cases (bare director/trustee headcounts kept in the
denylist by conservative default) and a four-concept "plausibly safe but not named in the
brief" appendix via `AskUserQuestion`; **human approved as written**. Lists live in
`src/ukcompany/accounts/public_long.py` as the single source of truth, reused by both the
builder and the staging guard so they cannot silently drift apart. Built via
`build_public_long_duckdb` (`COPY ... TO ...`, one Parquet per year, cgroup-wrapped, filters
the existing per-month Parquets only): 1,301,140,617 rows across 2014–2026, spot-checked
post-build to confirm only the 17 allowlisted non-numeric concepts appear and
`EntityCurrentLegalOrRegisteredName` has zero rows. Full lists and review:
`docs/accounts-public-long-concepts.md`.

**Task 5 — Kaggle WIDE packaging.** `kaggle/` contains both WIDE files, both provenance files
(human chose to include them over the smaller-download alternative), `README.md` (dataset
card), `column-dictionary.{csv,md}` (one row per column with coverage %, computed from the
real rebuilt files, not estimated), `dataset-metadata.json`, and `starter.ipynb`.
`dataset-metadata.json` uses `licenses: [{"name": "other"}]` with the OGL text embedded in
the description — Kaggle's current license enum wasn't verified live, so this is the safe
fallback per the brief's own instruction, flagged for the human to check before upload.
Title and `id` are explicit placeholders (`INSERT_KAGGLE_USERNAME/...`), per "flag, don't
decide". **The starter notebook was actually executed against the staged files, not just
written** (`jupyter nbconvert --execute`) — this caught a real, if tiny, pre-existing data
artifact: 14 of 33.4M rows (0.00004%) have an obviously mistyped `period_end` year (e.g.
3020, 2924 — filer data-entry errors, kept as-read, not corrected), which dominated the
notebook's "coverage by year" demo table until the cell was fixed to restrict to a plausible
year range with a note explaining why.

**Task 6 — safety checks, all passed.** WIDE schema listed and confirmed to contain only the
company number, two dates, financial values, and summary columns (19 columns total, no
name/address/free-text field). `scripts/kaggle_staging_guard.py` scans every Parquet in
`kaggle/` and `kaggle-long/`: for LONG-shaped files, checks every fact's concept against the
denylist/allowlist; for WIDE-shaped files (no `concept` column — concepts are column names),
checks column names against the denylist plus an *independently re-derived* person-name
regex (not just a re-check of the same list the builder used, per the brief's own reasoning
that the guard should check the lists, not only trust them). Regression-tested with 7 cases
(one clean pass per file shape, six synthetic violations each confirmed caught) before
trusting it against the real folders. The stale 2026-09-21 `accounts-wide.parquet`/
`accounts-wide-provenance.parquet` were moved to `data/accounts/_stale/` before rebuilding,
so there was no path by which they could have been staged. Full report:
`docs/accounts-kaggle-safety-checks.md`.

**Task 7 — docs finished.** `docs/accounts-limitations.md` gained a full "Kaggle publication
chapter" section with all the numbers above. New `docs/site/accounts.qmd` (no prior accounts
page existed on the site; created, added to `_quarto.yml`'s navbar, rendered successfully via
`quarto render docs/site` to confirm it doesn't break the build).

### Flag, don't decide (this chapter)

Employee cut-off (250) and the denylist/allowlist were both explicitly approved by the human
via `AskUserQuestion`, not inferred. Provenance-files inclusion: presented as a size-vs-
completeness tradeoff; **human chose to include both** provenance files in `kaggle/`. Kaggle
dataset title and `id` remain literal placeholders in both `dataset-metadata.json` files —
not decided here. The `dataset-metadata.json` license field defaults to `"other"` with OGL
text embedded, since Kaggle's current license enum wasn't checked live; flagged for the human
to verify (and switch to a named OGL entry if Kaggle now lists one) before upload. The four
"plausibly safe" non-numeric concepts excluded from the allowlist by conservative default
(`ScopeAccounts`, `CountryFormationOrIncorporation`, `PrincipalCurrencyUsedInBusinessReport`,
`ReportPeriod`) were not added — the human approved the list as written, without them.

### Upload commands (human runs these; not run here)

```
kaggle datasets create -p kaggle/
kaggle datasets create -p kaggle-long/
```

Both require `dataset-metadata.json`'s `id` (and ideally `title`) to be filled in first — see
the placeholders above — and the Kaggle CLI to be authenticated
(`~/.kaggle/kaggle.json`). Neither command was run by this agent.

### Post-close: real IDs filled in, commit provenance recorded (2026-09-25)

The human filled in both `dataset-metadata.json` placeholders themselves:
`thomassimm/uk-company-accounts-wide-2014-2026` and
`thomassimm/uk-company-accounts-long-2014-2026` (license left as `"other"`, per the flag
above — not resolved either way). `pyproject.toml`'s `dev` extra was also missing `duckdb`
and `pyarrow` (installed locally outside the declared dependencies, so CI's fresh install
failed on both in turn); fixed by adding `duckdb>=1.0` and `pyarrow>=14.0` (the latter needed
because DuckDB's `.pl()` conversion goes through Arrow). Committed as `c768486` ("Kaggle
accounts upload v1") and `4eb5ec9` ("Fix pytest ci test") on `kaggle_build`.

**Kaggle dataset v1 = commit `4eb5ec9`.** Both `kaggle/README.md` and
`kaggle-long/README.md` now name this commit as the exact code state that produced their
Parquet files, so anyone auditing a published number can check out that commit and see the
pipeline that made it. This repo's prior two PRs (#1, #2) both merged via a regular "Merge
pull request" commit, which preserves commit SHAs unchanged onto `main` — so this reference
should remain valid after merging, unless a future merge uses squash or rebase instead (which
would need the reference updated). If a v2 upload is ever made after further fixes, update
both README lines and this entry to the new commit — a stale commit reference here would be
actively misleading, not just outdated.

## Accounts parser check — prefix bug fix, benchmark, three-way comparison (2026-09-27)

Full report: `docs/accounts-parser-check.md`. Branch `feature/accounts-parser-check`; nothing
pushed. New scripts (all gitignored-data-producing, not part of the package):
`scripts/parser_census.py` (Phase 1), `scripts/parser_benchmark.py` +
`scripts/run_phase3_matrix.sh` (Phase 3), `scripts/parser_compare.py` +
`scripts/arelle_correctness.py` (Phase 4).

**Real bug fixed in `core.py`/`extract.py`**: `IX_FACT_RE` hardcoded the literal `ix:`
prefix, silently returning zero facts for any filing binding the inline-XBRL namespace to a
different prefix or to the default namespace. Fixed to match any prefix (or none), via the
same `(?:[\w.-]+:)?` idiom already used elsewhere in `core.py`. Added
`zero_fact_ixbrl_filings` (a filing-level flag, deliberately excluded from the
`accounted()`/`closes()` invariant) so a filing with inline-XBRL markup but zero matched
facts is never mistaken for a genuinely clean/empty filing. Six new regression tests in
`tests/test_accounts_core.py`; verified two of them genuinely fail on the pre-fix code via
`git stash` (not just written and trusted). Full suite: 167 passed, ruff clean.

**A second, more subtle bug was found in this task's OWN audit tooling, not in `core.py`**:
the census script's namespace-detection regex (and an early draft of `core.py`'s own
`IX_NAMESPACE_RE`) matched double-quoted `xmlns:ix="..."` only. A real single-quoted
`xmlns:ix='...'` filing from 2013 was misclassified as "no namespace binding detected",
inflating the naive bug-footprint estimate to 612,750 filings. Caught by a LONG cross-check
(bug-affected filings should have zero corresponding LONG rows; found 311,610 mismatches),
not by trusting the first number computed. Fixed with the same quote-agnostic backreference
idiom already used by `core.py`'s pre-existing `ATTR_RE`; corrected estimate: **≈291,802
filings (95% CI [264,049, 324,455]), concentrated in 2014-2022**, cross-check mismatches
dropped to zero. The lesson generalises: a regex-based audit tool can carry the same class of
bug as the code it's auditing, and needs its own independent verification, not just internal
consistency.

**A real Arelle robustness bug was found and fixed mid-benchmark**: a filing referencing an
unresolvable extension taxonomy (`dpl-frs`) caused Arelle to hang for 2+ hours against a
60-second budget, with the in-process `signal.alarm()` timeout never firing because Arelle
never yielded back to the Python bytecode loop (it was genuinely busy, logging thousands of
repeated schema errors, not deadlocked). Diagnosed via `/proc/<pid>/fd` and `/proc/<pid>/wchan`
(showed a running, non-blocked process) and finally the Arelle worker's own 61MB log file, not
`py-spy` (blocked by ptrace restrictions, no sudo used). Fixed by moving Arelle's timeout
enforcement to a hard subprocess-level kill (`multiprocessing.Process` + `.join(timeout)` +
`.kill()`); ours and ixbrlparse, being pure-Python, were left on `SIGALRM`. This fix was
load-bearing for the rest of Phase 3 and for the later Arelle correctness-set run (7,977
files, zero failures/timeouts) — a `SIGALRM`-only design would very likely have hung again on
similar pathological filings at that scale.

**Benchmark headline** (5,000-file fixed subset, e2e/1-worker): ours ~11.8x faster than
ixbrlparse, ~1,520x faster than Arelle, zero failures (ixbrlparse: 2/5,000, both
`IXBRLParseError: Filetype not recognised` on early-vintage filings — an independent blind
spot in ixbrlparse's own type-sniffing for the same 2013/2014 markup era as the quote-style
bug above). Projected full-archive wall-clock at measured 8-worker throughput: ~2.1h (ours)
vs ~34.5h (ixbrlparse) vs ~94.6 days (Arelle) — Arelle is not viable at this archive's scale
under any parallelism this machine can offer.

**Fact-level comparison** (ours vs ixbrlparse, same subset): 89.5% agreement on 271,795
shared facts. Disagreements decompose cleanly: two are documented design differences (nil-dash
deferred to pivot time; untransformed text vs Transformation-Registry-normalised text — both
confirmed as design choices, not defects, by the Arelle three-way cross-check below); two are
genuine, fixable-in-principle bugs in ours (no `ix:continuation`-chain following; a
nested-same-name-element defect that silently truncates or entirely swallows facts — both
confirmed by Arelle agreeing with ixbrlparse 95-100% of the time on these specific
categories); the rest are ours' by-design scope exclusions (multi-member and typed-member
dimensional contexts, plain-XML filings).

**Recommendation reported (not implemented), per the brief**: (b) — keep ours as the default
parser (speed), fall back to ixbrlparse for the 15,484,687 filings (43.3% of the archive,
computed directly from the existing full-archive census, no new scanning needed) that are
structurally out of ours' scope by design. The continuation/nested-fact bugs (14.9% of the
archive, overlapping with the above) are flagged as a separate, scoped follow-on fix
opportunity rather than folded into the permanent ixbrlparse-fallback population. Full
evidence and the two rejected alternatives ((a) ship the prefix fix alone; (c) switch to
ixbrlparse entirely) are in the report.

### Flag, don't decide (this chapter)

The optional WIDE-table cell-by-cell comparison (brief's Phase 4, conditional on ≥2h
remaining) was assessed against the real cost — a second reconciliation pipeline mapping
ixbrlparse's facts into the `pivot.py`/`WideColumnMap` schema, not an incremental extension of
the fact-level comparison already done — and skipped given time already spent; stated
explicitly in the report rather than silently omitted. The Arelle correctness-set's size
(7,977 files: all 4,977 disagreeing files plus a 3,000-file random top-up, ~33 minutes at 8
workers) was a judgement call sized from measured throughput, not a maintainer instruction —
flagged in the report. Recommendation (b) is reported with full evidence but not implemented,
per the brief; the maintainer decides whether/when to schedule the prefix-bug re-extraction
and the ixbrlparse-fallback pass, and whether the continuation/nested-fact bugs are worth
fixing directly in `core.py` before or instead of relying on ixbrlparse fallback for those
filings.

### Assumptions needing live verification

The Arelle hang's root cause (accumulated in-process controller state vs something specific
to the triggering file) is an informed hypothesis from a single isolated re-test (~13s, 126
facts, vs 2+ hours originally), not a proven mechanism — the original stuck process's state
could not be recovered once killed. The Arelle correctness-set's fact-key join (§4 of the
report) is explicitly best-effort, not as rigorously reconciled as the ours-vs-ixbrlparse
`FactKey` match — Arelle's own date-shifted context model (instant dates surface one day
later, XBRL's exclusive-end convention) was corrected for empirically after probing one real
file, but was not exhaustively verified across every context shape in the archive. The
projected full-archive timings (§3 of the report) scale measured 5,000-file throughput
linearly to 35.8M filings — a reasonable first-order estimate, but not verified against an
actual full-archive run of any of the three parsers.

## Accounts parser v2: fix, rerun, and correct the documentation (2026-09-27)

Full report: `docs/accounts-parser-check.md` §6 onward. Branch `feature/accounts-parser-check`
throughout (same branch as the prior chapter); nothing committed, nothing pushed, nothing
uploaded to Kaggle. v1 (`data/accounts/long/`, `data/accounts/accounts-wide-*.parquet`,
`kaggle/`, `kaggle-long/`) untouched; v2 writes exclusively to `data/accounts/v2/`,
`kaggle-v2/`, `kaggle-long-v2/`.

**Phase A (analysis, no code changes)** restricted the existing Phase 4 comparison to the 13
WIDE columns: 93.5-99.85% agreement, every disagreement either the nil-dash design choice or
one of two known ixbrlparse hard-failures. Numeric-only, dash-excluded agreement: **99.999%
(119,812/119,813, 95% CI [99.995%, 100%])** — the figure now published in place of 89.5%. A
typed-member personal-data scan (found and fixed a prefix-capture regex bug in the scan
itself first — a colon-less character class was capturing only the namespace prefix, not the
local name, the same class of mistake this whole audit exists to catch) found every sampled
typed dimension code-shaped, substantiated with non-identifying aggregate stats (100%
all-digit, max 2 characters for the two "Directors"-named dimensions) rather than a
classifier's say-so alone.

**Phase B**: nested facts and continuations were assessed against the maintainer's explicit
threshold (fix only if >0.1% of numeric facts or any WIDE concept affected) and found at
0.0015% / zero WIDE concepts — **deferred, not fixed**, per instruction. Comma-as-decimal
number formats (`numdotcomma`/`numcomma`/`numspacecomma`/`numcommadecimal`, `ixt`/`ixt2`) were
fixed in `normalise_number`; an unrecognised format now nulls and counts rather than
guessing. Six new tests, five verified to fail on pre-fix code via `git stash`. Speed impact
unmeasurable (within run-to-run noise).

**Phase C**: new `src/ukcompany/accounts/xml_adapter.py` routes plain-XML filings (previously
`xml_skipped`) through `ixbrlparse` into the same `FactObservation` schema as the iXBRL path,
via a small `core.py` refactor exposing the existing grouping/dedupe logic to both paths
rather than duplicating it. Two things confirmed empirically before writing the adapter, not
assumed: ixbrlparse already applies scale/sign internally (re-applying them would double-
count); its own `segments` list has a duplicate-entry quirk for typed members (BeautifulSoup's
`findChildren()` walks all descendants, not just direct children). New `parser` provenance
column on every observation (`OBSERVATION_SCHEMA_VERSION` 2→3), propagated to Parquet export
automatically via the existing column-list-driven design. Ten new tests. Checked against
Arelle on 200 real `.xml` filings: 100% agreement on shared facts (5,845/5,845), zero misses
across 186 successfully-compared files (14 excluded — a pre-existing, unrelated zero-byte
sample-extraction artifact from the 2015-12 archive month, found incidentally, confirmed
isolated and non-overlapping with the earlier HTML-only benchmark subset).

**Phase D**: disk-checked (441 GB free, ~30 GB v1 footprint, nowhere near the 50 GB floor),
then found that `ukcompany-accounts run` has no built-in parallelism — a live single-threaded
run measured ~820 filings/sec, projecting ~12.1 hours against the brief's ~4-5 hour estimate
(which came from Phase 3's benchmark *scripts*, not the production CLI). Flagged to the
maintainer with three options; the maintainer chose to parallelise. Killed the single-
threaded run (zero completed months, nothing wasted), smoke-tested a 2-worker/limited-filing
run, then launched 8 concurrent `ukcompany-accounts run` invocations over disjoint ~19-month
ranges (`scripts/run_phase_d2_parallel.sh`) — separate `--store` per worker (SQLite doesn't
tolerate concurrent writers), shared `--output-dir` (disjoint month ranges never collide on
filename). All 152 months completed, zero errors; manifests merged via the existing
`export-manifest` command. Rebuilt WIDE (both modes + provenance), public LONG
(1,312,845,786 rows), concept inventory (4,593 concepts), and restatement (overall + all 13
years) from v2 LONG via the DuckDB engine, each inside a `systemd-run` cgroup. One transient
failure: the by-year restatement loop was OOM-killed at a step transition after four earlier
steps had already succeeded; relaunched in a fresh cgroup with more headroom, completed
cleanly. Staging guard passed on `kaggle-v2/`/`kaggle-long-v2/` (hard-linked, not copied).

**Phase E, the headline finding of this chapter**: diffing v1's and v2's actual output
directly (no sampling) found the prefix-bug fix genuinely recovered **61,085 filings** — not
the ≈291,802 the prior chapter's sample-based, census-regex-proxy methodology had estimated.
Spot-checking ten real filings from that estimate's source population found all ten already
had complete, identical row counts in both v1 and v2 — they were never bug-affected. Root
cause: the census's namespace-*declaration* detector and the actual fact-*extraction* regex
are two independent regexes matching two different things, and they disagreed on more filings
than the earlier 2,907-filing LONG cross-check happened to catch. **This is logged as an
erratum in `docs/accounts-parser-check.md` §1, not a silent rewrite** — the original ≈291,802
figure and its derivation are left in place so the record shows how understanding evolved.
Two DuckDB queries needed rework mid-run at this scale: a naive multi-column join across
facts with duplicate/conflicting status exploded into a disk-filling cartesian product (fixed
by restricting to `status='selected'` rows, the only shape that comparison makes sense for
anyway); a 7-column anti-join across ~2 billion rows exceeded a 22 GB cgroup (fixed by
joining on one hashed key column instead of seven raw text columns). Full results: 273,418
XML-caused + 61,085 prefix-fix-caused new filings (20,955,250 new observations); 1,108
facts changed value (comma-decimal fix, confirmed against real examples both directions);
**zero regressions** (every v1 fact still present in v2); WIDE `as_first_reported` shows
~61,000 newly-filled cells per column (matching the prefix-fix filing count almost exactly);
`latest` mode's larger "changed" counts trace to newly-recovered filings sometimes becoming
the new most-recent-filing winner, not a new defect; restatement rate unchanged (9.36%
before and after); fill rates unchanged to within 0.3 percentage points on every column.

**Phase F**: `docs/accounts-limitations.md` corrected — the old "every concept, all-fact,
exactly as read" claim replaced with the exact multi-member/typed-member counts and the
typed-member personal-data finding; the nested-fact/continuation paragraph updated from the
prior chapter's vaguer "not fixed, out of scope" framing to the precisely-quantified,
reasoned-deferral framing above; the 89.5% figure replaced with 99.999%-on-numeric-facts,
worded exactly as instructed ("99.999% on numeric facts (dashes excluded; resolved
identically at pivot)"). `docs/accounts-validation-summary.md` and
`docs/source-material/deck-corrections.md` written (no site-restructure branch exists, so the
brief's fallback path was used for the former). `kaggle-v2/` and `kaggle-long-v2/` staged
with full changelog READMEs (not uploaded); their `dataset-metadata.json`/commit references
are placeholders pending an actual commit, unlike v1's which name a real commit SHA.

### Flag, don't decide (this chapter)

The Phase D2 parallelisation approach (kill-and-relaunch 8-way vs. accept the ~12h
single-threaded runtime vs. build-and-validate-alongside) was put to the maintainer via
`AskUserQuestion` rather than decided unilaterally; the maintainer chose parallelisation.
Nested-fact and continuation fixes were assessed against a maintainer-specified numeric
threshold and deferred once the measured rate came in under it — an instruction-following
outcome, not an independent judgement call. The Phase E prefix-bug erratum is reported as a
correction to prior work, not smoothed over; the maintainer should treat any other figure in
the prior chapter that rested on the same census-regex classification (rather than a direct
before/after diff) with the same caution until similarly re-verified. Kaggle v2's commit
reference is left as an explicit placeholder rather than guessed — the maintainer fills it in
once this branch's changes are actually committed and reviewed, matching how v1's README was
finalised (see the "Post-close" entry in the prior Kaggle chapter above).

### Assumptions needing live verification

The 8-way parallel `run_phase_d2_parallel.sh` split was smoke-tested on a 2-worker/limited-
filing run before the full launch, not on a full month pair — the full 152-month run's
success is the real validation, but if it's ever rerun on a machine with materially different
core count or network conditions, the per-worker `MemoryMax=4G` cgroup setting should be
re-checked (no worker was observed near that ceiling in this run, but it was not stress-
tested deliberately). The XML adapter's Arelle cross-check excluded 14 of 200 sampled files
for the zero-byte artifact; that artifact's root cause (a Phase 1 sample-extraction issue
specific to the 2015-12 archive month) was characterised but not fixed or explained further —
if the same issue recurs in a future re-extraction, it needs its own investigation. The
"other_new_coverage" cause label in Phase E's new-filing-coverage breakdown assumes every
non-XML newly-covered filing is prefix-fix-caused; this was not individually verified file by
file beyond the ten-filing spot-check reported above (a systematic secondary cause,
if one exists, would currently be invisible inside that bucket).

## Erratum contradiction resolved; a second real bug found and fixed (2026-09-28)

The maintainer caught a genuine contradiction between this chapter's §1 ("0 of 2,907 mismatches")
and its own erratum ("10 spot-checked filings had full v1 rows") and asked for it to be
traced to ground truth before anything was staged or uploaded — not glossed over with a
plausible-sounding explanation. It wasn't glossed over; the actual root cause was different
from, and more interesting than, either original claim.

**Root cause of the contradiction**: `find data/accounts/parser-census -name "*.parquet"
-newer scripts/parser_census.py` returns **0 of 152** — the persisted census Parquet files on
disk were never regenerated after `IX_NS_RE`'s quote-style fix was applied to the script.
Every `ix_prefix` classification this whole chapter's earlier work relied on — the ≈291,802
estimate, the "0 of 2,907" cross-check, and this session's own 10-file spot-check — was
computed from the *same stale, pre-fix data* the whole time. Confirmed directly: the current,
correctly-fixed `detect_ix_prefix()` returns `"ix"` for the exact traced example filing
(`Prod224_0005_03318735_20140331.html`); the stale Parquet says `"none"`.

**A deeper issue found while chasing this**: even with the quote-fix correctly applied,
re-scanning the *entire* 1% sample fresh (353,562 real files, not from stale Parquets) found
**zero** files classified `"none"`. Namespace-*declaration* presence was never a reliable
proxy for "will this filing's facts extract correctly" — a filing can declare `xmlns:ix=...`
and still tag its actual facts with a different prefix. The census's `ix_prefix` field
measures the wrong signal, independent of the quote bug. This means the ≈291,802 estimate
(and this chapter's own erratum, which tried to explain the mismatch via "the LONG cross-check
happened not to catch it") were both built on a methodology that was never going to reliably
track the real bug, on top of also using stale data.

**What was NOT wrong**: the direct v1-vs-v2 diff (Phase E) never touched the census's
`ix_prefix` field — it compares actual LONG output row-for-row. The 61,085 figure was
correct throughout, now corroborated a second, independent way: a full-archive anti-join
confirms **zero `.html` filings have zero rows in v2, in any year** (`zero_fact_ixbrl_filings
= 0` archive-wide) — the prefix fix is complete, no residual gap exists to find.

**A second, real, separate bug was found and fixed** while answering the maintainer's Q5
("trace WIDE newly-null cells — a published value disappearing needs an explanation"):
`normalise_number` recognised `numdotdecimal` but not the hyphenated Transformation Registry
spelling `num-dot-decimal` — the exact same format family, just punctuated differently.
Confirmed on a real 2024 filing (`format="ixt2:num-dot-decimal"`, raw `"49,386"`), then
confirmed archive-wide via the existing format census (no re-scan needed): 540 occurrences,
confined to exactly 3 months (July2024, July2026, August2026). This bug had been silently
nulling values that parsed *correctly* even before this chapter's comma-decimal fix existed —
a genuine regression introduced by the comma-decimal fix's own "never guess at an
unrecognised format" safety net, which is correct in principle but was matching format names
too literally. Fixed with `normalise_format_name()` (strips hyphens/underscores before
matching); tested against the real markup, and specifically verified to fail when *only* the
hyphen-normalisation is reverted (not just against the pre-chapter baseline, which would have
passed the value assertion by coincidence, since the ancient code doesn't read `format` at
all and comma-stripping happens to be right for this particular raw value). The 3 affected
months were re-extracted, WIDE/public-LONG/restatement rebuilt from the corrected LONG, and
every downstream Phase E number reverified: value-changed count 1,108→1,096 (12 facts that
were only "changed" because they were wrongly null), **every WIDE "newly null" cell across
every column and both modes is now exactly 0** (was 11–73 per column), regression check
re-run and still 0, restatement rate re-confirmed unchanged at 9.36%. `kaggle-v2/`/
`kaggle-long-v2/`'s hard-linked staged files were stale after the WIDE/public-LONG rebuild
(different inodes — `pivot`/`build-public-long` write-then-replace) and were refreshed;
staging guard re-run and passed. Nothing was staged or uploaded before this was fully
resolved, per the maintainer's explicit instruction.

### Flag, don't decide (this sub-chapter)

None — this was pure verification and bug-fixing in response to a direct maintainer
instruction, not a judgement call with a choice to flag.

### Assumptions needing live verification

The `numunitdecimal` format (36 occurrences across 8 months) remains correctly left as
"unrecognised, null" — its semantics were not researched or guessed at, per the "never
guess" principle, since 36 occurrences didn't warrant the risk of a wrong guess. If this
format's meaning is ever confirmed, `normalise_number` should be updated accordingly. The
census's `ix_prefix` field is now known to be an unreliable signal even when correctly
computed (namespace declaration presence != actual fact-tag prefix usage) — any future work
that wants a per-filing "was this specific filing bug-affected" answer should use a direct
before/after extraction diff (as Phase E does), not the census classification, regardless of
whether the persisted Parquet files are ever regenerated.

## Site restructure (`site_restruct` branch, 2026-10-02)

Rebuilt `docs/site/` from a 5-page methodology site into a hub with a navbar of **Home · Guide ·
Datasets · Indicators · Landscape · Evidence · Reference**, per the build prompt. **Text files
only — no code under `src/`, `scripts/` or `tests/` was touched, and no `quarto render`/`preview`
or other heavy command was run**, to avoid disturbing the parser-check benchmark that was running
and had frozen code changes. The one-off render and link check are deferred until the maintainer
confirms the benchmark's timed phase has finished.

### What was built

- New `_quarto.yml` (dropdown-menu navbar, `cosmo` theme, GitHub link, OGL/not-affiliated page
  footer; title changed from "open-company-uk methodology" to "open-company-uk").
- Rewritten `index.qmd`; four `guide/` pages; three `datasets/` pages; four `indicators/` pages
  (three moved from the old top level + a new `non-compliance.qmd` placeholder marked Planned);
  two `landscape/` pages; two `evidence/` pages; `reference.qmd`. Every page opens with a
  plain-language Summary then a separate Details section; figures carry a named repo-file source
  and a Checked/Estimated/Not-verified label.
- `docs/site/_CHANGES.md` records every content move (named with a leading underscore so Quarto
  does not render it into the published site — it is a maintainer reference, not a page).
  `docs/source-material/ch-guide-contribution.md`
  is a draft contribution for the maintainer to review (explicitly **not** submitted).

### Source material staged

The deck, notes, accounts explainer and the two parser-comparison scripts were in `~/Downloads`,
not in `docs/source-material/` as the prompt anticipated. The text-based ones were copied in
(latest variants: `…-notes(2).md` → `companies-house-accounts-notes.md`, `index.html` →
`accounts-explainer.html`, both `.py` scripts). The binary `.pptx` was **not** copied (text-only
constraint); its slide + speaker-note text was extracted with a stdlib `zipfile`+ElementTree
reader into `companies-house-accounts-deck.md` (the scratchpad extractor script is not in the
repo). `python-pptx`/`markitdown` were unavailable and were not installed.

### Flag, don't decide / deviations flagged

- **`indicators/methodology.qmd`**: the two links to the generated docs were changed from relative
  `../rules.md` / `../data-dictionary.md` (which point outside the `docs/site/` Quarto project and
  would render as broken links) to GitHub `blob/main` URLs. This is the only edit to
  otherwise-"moved unchanged" content; flagged here and in `_CHANGES.md`.
- **Restatement figure**: the old `accounts.qmd` cited 9.27%; the new dataset pages use **9.36%**
  (the post-dash-nil-fix value from `docs/accounts-limitations.md` / `kaggle-v2/README.md`). Both
  are sourced; 9.27% was pre-fix.
- **Kaggle links** are presented as clearly-labelled placeholders (slugs from the
  `dataset-metadata.json` files), **not** as verified live links — the deck notes say to add them
  once published, so publication status was treated as unconfirmed rather than checked over the
  network.
- Four superseded top-level pages (`methodology`, `validation`, `limitations`, `accounts`) were
  `git rm`-ed after their content moved; `accounts.qmd` is superseded by `datasets/accounts.qmd`
  plus `guide/accounts-data.qmd`.

### Assumptions needing live verification

- The REST API rate limit (~600 req/5min) is repeated from the deck notes and labelled **[Not
  verified]** on the site; confirm against current developer docs.
- `evidence/register.qmd` is **structure only** — the populated append-only register is not yet
  written; the page shows the discovery queue and schema and says so.
- The one-off `quarto render` + internal-link check (acceptance criterion) is **not yet done** —
  deferred until the benchmark is confirmed finished. Cross-page links were written to resolve
  within `docs/site/` (section-relative paths) and all generated-doc / repo references use GitHub
  `blob/main` URLs; these still need the live render to confirm.

### Post-review fixes (same branch, 2026-10-02)

Rendered once (17 pages) and link-checked after the maintainer confirmed the benchmark was done;
then three maintainer review points were addressed:

- **`CHANGES.md` was being published.** Quarto renders every `.md`/`.qmd` in the project, so the
  internal moves-log appeared as a site page. Renamed to `_CHANGES.md` (Quarto skips leading-`_`
  files); re-render dropped from 18 to 17 pages with no `CHANGES.html` in `_site`. References in
  `reference.qmd` and this log updated.
- **LONG could be read as downloadable-as-filed.** `datasets/accounts.qmd` previously said LONG is
  "the full-fact archive: every tagged concept as filed", which implies the raw archive (names,
  addresses, director loans) is the download. Reworded in four places (summary, table row, a new
  callout, the Kaggle block) to state plainly that the published LONG is the personal-data-removed
  subset and the full archive is never published.
- **Citations to gitignored `kaggle*/` files.** The `kaggle/`, `kaggle-long/`, `kaggle-v2/`,
  `kaggle-long-v2/` directories are gitignored (per the root `.gitignore`), so `Source:
  kaggle-v2/column-dictionary.md`/`README.md` citations and the `reference.qmd` blob link pointed
  at files not in the published repo — a `blob/main` 404 and a breach of "every number from a named
  repo file". Re-sourced to tracked docs: row counts → `docs/accounts-wide-rebuild-verification.md`
  (exact `33,513,017`/`36,710,673`); restatement → `docs/accounts-validation-summary.md`; creditors
  and employees → `docs/accounts-limitations.md` + the respective reconciliation/cut-off docs; LONG
  filter → `docs/accounts-public-long-concepts.md`. The per-column coverage percentages exist only
  in the pipeline-generated `column-dictionary.md` that ships with the Kaggle dataset — kept, but
  now attributed as generated-and-shipped-with-the-dataset (not a git-tracked repo file), not
  presented as repo-sourced.

### Verification done this round, and its limits

- **Figures spot-checked against sources** (not self-reported): size thresholds and the 2025/2028
  dates against `docs/source-material/accounts-explainer.html`; the 205/174 ONS sample, 164 repeats,
  99-of-107 creditors, and all commercial prices against `companies-house-accounts-notes.md`; the
  dataset/validation figures (`33,513,017`/`36,710,673`, 9.36%, 0.65 ms, 99.999%, 61,085, 273,418,
  35,806,258, 80.3%) and PSC figures (15,952,486, 10,917,257, 28.8%) against their tracked docs —
  all present.
- **Confidence-label semantics made explicit** on the Home page: `[Checked]` is either a project
  measurement (tagged as such) or an official source whose confidence the label *inherits* — not an
  independent re-verification by the site. This matters because many `[Checked]` figures were taken
  from the deck notes at the deck's stated (High) confidence.
- **Limits of the checks run here (for the maintainer):** the link check validated only
  repo-*internal* targets and in-page anchors on rendered `<a href>`. **External URLs were not
  fetched** (CH Guide, Open Ownership, Kaggle, GitHub blob targets) — run `lychee docs/site/_site`
  (or `quarto`'s link checker) **after merging to main**, since the `blob/main` links and
  `docs/site/_CHANGES.md` only resolve once this branch is on main. The Kaggle dataset URLs are
  placeholders and will 404 until the datasets are published. Image/asset `src` were scanned
  (0 local assets; the pages have no images), but this is only relevant if images are added later.

## Handoff 00 — status reconciliation (2026-10-02)

Read-only reconciliation of an October-2026 repo review against code and git history. Sole output:
`docs/status-2026-10.md` (no code/data/docs otherwise changed). Headline findings, each cited in
that file:

- **Validation run DID happen and the bug was fixed.** The first run exposed two defects —
  validation bypassed `score_all()`'s dissolved/closed exclusion gate and evaluated the whole cache
  rather than the sampled cohort — producing an invalid 500/501 (= 99.8%) headline. Fixed
  (`validation/evaluate.py:103-107`, `--positives` required) and covered by two tests
  (`tests/test_insolvency_validation.py:99`, `:130`). Corrected run: 298 excluded / 202 flagged / 0
  genuine misses; 100% conditional recall on the 202 screenable (`AUDIT.md:703-722`). TASKS.md and
  README are stale on this.
- **PSC bulk snapshot:** recon on `main`; downloader + Parquet loader with the `data_governance`
  switch and HMAC person-keys on the unmerged `feature/psc-loader` (Tasks A+B; C+D absent).
- **SIC section derivation exists** (`validation/labels.py:55`, reused by `control.py`); the "wrong
  column" bug was fixed by switching the label source to `sic07_2_digit`.
- **Accounts positioning is a real conflict** (plan.md/TASKS.md "out-of-scope/rejected" vs the
  built, Kaggle-published module) — flagged for the maintainer, not decided.
- **Accounts carry period dates + a month-resolution archive proxy, no per-filing filed/received
  date** (`extract.py:38-52`, `pivot.py:126-132`).
- **WIDE publication gates:** Creditors reconciliation, start-year recon and parser audit all done;
  only the Kaggle/OGL human approval remained open.
- Stale statements across TASKS.md/README/accounts-wide-columns.md/AUDIT narrative were **listed,
  not fixed**, per that handoff's acceptance criteria.

## Handoff 01 — point docs at the published Kaggle datasets (2026-10-02)

Text-only doc-sync so the docs reflect the live Kaggle datasets. No data regenerated, staged or
re-run; no extraction/pivot/guard executed.

- **Maintainer clarification (via `AskUserQuestion`).** The handoff left the Kaggle URLs as literal
  `<URL 1>`/`<URL 2>` placeholders and its "LONG is not published" line conflicted with the site.
  Resolved live: the WIDE URL is exactly the repo slug
  (`kaggle.com/datasets/thomassimm/uk-company-accounts-wide-2014-2026`), and **both** the WIDE and
  the personal-data-removed public LONG are published — the "LONG is not" line refers only to the
  full private as-filed archive.
- **`docs/site/datasets/accounts.qmd`** — replaced the "Kaggle links — publication pending /
  [Not verified]" callout with a live-links box (both published datasets, OGL v3). The slugs were
  already correct; the edit removed the pending/unverified framing.
- **`docs/site/datasets/accounts-validation.qmd`** — replaced the "Results pending" callout with the
  completed parser-check results, each with a `Source:` line, numbers taken from committed files
  only (99.999% / 119,812-of-119,813; 0.65 vs 7.7 vs ~992 ms; prefix-bug 61,085, comma-decimal
  1,096, hyphen-format 540, plain-XML 273,418; restatement 9.36% — `docs/accounts-parser-check.md`,
  `docs/accounts-validation-summary.md`).
- **`README.md`** — added an "Accounts dataset (bulk iXBRL)" section describing the
  `ukcompany-accounts` subsystem, linking both published datasets, and stating that both public
  tables are published under OGL v3 while the full as-filed archive (with personal data) is never
  published.
- **Task 4 — staging-guard record (reported, not acted on).** `kaggle_staging_guard.py` **ran and
  passed on the staged-for-upload directories**: `docs/accounts-kaggle-safety-checks.md:36`
  ("passed for both `kaggle/` and `kaggle-long/` as staged"), and re-run/passed on
  `kaggle-v2/`/`kaggle-long-v2/` (`AUDIT.md:1579`, `:1702`). The actual Kaggle **upload is a manual
  human step** ("human runs these; not run here", `AUDIT.md:1391-1400`); there is **no record of the
  guard running against the post-upload live files** — only the staged inputs (hard-linked to what
  was uploaded). The maintainer decides whether that gap matters.
- **Task 5 — Kaggle card (read-only).** Both dataset URLs return **HTTP 200** (browser UA), so the
  links are live, including the LONG slug taken from the repo. The card's **rendered content could
  not be verified from this environment**: Kaggle is a JS SPA (WebFetch 404s automated fetchers;
  curl returns only the login shell) and no `kaggle` CLI/credentials are available — nothing was
  installed. **NEEDS LIVE VERIFICATION by the maintainer:** (a) licence shows **OGL v3 with
  attribution** — note the staged `dataset-metadata.json` left `license` as `"other"` with OGL text
  embedded, flagged unresolved (`AUDIT.md:1384-1386`, `:1406`), so the live card may still read
  "Other"; (b) the WIDE card does **not** describe LONG as included (they are separate datasets);
  (c) coverage reads **2014-01 → 2026-08** (`docs/accounts-coverage.md`).
- **Assumption needing verification:** the LONG link uses the repo slug
  (`uk-company-accounts-long-2014-2026`); it returns 200, but the maintainer chose "both published"
  without pasting a distinct LONG URL.
- **Verification.** Quarto 1.9.36 rendered both changed pages (exit 0); the rendered HTML carries
  the live links and no longer contains "publication pending" or "Results pending". Link check: both
  Kaggle URLs HTTP 200.
- **Scope.** `docs/site/datasets/accounts.qmd`, `docs/site/datasets/accounts-validation.qmd`,
  `README.md` (text only), plus `docs/status-2026-10.md` (handoff 00) and this entry. No code, data,
  rules, severities, `FIELD_DOCS`, or generated docs (`rules.md`/`data-dictionary.md`) changed.
  Branch `handoff-00-status-reconcile`; nothing pushed or deployed.

## Handoff 04 — PSC ownership-structure features, attributes only (2026-10-02)

Turned the verbatim `psc_natures_of_control` string into structured per-company attributes.
**Attributes only: no new rules, no composite score.** No names or nationality are read or emitted.

- **Path decision (via `AskUserQuestion`).** Handoff 04 was on hold pending the Handoff 00 Q2/Q7
  finding that the unmerged `feature/psc-loader` (bulk loader, Tasks A+B) already decomposes
  natures and captures corporate reg numbers. Reported the overlap; the maintainer chose the
  **hybrid**: one shared nature-of-control mapping, consumed by the per-company derive path now and
  by the bulk loader when it merges.
- **New module `src/ukcompany/psc_natures.py`** (single source of truth): `decompose_nature`
  (strip entity-type suffix → read `N-to-M-percent` band → match core right), `summarise_natures`,
  `classify_kind`, `is_uk_company_number_format` (reuses `validate.normalise_company_number`).
  `NOC_SUFFIXES` mirror the bulk loader's four families; **align the loader's DuckDB `psc_noc` SQL
  to these constants when it merges** so the two paths keep one mapping.
- **`derive.derive_psc`** now emits (active records only): `psc_max_ownership_band`,
  `psc_max_voting_band`, `psc_has_appointment_rights`, `psc_has_significant_influence`,
  `psc_n_distinct_natures`, `psc_n_individual` / `_corporate` / `_legal_person` / `_super_secure`,
  `psc_corporate_reg_numbers` (verbatim; company identifiers, not personal data),
  `psc_n_corporate_uk_format_regno`, and `psc_unmapped_natures`. Not-fetched → `None` (unknown);
  cached 404 → the "absent" value (`0`/`None`/`False`), matching the existing PSC-field rule.
- **FIELD_DOCS**: 12 new entries added; `docs/data-dictionary.md` regenerated via
  `python -m ukcompany.cli data-dict` (not hand-edited).
- **Tests**: `tests/test_psc_natures.py` (synthetic only) — decomposition across band/suffix
  families, ROE "more-than" band (core mapped, band `None`), unmapped-core collection,
  `classify_kind`, UK-format check, and the derive-level features incl. active-only scoping, 404,
  and not-fetched.
- **Report**: `docs/psc-ownership-features.md` — code-coverage table, unmapped-code handling,
  corporate-PSC join rate, and the ECCTA-verification-as-rule options (A keep-as-attributes
  [recommended] / B info-flag / C medium-once-rollout-complete) — **implemented none**, per the
  constraint that ECCTA-as-rule is a maintainer decision.
- **Enumeration verified (correcting this session's own earlier error).** An earlier draft of this
  entry/report asserted natures were NOT in `psc_descriptions.yml` — wrong, and made without
  fetching the file. The authoritative list is that file's `description:` section (86 nature codes;
  `statement_description:` is the separate statement section). It was fetched (commit `0d3fb78`),
  the `description:` block vendored as `tests/fixtures/psc_descriptions_natures.yml`, and a test
  asserts all 86 decompose with **zero unmapped**. Fixes this surfaced: `decompose_nature` now
  strips the **longest** (compound) suffix, and recognises the `part-`/plain
  `right-to-share-surplus-assets` and `registered-owner-as-nominee` cores it previously dropped;
  ROE `more-than-25-percent` bands are captured but excluded from max-band ranking. No `-se`
  suffix exists. The 86 codes reduce to **7 cores / 24 suffix-stripped bases** — neither the "32"
  estimate nor the recon's "55 distinct base rights", so those counts use different definitions and
  must be reconciled before the bulk loader's `psc_noc` SQL and `psc_natures.py` merge (the loader
  also still lists only the four single suffixes and must adopt the compound set).
- **NEEDS LIVE VERIFICATION.** A real-cache census (codes seen in live data beyond the enumeration)
  still needs a run; `psc_unmapped_natures` collects it. The corporate-PSC join rate is not
  measurable from synthetic fixtures; the recon's 91.0%-carry-regno / 77.9%-resolve-to-live was
  measured against the **2026-08-01** register, ~7 weeks older than the 2026-09-18 PSC snapshot —
  label that staleness wherever published.
- **Verification.** Installed the `[dev]` extra (`pip install -e .[dev]` → ixbrlparse 0.11.2,
  duckdb 1.5.6, pyarrow) and ran the FULL suite — not relying on CI: `ruff check src tests` passes
  and `pytest` is **202 passed, 1 deselected** (the deselected one is the `@live` smoke test),
  including the new nature-decomposition and enumeration-coverage tests.
- **Scope.** `src/ukcompany/psc_natures.py` (new), `src/ukcompany/derive.py` (derive_psc +
  FIELD_DOCS + import), `tests/test_psc_natures.py` (new),
  `tests/fixtures/psc_descriptions_natures.yml` (new, vendored enumeration @ 0d3fb78),
  `docs/data-dictionary.md` (regenerated), `docs/psc-ownership-features.md` (new), this entry. No
  rules, severities, scoring, `docs/rules.md`, fetch or production scoring behaviour changed.

## PSC loader — Tasks A + B only (2026-09-25), branch `feature/psc-loader`

Per `docs/brief/psc-loader-and-page.md`, Tasks A (download/archive) and B (loader to
Parquet) only. C (`scripts/psc_checks.py`) and D (`docs/site/psc.qmd`) explicitly not
started. New package `src/ukcompany/psc/` (`download.py`, `manifest.py`, `loader.py`,
`cli.py`), entry point `ukcompany-psc`, `config/settings.yaml`'s new `psc:` section,
`tests/test_psc_download.py`, `tests/test_psc_loader.py`. ruff + full pytest suite green
(174 passed) throughout.

**Bugs found and fixed before any real-scale run:**
1. A SQL CTE-scoping bug (`_records_select_sql` assumed an "open" WITH-prefix from
   `_parsed_sql` that didn't exist) — fixed by giving `_parsed_sql` a proper closing
   `enriched AS (...) SELECT * FROM enriched` and having callers wrap it as
   `WITH src AS ({parsed}) SELECT ... FROM src`.
2. Report/reconciliation stats were originally going to be read back from the just-written
   Parquet, which is incomplete in `--data-governance` mode (drops `middle_name`, `raw`,
   etc.). Fixed by computing every report statistic from a fresh, always-full
   `_parsed_sql()` scan, independent of which mode is being persisted — `load_report.json`
   is aggregates-only either way, same standard as `docs/recon-psc-results.json`.
3. **Privacy bug**: `GOVERNANCE_DROPPED_COLUMNS` listed `postal_code_raw` but not
   `postcode_norm`, so the full normalised postcode (not just the outward code) survived
   into the "privacy-safe" governed output. Caught by manual schema inspection on a smoke
   test, not by an automated test (none existed yet). Fixed by adding `postcode_norm` to
   the drop list.
4. **Correctness bug**, found while writing `tests/test_psc_loader.py`'s governance test:
   `postcode_district` was extracted via a regex anchored on the *front* of the
   space-stripped `postcode_norm` (`^[A-Z]{1,2}[0-9][A-Z0-9]?`). Since UK inward codes are
   always exactly 3 characters, this greedily ate the inward code's leading digit too —
   e.g. `"SA1 1AA"` → `"SA11AA"` → wrongly extracted `"SA11"` instead of `"SA1"`. Fixed to
   `left(postcode_norm, length(postcode_norm) - 3)`, which is correct for every UK postcode
   length variant. Verified against real governed output (outward codes like `WN6`, `SS12`,
   `EH47`, `CV5` are all now correct).

**Memory cap.** The brief mandates every full-scale job run under
`systemd-run --user --scope -p MemoryMax=<N>G -p MemorySwapMax=0`, no exceptions. The
loader's own shipped default (`DEFAULT_MEMORY_LIMIT_GB = 8`, matching the accounts
pipeline's `ooc.py` convention) **OOM-killed within ~9 seconds** at a matching 8G cgroup
cap — this job's 13 GB of raw NDJSON text across 32 parts, read via `read_ndjson_objects`
with a `row_number() OVER (PARTITION BY filename)` window function, needs materially more
headroom than the accounts pivot job the 8G default was tuned for. Both real full loads
below were run at a 20G external cap / 16G internal `duckdb-memory-gb` instead, which held.
**`config/settings.yaml`'s `psc.duckdb_memory_gb: 8` and `loader.py`'s
`DEFAULT_MEMORY_LIMIT_GB` were left unchanged** — raising the shipped default is a
production-budget decision for T, not made here; anyone running `ukcompany-psc load` with
the shipped default on a full snapshot should expect the same OOM.

**Performance note.** Report statistics are computed via ~9 separate full re-parses of the
raw corpus (one per aggregate: line count, category counts, unknown kinds, company-number
mismatches, record-id dupes, psc_id cross-company sharing, middle-name fill, date flags,
plus the totals-line lookup) — a deliberate governance-safety tradeoff (point 2 above), not
an oversight, but it does make each full load slow (tens of minutes of CPU time at ~600%
utilisation on an 8-core machine for both runs below). Left as-is since Task B was already
complete; flagging as a real cost if this loader is scheduled to run daily.

**Real full-scale runs, 2026-09-18 snapshot (32 raw parts, 13 GB text, already extracted
locally, not downloaded by this agent):**
- `--no-data-governance` → `data/psc/2026-09-18/`
- `--data-governance` → `data/psc/2026-09-18-gov/` (separate directory, deliberately, since
  the loader's output filenames are fixed and running "both modes" as instructed would
  otherwise overwrite one mode's Parquet with the other's — T should decide which becomes
  the canonical `data/psc/2026-09-18/` output, or whether the `-gov` suffix convention
  should stick for dual-mode archival going forward)

Both runs produced byte-identical `load_report.json` statistics (expected, per point 2
above) and reconciled exactly against `docs/recon-psc-results.md` and the snapshot's own
totals line — see the chat summary delivered to the user for the full reconciliation table
and FLAG list. Governance-mode output verified clean on the real 15,952,486-row Parquet
(schema disjoint from `GOVERNANCE_DROPPED_COLUMNS`), not just the earlier smoke test.

**Live Task A run.** `ukcompany-psc fetch` was run live against
`https://download.companieshouse.gov.uk/en_pscdata.html` to get a real daily-zipped-size
figure (the brief's Task A FLAG item). Companies House only serves the *current* day's
snapshot (established previously in `docs/recon-psc.md`), so this necessarily downloaded
2026-09-25's snapshot (32 parts, 2,219,852,147 bytes total), not 2026-09-18's — there is no
way to fetch a past day's zips for direct measurement. Zips kept at
`~/Downloads/psc/2026-09-25/`, manifest at `data/psc/2026-09-25/manifest.json`.

**Assumptions not otherwise flagged inline:** `psc_id` for exemption records is the literal
string `"exemptions"` (the last path segment of `/company/<company>/exemptions`), not a
per-record identifier — exemption records are excluded from the
`psc_id_shared_across_companies` check for this reason. `raw` is fully dropped in
governance mode rather than rewritten in place (the brief allowed either). `person_key`
uses forename+surname+dob_year+dob_month only (matching `docs/recon-psc.md`'s base
definition), no NOC or company info folded in. `n_bad_lines` conflates "malformed JSON"
and "valid JSON with no `kind` field" into one count (both land in `category='unknown'`,
`kind IS NULL`) — not split into separate sub-counts.

## PSC loader — follow-up review (2026-09-25)

Eight follow-up items from reviewing the first pass above, all against the real 2026-09-18
snapshot. Both full loads re-run end to end after the code changes (private and governed);
both green, `ruff` and the full pytest suite (178 tests) green throughout.

**1. `f_ceased_out_of_range` (272) vs. the "97" figure in `docs/recon-psc.md`.** Re-derived
`docs/recon-psc-results.json`'s own `overall.ceased_on.years` histogram (the source recon
already wrote): summing every year outside [2016, 2026] in that histogram gives **272**,
matching the loader exactly — recon's own persisted output does not contain a 97 anywhere.
Independently recomputed recon's exact string-prefix definition (`ceased_on_raw[:4]`,
`isdigit`-filtered, outside [2016, 2026]) directly against `psc_records.parquet` and got
272 with zero row-level disagreement against the loader's `TRY_CAST`-based definition. The
"97" in `docs/recon-psc.md`'s prose does not match the JSON it's supposed to summarise and
is most likely a stale figure from an earlier, non-final recon pass — not a different
definition. Not corrected here (out of this brief's file scope); flagging for T to fix the
prose or re-derive it.

**2. Base rights: loader 54 vs. recon 55 — a NULL-handling artifact, not a vocabulary
difference.** At least one real record (`OE020203`, an overseas entity) has a literal JSON
`null` inside its `natures_of_control` array. recon's code stringifies every NOC value
(`str(noc)`), so that `null` becomes the 4-character string `"None"`, which survives
suffix-stripping as its own "base right" — recon's 55 includes this artifact. The loader's
`unnest` preserves it as a genuine SQL `NULL`; `COUNT(DISTINCT base_right)` correctly
excludes NULL per SQL semantics, giving 54. Confirmed exactly 2 raw `null` NOC entries exist
in the corpus (`psc_noc.parquet` has 2 rows with `base_right IS NULL`). Recomputing recon's
own vocabulary (`docs/recon-psc-results.json`'s 87-entry list) with the identical
suffix-stripping logic and removing the `"None"` artifact gives the same 54 real strings the
loader has — the two scripts agree completely once the artifact is set aside. Not fixed
(the `null` is genuine source data, not a bug to correct); both counts are legitimate under
their own counting rules.

**3. Written-output consistency check.** Added to `load_psc()`: after both COPY writes,
reads back `psc_records.parquet`'s per-category row counts and compares them against
`category_counts` (from the independent `stats` re-parse), and compares `psc_noc.parquet`'s
row count against an independently-derived expected count (`SUM(len(...))` over
`natures_of_control_json`, a different mechanism than the `unnest`-based write). Raises
`RuntimeError` on any mismatch. New `consistency_check` block in `load_report.json`. Passed
cleanly on both real re-runs (expected NOC rows = 35,169,887 = actual, both modes).

**4. Memory in the first 9 seconds.** `duckdb==1.5.3`; unconfigured defaults on this machine:
`threads=8` (= `nproc`), `memory_limit`/`max_memory`=24.7 GiB (~80% of 30 GB RAM),
**`preserve_insertion_order=True`**. The last one matters most: with it on (the default),
DuckDB must buffer completed-but-out-of-order result batches so they can be re-emitted in
original scan order, on top of the `row_number() OVER (PARTITION BY filename)` window
function's own per-partition materialisation — across 8 threads racing ahead on 32 files of
~400-490 MB uncompressed text each, both buffering mechanisms peak almost immediately at
pipeline start, before any hash-aggregate stage exists to spill from. That combination is
enough to cross an 8 GB buffer-manager cap in ~9 wall-clock seconds despite `SET
memory_limit='8GB'` being configured correctly. **Not changed**: `preserve_insertion_order`
is a strong candidate to set to `false` (row order in the output Parquet files is never
relied on), but per instruction the default memory limit and no other DuckDB settings were
touched this round — flagging both as tuning candidates for T.

**5. `postcode_district` now requires valid UK format.** Added `UK_POSTCODE_NORM_RE`
(mirrors `scripts/recon_psc.py`'s `POSTCODE_NORM_RE`, anchored for a full-string match) as a
gate before the last-3-characters slice; anything not matching (foreign addresses, free
text, partial data) now yields `NULL` instead of a plausible-looking but meaningless slice.
Real corpus: 14,861,207 postcodes present, 14,555,841 (97.9%) valid UK format, 305,366
(2.1%) invalid — new `postcode_format` block in `load_report.json`.

**6. `person_key_strict` (includes middle name).** New governance-mode-only column,
`person_key_strict_hmac(forename, middle_name, surname, dob_year, dob_month)`, all five
fields required non-NULL — so it's populated only for the ~53% of individuals with a
recorded middle name (real corpus: 7,365,820 of 13,887,210). Confirmed by test
(`test_person_key_strict_requires_middle_name`) and on the real governed output. The
existing "`data_governance=True` without a secret raises `ValueError`" guard fires before
either HMAC UDF is registered, so it already covered the new key with no code change needed
— reconfirmed by `test_data_governance_true_requires_a_secret` (unchanged, still passing).

**7. `n_bad_lines` split.** New `bad_line_reasons: {invalid_json, missing_kind}` in
`load_report.json` (`invalid_json` = the line never parsed as JSON at all; `missing_kind` =
parsed fine but no usable `kind`, e.g. no `data` object or `data` with no `kind`). Real
corpus: both zero (matches recon's "0 bad lines" — the split has nothing to show here, but
the plumbing is real and tested with synthetic fixtures of each kind).

**8. Canonical output paths.** Adopted `data/psc/<date>/private/` and
`data/psc/<date>/governed/` as the loader's actual default (`cli.py`'s `DEFAULTS` and
`config/settings.yaml`'s `psc.output_dir` both now `"data/psc/{date}/{mode}"`, filled in by
`cmd_load` from the `--data-governance` flag). This supersedes the ad hoc
`data/psc/2026-09-18-gov/` directory from the first pass — both real outputs were deleted
and regenerated fresh under the new convention, so there is no longer any output on disk
using the old naming.

Real numbers were otherwise unchanged from the first pass (all category counts, totals-line
reconciliation, NOC assertion count, date flags, middle-name fill) — the code changes above
added new checks and columns without altering any existing figure.

## PSC loader Stage-1 follow-up (2026-10-02), branch `feature/psc-loader`

Addresses the review of the Tasks A+B run. Branch rebased onto `main` (which now carries
`ukcompany.psc_natures` via the handoff 00/01/04 ff-merge); only `docs/AUDIT.md` conflicted on
rebase (both histories kept). Code changes verified with a FULL run over the 32-part 2026-09-18
snapshot (15,952,486 lines) at the **default 8 GB** limit; numbers below are from that run
(`data/psc/2026-09-18-stage1/load_report.json`, gitignored) plus a governed single-part check.
Synthetic fixtures only in tests; no personal data committed.

- **Item 1 — out-of-range ceased dates: 272 is correct; "97" was an error.** Two definitions:
  recon counts `ceased_on[:4]` digit-years outside [2016, 2026]; the loader's `f_ceased_out_of_range`
  `TRY_CAST`s `ceased_on` to DATE then flags `EXTRACT(year) < 2016 OR > snapshot year`. Recounting
  the **recon's own** `ceased_on.years` (recon-psc-results.json) sums to **272** (269 pre-2016 + 3
  post-2026: 2924/9998/9999); the full run's `f_ceased_out_of_range` is also **272**. They AGREE —
  no date-parsing bug. The "97" is not reproducible and is almost certainly **97485** (the 2016
  ceased count) mis-transcribed. Kept the loader definition; `docs/site/datasets/psc.qmd`'s "97"
  should be corrected to 272 (flagged, not changed here — site is re-scoped in Task D).
- **Item 2 — one nature mapping.** Deleted the loader's own `NOC_SUFFIXES`; `psc_noc`'s suffixes,
  cores and band pattern are now built in SQL from `ukcompany.psc_natures`
  (`SUFFIXES_LONGEST_FIRST`, `CORE_PREFIXES`/`CORE_EXACT`, `BAND_PATTERN`, made public). `psc_noc`
  now also emits `core`; suffixes strip longest-first (compounds whole), ROE `more-than` bands are
  captured (`NULLIF` so "no band" is NULL not ''). **Restatement (one definition, documented in
  load_report + `docs/psc-ownership-features.md`):** the snapshot's natures reduce to **86 distinct
  codes → 7 cores → 24 suffix-stripped bases**. The old "54 vs 55" was a definitional mismatch:
  recon strips a single suffix (compounds leave residue → more bases) while `psc_natures` strips
  the longest. **Item 2c — codes not in the vendored enumeration: NONE.** The 86 distinct codes in
  the snapshot are exactly the 86 in `tests/fixtures/psc_descriptions_natures.yml`; 0 in snapshot
  outside it, all 86 present, **0 unmapped real codes**. (Data-quality note: 2 NULL array elements
  in 2 records' `natures_of_control` → `noc_unmapped_codes = {"null": 2}`.)
- **Item 3 — check the written files.** The run reads back each Parquet: `psc_records` category
  counts vs the independent re-parse (equal), and `psc_noc` row count **35,169,887** vs the
  array-length expectation (equal — and matching the recon's assertion total exactly). Added a
  governed-mode assertion that the on-disk `psc_records` schema shares **zero** columns with
  `GOVERNANCE_DROPPED_COLUMNS`; verified on a real governed part (0 personal columns on disk).
- **Item 4 — memory.** Root cause was DuckDB's default `preserve_insertion_order = true`: the
  ~16M-row records COPY buffered the whole result in input order, blowing the 8 GB cap in the first
  seconds (the first thing the run does is that COPY). Fix = `SET preserve_insertion_order = false`
  in `_connect` (stream + spill to `temp_directory`), **not** a higher limit. The full run now
  completes **at 8 GB in 562 s**, writing a 3.76 GB `psc_records.parquet` and 441 MB
  `psc_noc.parquet`. Settings surfaced in `load_report.duckdb_settings`.
- **Item 5 — postcode district.** Already validated against `UK_POSTCODE_NORM_RE` before deriving a
  district (district NULL when invalid). Full run: 14,861,207 present, 14,555,841 valid UK format,
  **305,366 invalid** (district nulled).
- **Item 6 — person keys.** Baseline HMAC (forename, surname, dob year+month) and a strict key that
  also includes `middle_name`, both computed at load time before names are dropped. Secret read
  from `PSC_PERSON_KEY_SECRET` (`.env`); the loader and CLI **raise** when it is missing in governed
  mode — no default fallback (verified). Governed single-part check: person_key eligible
  461,687/461,706 individuals, strict 250,335 (~54%, those with a recorded middle name).
- **Item 7 — bad_lines split.** `bad_line_reasons` = `{invalid_json, missing_kind}`; full run both
  0 (n_bad_lines 0; categories sum to lines).
- **Item 8 (optional) — not done.** Stats are still gathered in ~10 re-parses of the NDJSON (562 s
  total is acceptable); consolidating into one pass is left as a non-urgent optimisation.

Verification: `ruff check src tests` passes; `pytest` **220 passed, 1 deselected** (the `@live`
smoke test) with the `[dev]` extra installed. New test
`tests/test_psc_loader.py::test_noc_core_compound_suffix_and_unmapped_via_shared_mapping`. Scope:
`src/ukcompany/psc/loader.py`, `src/ukcompany/psc_natures.py` (constants made public),
`tests/test_psc_loader.py`, this entry. **Task C (Stage 2) not started — awaiting maintainer review
of these numbers.** Nothing pushed.

## PSC loader Stage-1 — correction & postcode addendum (2026-10-02)

A correction to the entry above (left intact, not edited):

- **Person-key eligibility was quoted from the 1-part governed check, not the full snapshot.**
  The entry's "person_key eligible 461,687/461,706, strict 250,335" are the figures for part 1
  only. Over the **full** 15.9M-line snapshot (`data/psc/2026-09-18-stage1/load_report.json`):
  individual-kind records **13,887,210**; baseline-key-eligible (forename+surname+DOB year+month
  all present) **13,886,736** (99.997% — only 474 fail: 110 missing a name element, 385 missing
  DOB month/year); middle name present **7,365,984** (53.0%); strict-key-eligible **7,365,820**
  (53.0%). "Eligible" = an individual record able to form the key. The strict key's ~53% coverage
  is a **non-random** subset (middle-name recording correlates with vintage/registrar practice).
- **Invalid postcodes where the country is a UK variant: 3,990** of the 305,366 invalid-UK-format
  postcodes. Breakdown: United Kingdom 2,494, England 1,316, Scotland 105, Northern Ireland 40,
  Wales 31, UK 2, Cymru 1, Great Britain 1. (The regex-adjacent "Ireland" = 4,498 is the Republic
  of Ireland, a separate country, excluded from the UK-variant count.) These ~3,990 are UK-address
  records whose postcode fails UK format, so `postcode_district` is nulled — the only subset where
  a nulled district reflects a malformed UK postcode rather than a correctly-excluded foreign one.

## PSC loader Task C — companies-per-person usability (2026-10-02)

Focused Task C from the brief: is "companies per person" usable given no stable person ID? Full
report (with pre-registered usability criteria written **before** computing):
`docs/psc-checks-results.md`. Computed over the gitignored full-snapshot load joined to the
2026-09-01 register; aggregates only, no individual-level output committed. Keys: baseline =
forename+surname+DOB(y,m); strict = baseline + middle name (~53% coverage, non-random).

- **Baseline→strict split (detectable splits only):** 2.07% of baseline keys (4.91% of records, the
  relevant record-weighted figure) show a detectable split — an upper bound on *detectable* splits,
  NOT a bound on all collisions (it cannot see collisions among the ~47% with no middle name, or
  where both share a middle name).
- **companies-per-person by name-frequency band:** even the rarest band (unique name) shows a
  genuine tail (its most-connected keys reach ≥1,000 companies; 0.30% on ≥11 companies) — real
  multi-directorship, not purely a common-name artifact. But the ≥11 rate rises with name commonness
  (0.30→1.34% across baseline bands) and the strict key flattens it (0.28→0.53%) and lowers the
  common-name-band maxima (all ≥1,000) — part of the baseline tail is collision the middle name
  resolves. (Single-key maximum values scrubbed — see the 2026-10-02 scrub entry below.)
- **High-count tail (≥11 companies):** 38,343 baseline tail keys (~35% unique-name/genuine), halved
  to 18,068 under the strict key. Of the 659,653 companies linked to the tail, **51.1% are
  unmatched in the live register (dissolved/removed)**, 46.2% Private Limited — "ever" counts are
  dominated by dissolved shells, so an active-only variant is the more defensible feature.
- **Verdict (against the pre-registered rule):** usable as a documented **attribute** — never a
  rule, never a clean identity — carrying its name-frequency band, a match-confidence caveat (2.07%
  keys / 4.91% records show a detectable split — not a total-collision bound; strict key = higher
  precision at ~53% recall), and active-only vs ever.

Deliverable `docs/psc-checks-results.md` (new). No code changed in Task C. Stopping for maintainer
review before any build on top of this. Nothing pushed.

## CI dependency fix — DuckDB Python UDFs (2026-10-02)

GitHub Actions failed four PSC loader tests because the PSC data-governance path
registers Python scalar UDFs with DuckDB, which requires NumPy; the CI `dev`
extra installed DuckDB but not NumPy. Added `numpy>=1.24` to the `dev` extra so
the existing `pip install -e .[dev]` CI setup provides that runtime dependency.
The Node.js and Ubuntu runner annotations were informational and unrelated to
the test failure. Ruff and all 220 selected tests pass locally in `env1` (Python
3.14); a rerun in GitHub Actions is still needed to confirm the fix on Python
3.11.

## Scrub single-key maxima from the PSC companies-per-person tables (2026-10-02)

Removed the per-band **maximum** companies-per-person values from `docs/psc-checks-results.md` (both
the baseline and strict tables, and the §2 prose) and from the Task C AUDIT entry above, replacing
them with banded statements (`≥1,000`, `100–999`). The maxima — chiefly the rarest-name band's
**single-key** maximum — point at one person via the public register (a unique-name key on a very
large number of companies is effectively identifiable), so even a per-band count with no name is a
re-identification risk. Band percentages, medians and p90/p99 (distributional over hundreds of
thousands of keys) are retained; only the single-key maximum column is banded.

**Already-pushed note.** These values were already on `origin/main` (merged via PR #9), so this is a
**forward** scrub: the current files no longer carry them, but they remain in git history. Public
history is **not** rewritten — a no-name per-band count is a low-severity exposure and force-pushing
`main` would cause more trouble than it prevents. Scrub committed on `main` (not pushed);
`feature/psc-site-page` is rebased onto it. The site page and its CSVs never contained the maxima.

## Public accounts LONG withdrawn from Kaggle; WIDE confirmed clean (2026-10-03)

Branch `fix/withdraw-public-long`, text-only, not pushed.

**Timeline.** The per-fact accounts **LONG** table was published on Kaggle (made public on
**2026-10-02**; to be confirmed) and **deleted on 2026-10-03** after a read-only dimension check on
the published v2 LONG. Download/view counts at deletion: **not provided** (add here if available).

**Leak finding (aggregate; from the dimension check over the v2 public LONG,
`data/accounts/v2/kaggle-long-src/*.parquet`).** Facts whose `dimension`/`member` matched
Officer/Director/RelatedPart/KeyManagement/Trustee: **411,338 facts**, **23 distinct concepts (all
numeric), all 23 outside the 95-concept numeric denylist**, across **44,225 companies**. These are
related-party / key-management amounts (balances and loans owed to/by related parties, payments,
income from related parties, and the increase/decrease variants) carried on dimensional **members**
(e.g. `KeyManagementPersonnel`, `OtherRelatedParties`, `Associate1`). The concept-level denylist
missed them because the person/related context lives in the member, not the concept name — in a
single-director company a "loan owed to key management personnel" is effectively a per-person amount.
This is why LONG was withdrawn.

**WIDE confirmed unaffected (read-only).** Every WIDE value comes from either a dimensionless fact
(the nine total concepts) or one of the four reviewed `(concept, dimension, member)` members
(`Equity`×`EquityClassesDimension`×{`ShareCapital`,`RetainedEarningsAccumulatedLosses`};
`Creditors`×`MaturitiesOrExpirationPeriodsDimension`×{`WithinOneYear`,`AfterOneYear`}). The pivot
(`accounts/pivot.py`) admits totals only where `dimension IS NULL` and members only via an inner
join on those four triples, so no related-party / officer / director / key-management context can
enter. Confirmed the built WIDE schema: the 9 totals + 4 members + housekeeping columns only, **no
related-party/officer/director/key-management columns**.

**Site/README reworded (part 2).** Removed every claim that the public LONG is published and the
LONG Kaggle link, stating it is **withdrawn pending a dimension-aware filter** (no leak detail on the
site): `docs/site/datasets/accounts.qmd` (title, summary + withdrawal callout, the-tables section,
limitations, licence, Kaggle box), `README.md` accounts section, `docs/site/guide/sources-map.qmd`,
`docs/site/index.qmd`, `docs/site/guide/accounts-data.qmd`, `docs/site/_quarto.yml` nav. (The
`docs/site/_CHANGES.md` row is a historical changelog, left as-is.)

**v3 parked — design noted (not built).** (a) **Dimension allowlist**: admit a fact only if it is
dimensionless or its `(dimension, member)` is on a reviewed allowlist (the maturity and
equity-class members WIDE uses); drop all other dimensional contexts (related-party, officer,
director, key-management, trustee). (b) **Denylist the 23 concepts, including their non-dimensional
totals**, so even the dimensionless version of a related-party concept is dropped. (c) **Dimension-
aware staging guard**: `scripts/kaggle_staging_guard.py` currently scans concepts only; extend it to
scan `dimension`/`member` and fail on the person/related-party families. Rebuild and re-publish LONG
only after the guard passes dimension-aware. Render + link check run; nothing pushed.

## CI dependency for PSC feature tests (2026-10-04)

The PSC feature module imports pandas, and `tests/test_psc_features.py` exercises
DuckDB's pandas-backed `.df()` result. Added `pandas>=2.0` to the `dev` extra so
the GitHub Actions `pip install -e .[dev]` step installs it before test collection.

## Handoff 08 — per-company features from the basic-company snapshot (2026-10-04)

Produced per-company features for every live company from the monthly basic-company bulk file,
mirroring the PSC pattern (one definition, parity, coverage, governed/ungoverned tiers). Branch
`feature/snapshot-features` off main. Snapshot: **2026-08** (2026-08-01 reference date).

**Task 1 — refresh (`ukcompany-snapshot refresh`, new `snapshot/cli.py`, `snapshot/archive.py`).**
Added checksum verification against the manifest, a retention policy (first snapshot of each month
+ latest; a near-no-op at monthly cadence, implemented + tested for symmetry with PSC), and a
one-shot refresh that downloads, verifies, prunes, loads and reconciles the row count against the
manifest, failing loudly on any mismatch. New `ukcompany-snapshot` entry point; `snapshot:` block
in settings.yaml. Run on the existing 2026-08 archive (`--skip-download --prune-dry-run`):
checksums verified, **5,695,466 rows** reconciled against the manifest, ~2 s, ~0.9 GB.

**Task 2 — features (`snapshot/features.py`, `ukcompany-snapshot features`).** 5,695,465 companies
(one malformed line dropped by DuckDB's `ignore_errors`; the manifest/refresh count uses the same
Polars method and reconciles exactly). One definition: `_months_between` for age and
`sic_section_from_code` for SIC sections are reused (applied over distinct values, joined back) —
no second implementation. Features: status/type/age (age against the snapshot date); SIC sections,
code count, and three SEPARATE flags (dormant 99999, non-trading 74990, n.e.c.); previous-name
count (capped at 10 = "10 or more"); charge counts (total/outstanding/part-satisfied/satisfied);
accounts category, accounts/confirmation overdue (computed vs snapshot date), never-filed;
registered-office concentration. The n.e.c. list (`NEC_SIC_CODES`, 38 codes) is one constant
enumerated from SIC-2007 condensed-list "n.e.c." descriptions (ONS UK SIC 2007), a malformed
4-digit `9305` excluded. Two tiers via `data_governance`: governed (22 cols, no exact-address),
ungoverned (23 cols, adds `n_companies_same_address`); written-schema assertion enforces the drop.
Each tier built in ~1.5 min at ~4.8 GB. Address normalisation is one function
(`normalise_address`); the count is insensitive to it (2,634,652 distinct addresses standard vs
2,633,802 loose, a 0.03% shift).

**Task 3 — parity (`scripts/snapshot_parity_check.py`, `docs/snapshot-parity-2026-08.md`).** 714
companies in both the API cache and the snapshot. `has_charges` 100%; `date_of_creation`/
`age_months` 99.3%; `n_previous_names` 96.5%, `sic_sections` 96.8%, overdue flags 97.2–97.5%. All
96 disagreements have the API cache newer than the snapshot (fetched 2026-08-07 vs 2026-08-01) —
consistent with change in that window. The 5 `date_of_creation` disagreements are all Charitable
Incorporated Organisations (CE/CS-prefixed): the API omits `date_of_creation` for CIOs while the
bulk records it — a source field-availability difference, not a parsing error (carries into
`age_months`). `company_status`/`company_type` use different vocabularies (register category vs API
slug) and are reported as cross-tabs, not equality-compared.

**Task 4 — distributions (`scripts/snapshot_distributions.py`,
`docs/snapshot-distributions-2026-08.md`).** Fill rates per feature (core fields 100%;
accounts_next_due 96.97%, confirmation 98.64%); registered-office concentration as percentiles and
banded company counts (postcode median shared by ~17; 37% of companies alone at their exact
address; the tail is formation agents — the largest postcode alone exceeds 1% of all companies);
SIC/accounts flag shares.

**Docs/tests.** FIELD_DOCS entries added for the 14 snapshot-new attributes; data dictionary
regenerated. `docs/snapshot-features.md` documents the table. Synthetic-fixture tests
(`tests/test_snapshot_archive.py`, `tests/test_snapshot_features.py`) cover the archive functions,
feature values, both tiers, and parity vs derive_profile. All tests + ruff green. `data/` outputs
gitignored.

**Rule not verified.** The 21-month first-accounts deadline used by `accounts_never_filed` is NOT
VERIFIED against current CH guidance in this build (no network); labelled inferred in FIELD_DOCS
and the feature doc.

**No judgement-layer change.** No rules, severities, SOLVENT_CASE_TYPES, EXCLUDED_STATUSES or
composite score added. Attributes only.

## Handoff 08 follow-up — bad-line handling, CH-deadline never-filed, latest refresh (2026-10-05)

Three maintainer-requested fixes on `feature/snapshot-features`.

**(1) The "dropped malformed line" — identified; no real company lost; no silent drops.** DuckDB's
strict parse of the 2026-08 snapshot yields 5,695,465 records with **zero** parse rejects; the
1-row gap vs the manifest's Polars count (5,695,466) is a single **blank line in part 4**
(line 454677), confirmed against Python's `csv` reader. Company **09056746**'s
`PreviousName_10.CompanyName` contains a quoted embedded newline that parses correctly as one
record (not a bad line). So there is no malformed company row and no CSV option to fix. Hardened
the feature build against *silent* drops regardless: it reads with `ignore_errors` (one stray row
never aborts a multi-GB load) and then **reconciles** the loaded company count against an
independent full count from the Polars loader (which counts every physical record). The difference
(`n_rows_not_loaded`) is reported, written to `unloaded_rows_report.json`, and the build **fails**
above `SNAPSHOT_MAX_BAD_ROWS` (1000). For 2026-08 it is 1 (the blank line). Column names are taken
from DuckDB's own schema (`SELECT * ... LIMIT 0`), which strips the file's leading-whitespace
headers. Synthetic tests cover the reconciliation (an empty-field row is counted, not silent) and
the threshold (fails when exceeded).

**(2) never-filed rule replaced with CH's computed deadline.** `accounts_never_filed` is now
`AccountCategory = 'NO ACCOUNTS FILED' AND Accounts.NextDueDate < snapshot_date` — CH's own
next-due date, which already handles the PLC 18-month deadline, the 3-months-from-ARD alternative,
ARD changes and extensions. Old vs new on 2026-08: the inferred "incorporation + 21 months" rule
flagged **225,955 (3.97%)**; the CH-deadline rule flags **64,981 (1.14%)** — 160,974 of the old
hits were companies whose CH deadline had not actually passed. FIELD_DOCS updated (new source +
definition, NOT-VERIFIED label removed); data dictionary regenerated. `FIRST_ACCOUNTS_DEADLINE_MONTHS`
removed.

**(3) August confirmed, latest snapshot refreshed.** August was chosen because all 1,013 API
profile caches were fetched in 2026-08 (2026-08-07) and the on-disk snapshot is 2026-08-01, so the
parity test compares like with like. Ran `ukcompany-snapshot refresh` on the latest published
month: **2026-10** (2026-10-01), 7 parts downloaded (~2.7 GB), checksums verified, retention kept
both 2026-08 and 2026-10 (2026-08 retained for the parity alignment), **5,704,712 rows** loaded and
reconciled against the manifest, 49 s. The feature table remains built on 2026-08 for the API-cache
parity; the 2026-10 refresh demonstrates the repeatable pipeline on fresh data.

Both feature tiers rebuilt on 2026-08 under the new code (5,695,465 companies each; 1 row not
loaded, surfaced). All 243 tests + ruff green. `data/` outputs gitignored.

## Handoff 08 follow-up 2 — blank/malformed separation, deadline audit, 2026-10 build (2026-10-05)

**(1) Blanks separated from malformed; store_rejects confirmed working in DuckDB 1.5.6.**
`store_rejects=true` DOES work in 1.5.6 - but only on a *materialised* read (`CREATE TABLE AS
SELECT`, not `COUNT(*)`, which the optimiser strips). The feature build now reads with
`store_rejects` (plus a pinned dialect and `ignore_errors`); malformed rows (MISSING / TOO MANY
COLUMNS) are captured per line in `reject_errors`, counted (`n_malformed_rows`), quarantined to
`malformed_rows.csv`, and the build FAILS if they exceed `SNAPSHOT_MAX_MALFORMED_ROWS` (5) - a
malformed row may be a real company, so the tolerance is tiny. BLANK lines are skipped by DuckDB
(not rejects), counted separately (`n_blank_or_other_rows`, via the Polars full-record count minus
companies minus malformed), and ALLOWED in any number. On 2026-08: 0 malformed, 1 blank. (Note:
`strict_mode=false` was tried and rejected - it silently dropped 9 valid rows from the real
2026-08 file by mis-handling quoted embedded newlines; the pinned dialect + materialised
store_rejects works without it.)

**(2) No other hand-built accounts-deadline logic.** Grep of src/ and scripts/ found only the
already-removed 21-month rule. Everything else uses CH's own computed values: `rules.py`
(`_accounts_overdue`/`_cs_overdue`) consumes the CH-computed `accounts_overdue`/
`confirmation_statement_overdue` booleans; `derive_profile` reads `next_accounts.overdue`/`due_on`
and `confirmation_statement.overdue`/`next_due` directly from the API. `ard_day`/`ard_month`/
`next_accounts_period_end` are captured (derive.py comment "phase-1.2 deadline reconstruction")
but that reconstruction is NOT implemented - flagged for whoever builds it to use CH's computed
deadline (or mark it inferred). No change made.

**(3) 2026-10 feature table built; 2026-08 kept.** Built both tiers for 2026-10 (2026-10-01):
5,704,711 companies each, 0 malformed, 1 blank. 2026-08 rebuilt under the final code (5,695,465
each, 0 malformed, 1 blank) and retained for the API-cache parity. Governed tiers carry no
exact-address column; ungoverned add it.

Tests: a mixed-line-ending bug in the synthetic-snapshot test helper (csv.DictWriter's default
\r\n vs appended \n) had been defeating DuckDB's newline sniffer; fixed by forcing \n. 10 snapshot
tests (incl. malformed-quarantine and threshold) + 244 total pass; ruff clean. docs/snapshot-
features.md updated. `data/` outputs gitignored.
