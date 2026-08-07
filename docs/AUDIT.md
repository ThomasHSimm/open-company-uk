# Audit log

Implementation notes and assumptions that need live verification against the
real Companies House API. Append-only.

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
