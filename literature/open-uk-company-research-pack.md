# Open UK Company — evidence-base prompt pack (single file)

This one file replaces the earlier nine-file pack. It contains the project context and
every prompt needed to build a checkable evidence register from company-register sources
(UK and non-UK datasets, tools/products, national registers, and documented uses).

It adapts the Open Road Risk literature-review discipline: keep source-derived evidence
separate from interpretation, keep *claimed / observed / measured* distinct, and never let
a plausible inference look source-grounded when it is not.

---

## 0. How to use this file

Attach or point the agent at **this whole file** for every task. Then tell it which task
you want. The agent must **use only the section for the current task**; the other sections
exist for other tasks and their rules must not bleed in (e.g. synthesis rules must not
change how a single source is extracted).

| Task | Use section |
|---|---|
| Extract one source into a structured record | §3 (pick body A/B/C/D by source type) |
| Add finished extraction(s) to the evidence register | §4 |
| Check an extraction against its source before trusting it | §5 |
| Answer a project question across finished extractions | §6 |
| Manual final check before accepting an extraction | §7 |

**Standing rules for every task**

- One source per extraction session. Do not extract two sources in one pass.
- If the source was not fully accessible, say so explicitly and mark unverifiable fields
  `Not verified`. Never produce a complete-looking extraction from a filename, an abstract,
  a truncated read or a partial page. A short access note is the correct output when the
  artefact is inaccessible.
- Unknown fields are `Not stated` (source is silent) or `Not verified` (could not be
  checked), never a guess.
- Cite exact evidence: page / table / figure / section for documents; **file path + line
  range + commit/tag** for repositories.
- Record an access date for any mutable claim (pricing, API limits, licence, live schema).
- Agreement between models or sources is not evidence. The source artefact is the evidence.

**Chat-agent / Codex limitation you cannot design away.** A chat or agent session has no
persistent register state. The register in §4 is a growing, append-only artefact. So the
working pattern is: the agent produces *per-source* extractions (§3), and the register
update (§4) is a separate task where **you supply the current register file** and the new
extraction(s) as inputs. An agent asked to "produce the whole register" from scratch will
either cover only the sources in that one session or invent structure across sources it has
not read. Keep register accumulation as its own step with the current register given.

---

## 1. Project dossier (canonical context — do not redefine)

An extraction or research agent must not silently broaden or redefine the project below.

### Positioning

Open UK Company is a proposed open, reproducible pipeline for analysing UK company-register
data and deriving **transparent company-status, compliance and ownership indicators**.

It is **not** a measure of trustworthiness, creditworthiness, solvency or fraud. Companies
House records can support due-diligence and data-quality signals, but the absence of a
recorded adverse event is weak and asymmetric evidence.

### Unit of analysis and v1 workflow

The v1 unit of analysis is a **supplied list of hundreds of UK company numbers**, not the
whole register.

```
company-number list
  -> fetch and cache current Companies House API resources
  -> derive structured company attributes
  -> derive documented indicators
  -> return attributes, indicators, exclusions and run metadata
```

The API path is preferred for freshness-sensitive current state. A monthly company snapshot
is a later population-context source (e.g. registered-address concentration, cohort
baselines); it must not silently overwrite current API values.

### Intended v1 sources

Core Companies House resources: company profile; status and status detail; accounts and
confirmation-statement metadata; registered-office dispute and undeliverable-address fields;
insolvency links/cases; charges links/resources; officers and appointments; filing history;
PSC and PSC statements; identity-verification fields where publicly exposed and properly
understood.

Later sources: monthly CH company snapshot; daily PSC snapshot; iXBRL accounts; The Gazette;
disqualified-director data; other UK registers and sanctions/enforcement sources; non-UK
company and beneficial-ownership registers; cross-border identifiers and aggregators.

### Intended outputs

Wide company attribute table; long indicator table (company number, rule id, severity/context
class, evidence fields, source, retrieval time, rule version); exclusion/status output for
dissolved/converted/closed/unsupported/failed inputs; fetch/data-quality report keeping
company state separate from pipeline failure; run manifest and raw replayable evidence cache;
later population features and cohort summaries from dated snapshots.

**No real officer-level or named-company indicator output is intended for publication.** The
public repo holds code, methodology, synthetic fixtures and aggregate demonstrations unless a
separate publication assessment supports more.

### Indicator direction

Candidate indicators/contexts: current formal insolvency or adverse status; active proposal
to strike off; overdue accounts; overdue confirmation statement; registered office in dispute;
undeliverable registered office; typed insolvency cases with event-level evidence; PSC
identification/completeness statements; company age as context; charges as context; later —
historical late filing, officer churn, address concentration, cohort-relative features.

Dissolved/converted/closed entities are statuses or exclusions, **not** automatically
high-risk indicators. Outstanding charges and young-company status are informational context.
A generic historical insolvency entry must not be assigned one severity without classifying
case type and current/concluded state.

### Evidence and interpretation guardrails

1. Use **registrar-recorded**, not **registrar-verified**, unless the specific fact is
   demonstrably part of an identity-verification process.
2. Separate raw register fields, official annotations, filings, identity verification, derived
   attributes and analytical indicators.
3. Preserve retrieval time, source release/snapshot date and event/effective date as different
   concepts.
4. Do not treat absence as evidence until coverage, applicability and successful retrieval are
   established.
5. Keep endpoint failure, unsupported company type and genuine company state separate.
6. Treat current API data as preferred for current-state screening, not as infallible.
7. Do not infer fraud, legitimacy, beneficial ownership or operational activity from a clean
   profile.
8. Do not use current or post-outcome fields as historical predictors without a valid
   time-indexed reconstruction.
9. Treat officer/person linkage as entity resolution with uncertainty; names alone are
   insufficient.
10. Keep vendor capabilities, observed use and measured effectiveness separate.

### Transferability rules

High transferability: implementable with the free Companies House API or bulk data, other
open official UK data, a supplied list of valid company numbers, standard Python/Polars/Parquet,
transparent deterministic transforms, and reproducible source/retrieval metadata.

Lower/mixed: requires paid proprietary company or credit data; private bank/transaction/tax/
payroll/customer data; large-scale manual document review; opaque vendor scores; full historical
register states not publicly available; high-confidence person matching without stable
identifiers; jurisdiction-specific data not mappable to UK concepts; publication of personal
data beyond the project's posture.

Decompose transferability — a method can transfer while its labels, input data or claimed
performance do not.

### Technical constraints

Python + Polars for population-scale parsing, Parquet outputs; API responses cached with
retrieval metadata (rescoring must not need network access); company numbers stay validated
strings preserving leading zeros/prefixes; API credentials as environment variables only; no
live API calls in CI (synthetic fixtures + optional manual smoke tests); no LLM in the
deterministic bulk/batch path.

### Scope boundary (out of scope for v1)

Composite trust/fraud/credit scoring; iXBRL/financial-statement parsing; fuzzy
name-to-number resolution; officer network graphs; non-UK production ingestion; public
publication of named company/officer results; LLM-generated indicator decisions. Research may
examine these to map the landscape, but recommendations must label them **future work**, not
silently expand v1.

---

## 2. Shared conventions (used by every prompt below)

### Evidence-role vocabulary

Label each material claim as exactly one of:

- `official-definition` — official registry/law/source documentation establishes it.
- `capability` — inspectable code or documentation shows the function exists.
- `claimed` — the provider/author says it exists or works.
- `observed` — a documented user/case demonstrates use in practice.
- `measured` — a defined evaluation reports an outcome with method.
- `interpretive` — reasoned analysis, not direct evaluation.
- `not-applicable`.

Source *quality* is a separate axis. An official product page is high-quality evidence for
product features but only `claimed` evidence for effectiveness.

### Distinctions to preserve in any source

- data filed by a company vs generated/annotated by the registrar;
- registrar-recorded vs identity-verified;
- current state vs historic event; event/effective date vs snapshot date vs retrieval time;
- no record vs not applicable vs inaccessible vs fetch failure;
- individual search vs programmatic API vs true bulk access;
- free viewing vs free reuse/export/API access;
- provider capability vs observed use vs measured effectiveness;
- direct register fields vs values derived by this project;
- a selected/investigated sample vs a representative population.

### Action discipline (least-disruptive useful action)

Recommend the *lowest* sufficient rung, never higher than the evidence supports:

1. source/documentation note → 2. schema/data-dictionary update → 3. test fixture or
data-quality check → 4. diagnostic → 5. small pilot → 6. comparison with a simple baseline →
7. candidate contextual attribute → 8. candidate indicator → 9. production indicator / workflow
change.

Do not recommend a production indicator from one paper, product or anecdote. If a
field/method already exists in the plan, recommend testing/documenting/refining it, not
"adding" it again. Never recommend a composite trust/risk score.

### Delivery and honesty rules

- Cite exact source locations (page/table/section, or repo path + line range + commit/tag).
- Record access dates for mutable claims; do not claim a live endpoint was tested unless it
  was actually called.
- Prefer a sparse accurate record over a complete-looking speculative one.
- Do not add general literature-review prose before or after an extraction.
- If file creation is available, write the extraction to the path given in the task and
  present it; otherwise return raw Markdown in one copy-safe block.

---

## 3. Source extraction prompt (one prompt, four bodies)

**Role.** You are extracting evidence from **one** source for Open UK Company. Read §1
(dossier) and §2 (conventions) first. Do not write a generic description of the source or its
organisation. Prefer `Not stated` / `Not verified` over inference.

**Pick the body by source type:**

- Official dataset / API / bulk product / delta feed / document corpus / register → **§3A**
- Open-source, free, freemium or commercial tool/product → **§3B**
- A non-UK company-register ecosystem (one jurisdiction) → **§3C**
- Paper / report / investigation / case study / applied repository / evaluation → **§3D**

Every body uses the **shared metadata block** first and the **shared closing block** last.

### Shared metadata block (all bodies)

- Extraction date; reviewer tool/model if visible.
- Source / product / paper name; operator or authors; jurisdiction(s).
- Exact URL(s), file(s), repository + commit/tag reviewed; version/release/snapshot date.
- Input type: PDF / HTML / repository / dataset / pasted text / abstract-only / other.
- Was the full source accessible? yes / no / uncertain — and what was *not* accessible.
- Suggested output filename (see closing block).

---

### §3A — Official data source

1. **Authority and purpose.** Statutory role of operator; purpose of *this specific* product;
   population covered; explicit exclusions; unit of each record; whether the source is
   definitive, a filing channel, a publication layer, an index or a secondary compilation.
   Do not call content "verified" unless the docs define the verification performed.
2. **Access routes.** Table: route | endpoint/URL | individual/batch/bulk | auth | cost |
   rate/volume limit | refresh | historical access | automation stated? | evidence. Then
   answer: suitable for fresh list-level screening? for population context? reproducibly
   downloadable? is "free" viewing-only or does it include API/bulk/export/reuse? what
   happens when records change or disappear?
3. **Coverage and time semantics.** Earliest coverage; officially stated+dated population
   size; entity/company types; dissolved/historic included?; update cadence; publication lag;
   snapshot compile date vs release date; event/effective dates; how corrections/deletions/
   redactions appear; retained historical snapshots/deltas; known structural breaks/reforms.
4. **Identifiers and linkage.** Table: identifier | entity | stable? | format | reuse across
   products | cross-border mapping | leading-zero/prefix risk | evidence. Do not describe name
   matching as stable linkage.
5. **Field inventory** (project-relevant fields only; group nested resources, preserve exact
   names/paths). Table: field/path | type | resource | meaning stated by source |
   optional/required | current/historic | direct/derived-by-source | verification/filing status
   | project use | caveat. Flag deprecated fields, externally-maintained enumerations,
   company-type-specific fields, booleans where absence ≠ false, links that trigger further
   retrieval, and fields whose meaning is shifting under identity-verification/legal reform.
6. **Missingness, applicability and error states.** Table: situation | how represented |
   company state / lawful state / source limitation / pipeline failure? | safe interpretation |
   unsafe interpretation. Cover empty results, missing optional fields, unlinked endpoints,
   partial data, redacted/protected records, unsupported entity types, HTTP failures, stale
   snapshots.
7. **Data quality and verification limits.** Who supplies the data; documented validation/
   identity verification; what is only syntactically checked/filed/self-declared; registrar
   annotations/dispute mechanisms; official caveats; schema instability.
8. **Licensing, personal data and publication.** Licence/reuse basis; attribution; automation/
   redistribution terms; personal data present; suppression/redaction expectations; retention/
   purpose limits; whether raw or derived records could be republished under the project's
   posture; questions needing legal/DP review. Distinguish source licence from the project's
   obligations. Not legal advice.
9. **Reproducible acquisition design.** Least-fragile ingestion: recommended route; latest-
   release discovery; auth handling; pagination/delta/stream handling; conservative rate limit;
   retry/backoff; raw versioning + metadata; schema validation; checksums/ETags; resume/
   idempotency; storage estimate if measurable; test fixtures/edge cases; failure reporting.
   Separate evidence from implementation judgement.
10. **Canonical project mapping.** Table: source field/resource | proposed canonical attribute/
    event | transformation | retrieval timestamp | event/effective timestamp | evidence role |
    conflict rule | notes.
11. **Indicator support.** Table: candidate attribute/indicator | exact supporting fields/
    events | direct or derived | alternative explanations | missingness risk | temporal risk |
    appropriate status. Status ∈ {raw/context attribute, exclusion/status, data-quality
    diagnostic, small pilot, candidate indicator pending evidence, supported indicator,
    reject/defer}. Do not convert contextual fields into adverse indicators without evidence.

→ continue to **shared closing block**.

---

### §3B — Tool / product

Provider pages are primary evidence for *product claims and current commercial terms*, not
independent validation of outcomes. Do not infer underlying data, scoring rules or accuracy
from interface labels.

1. **Description.** What it is; main user problem; stated target users; current status/version;
   relationship to parent/other products. Brief and factual; note the evidence role of the
   description.
2. **Data-source claims.** Table: data source stated | official/private/user-supplied |
   jurisdiction | current/historical | raw/joined/derived | provenance exposed? | verified from
   source? | evidence. Then separate: sources explicitly named vs only implied vs proprietary vs
   user-supplied vs unverifiable. Do not write "Companies House plus other sources" without
   naming which other sources are actually stated.
3. **Capability map.** Table: capability | direct lookup/linkage/derived analysis? | web/UI |
   API | batch/export | evidence role | method transparency | source. Cover profile/status,
   officers/ownership, filings/accounts, charges/insolvency/notices, group structures/networks,
   matching, monitoring/alerts, KYB/AML/sanctions, risk/health indicators, search/name
   resolution, bulk/API/export, international coverage, provenance/audit trail — where
   applicable.
4. **Free / paid / access boundary.** Table: function/tier | public browsing | account
   required | free allowance | paid price/contract | API/export restriction | checked date/
   source. Record exact public prices; `Quote required` when quote-only (do not estimate);
   distinguish free trial from permanently free; distinguish individual lookup from usable
   batch/API; record rate/credit/record limits.
5. **Derived indicators / scores.** Table: output | stated meaning | inputs disclosed | method
   disclosed | validation disclosed | explainability/provenance | evidence role | main caveat.
   Answer: deterministic mapping of public fields, or opaque vendor score? any *measured*
   performance with sample/target/validation design? could the result be read more strongly
   than the evidence supports? Do not reverse-engineer a score from examples unless the source
   supports it.
6. **Open-source code quality** (public code only; else `Not applicable`). Repo + inspected
   commit/tag; licence; language/deps; API vs bulk pattern; storage/cache design; pagination/
   rate-limit handling; tests/CI; synthetic fixtures vs live tests; docs quality; last material
   activity; runnable without proprietary data?; personal-data handling; realistically reusable
   components; security/maintenance concerns. Do not infer quality from stars or a polished
   README.
7. **Evidence of real-world use/effectiveness.** Table: claim/use | claimed/observed/measured? |
   user/sample | outcome | comparator | validation | result | independent source? | limitation.
   Logos, testimonials and case-study prose are not measured validation unless methods and
   outcomes are stated.
8. **Value-add decomposition.** Table: value layer | evidence | replicable with open data? |
   effort for this project | main barrier. Layers: official-data access; cleaning/
   normalisation; historical state/change capture; entity resolution; cross-jurisdiction
   plumbing; proprietary data joins; derived analytics; interface/workflow/monitoring;
   compliance assurance/manual review. Do not assume the moat is an algorithm if the evidence
   points to data engineering, licensing, workflow or human operations.

→ continue to **shared closing block**.

---

### §3C — Non-UK register ecosystem (one jurisdiction)

One jurisdiction per review (or a tightly-related group with genuinely shared governance and
access). Current law/access/pricing must be checked against official registry/government/
legislative/EU sources; secondary guides aid discovery only. If current access cannot be
confirmed, write `Not verified`. Do not assume: one "business register" holds company +
officer + ownership + financial data; free web viewing implies API/bulk reuse; shareholder =
beneficial-owner data; basic data and legal filings share an identifier/operator; an EU rule
is implemented uniformly; a technically accessible page may lawfully be scraped; a field has a
direct UK equivalent.

1. **Institutional map.** Table: function | official operator | register/product | legal role |
   URL | evidence. Cover (where applicable) legal company register, statistical business
   register, beneficial-ownership register, securities/market filings, financial statements/
   central balance-sheet data, insolvency register, disqualified directors/enforcement, gazette/
   legal notices, national and cross-border identifiers.
2. **Entity and company-type coverage.** Entity types; sole traders/partnerships?; domestic vs
   foreign; active/dissolved/historical; branches; public/private distinction; important
   exclusions.
3. **Data-class availability.** Table: data class | available? | source/register | public
   detail | current/history | structured vs document-only | cost/access | main limitation |
   evidence. Classes: basic legal identity/status; registered address; industry/activity;
   officers; shareholders; beneficial owners; filings/history; financial statements; insolvency;
   charges; previous names; groups/parents/subsidiaries; identity verification; official
   annotations/disputes.
4. **Access and reuse.** Table: product/route | web search | API | bulk | delta/stream | auth |
   price | licence/reuse | refresh | historical access | evidence/access date. Distinguish free
   search, free machine-readable access, free reuse, paid document purchase, legitimate-interest/
   professional access, research/journalism exceptions, request-only bulk, and technical access
   with unclear reuse rights.
5. **Identifiers and cross-border linkage.** Table: identifier | entity | format | stable? |
   public? | maps to EUID/LEI/other? | available in bulk/API? | evidence. State the reliability
   limits of matching to UK companies/people. Do not recommend name-only linkage.
6. **Data assurance and legal meaning.** Who files each class; checks performed; identity
   verification (for whom); audited/notarised/validated vs merely registered; official
   disclaimer; how corrections/disputes/redactions/protected info are handled. Do not treat
   stricter filing law as proof all records are accurate.
7. **Ownership-access analysis** (dedicated — often differs from basic access). Shareholder
   data? beneficial-owner data? public/restricted/legitimate-interest/paid/unavailable? how
   natural persons, legal entities and control types are represented; historical ownership;
   machine-readable vs documents; relevant court decisions/legislation/deadlines; current
   practical access on the review date.
8. **Financial-data analysis.** Which entities must file accounts; XBRL/iXBRL vs PDF/image vs
   mixed; public/free/paid; coverage and exemptions; current vs historical; standard taxonomy/
   comparability; suitability for bulk analysis.
9. **Comparability with Companies House.** Table: UK concept/project need | closest local
   equivalent | direct/partial/no mapping | main semantic difference | access difference |
   project implication. Cover company number, status/detail, filing compliance, officers, PSC/
   beneficial ownership, insolvency, charges, address, accounts metadata, identity verification,
   historical change.
10. **Practical ingestion feasibility.** list-level lookups; population-scale ingest;
    incremental updates; document parsing; language/encoding; auth/session barriers; stable
    URLs/versioning; storage/engineering burden; existing open-source libraries. Use
    `high/medium/low/not verified` and explain.

→ continue to **shared closing block**.

---

### §3D — Use-case / paper / repository

Extract methodological and evidential metadata. Do not write an abstract. Separate what the
source *reports*, *demonstrates technically*, *observes in practice*, *measures*, and what you
*infer* about transferability. Do not infer that a feature predicts misconduct or failure
merely because it is common in an investigated sample.

1. **Citation and type.** Title; authors/org; year; DOI/stable URL; type (academic /
   official report / investigation / case study / applied repository / evaluation);
   peer-/formally-reviewed?; jurisdiction(s); funding/conflicts/provider relationship if
   stated.
2. **Objective and claim type.** One-sentence objective; main claim type (descriptive /
   investigative / predictive / causal / operational screening / methodological / technical
   capability); intended user or decision; evidence reference.
3. **Data sources.** Table: data source | operator/provider | jurisdiction | current/historical
   | access route | fields used | coverage/sample | main limitation | evidence. Distinguish
   company-register data from proprietary, transactional, enforcement, sanctions, web, survey or
   hand-labelled data.
4. **Unit, population, sampling.** Unit of analysis (company / company-year / filing / officer /
   person / address / network / transaction / case / jurisdiction); population; sampling frame;
   inclusion/exclusion; sample size; time period; active/dissolved/historic treatment; case-
   control/known-case/convenience selection; representativeness concerns.
5. **Entity resolution and linkage.** Company/person identifiers; join keys; name/address
   normalisation; fuzzy/probabilistic matching; thresholds and clerical review; precision/recall
   or match-quality evaluation; unmatched/ambiguous handling; cross-border linkage. Do not accept
   "matched by name" as reliable linkage without qualification.
6. **Target / outcome / endpoint.** Outcome or purpose; how constructed; ground-truth source;
   time between features and outcome; whether the outcome reuses the same registry fields;
   positive/negative class definition; prevalence/base rate; label noise/incompleteness. If
   descriptive/investigative with no outcome, say so.
7. **Fields / signals / features.** Table: field/signal | raw source | engineering | intended
   interpretation | alternative explanation | available to this project? | evidence. Only
   features actually used or explicitly proposed.
8. **Method.** Deterministic rules; statistical/ML/network methods; baseline/comparator;
   training design; temporal design; network construction; threshold selection; explainability;
   human review.
9. **Temporal validity / leakage audit.** Table: potential issue | present? | why | effect |
   evidence. Check specifically: current status predicting a past outcome; post-outcome filings/
   appointments; labels derived from the same adverse register events used as features;
   retrospective corrections; random splits across repeated companies/people/addresses; network
   leakage via shared entities; future information in a snapshot. Distinguish leakage from weaker
   external generalisation.
10. **Validation.** Train/test split; temporal holdout; grouped/entity holdout; geographic/
    jurisdiction holdout; external validation; baseline; metrics; calibration; threshold
    evaluation; false-positive analysis; subgroup/fairness; human-review comparison. Do not call
    in-sample fit predictive validation.
11. **Quantitative results.** Table: result type | metric | value | sample/subgroup | evaluation
    condition | interpretation supported | evidence. Then: are results in-sample / cross-
    validated / temporally held out / entity-held-out / externally validated / not stated? what
    base rate or comparator is needed? which results are likely optimistic? were uncertainty
    intervals/sensitivity analyses reported? If no evaluation exists, `Not stated` — do not
    construct one.
12. **Findings relevant to the project (3–6).** Each: finding; direct evidence or
    interpretation?; why it matters; scope limitation; evidence reference; confidence
    high/medium/low.

→ continue to **shared closing block**.

---

### Shared closing block (all bodies)

**Transferability assessment.** Assess components separately (use
`high/medium/low/mixed/not applicable`): research question; raw data; entity linkage; feature
engineering; method; outcome/label; validation design; operational/public use — with reason,
data availability, scale fit and adaptation required.

**What this source does NOT establish.** List claims a reader might be tempted to make that the
source does not support.

**Risk of false confidence from project context.** Where could knowing the Open UK Company
project make a plausible but unsupported inference look source-grounded?

**Unsupported details requiring checking.** Important details not verifiable from the supplied
artefact. If the full source was unavailable, state: *Not available without the full source
artefact.*

**Project actions.** Follow §2 action discipline. Table: action | type | why supported | phase
| effort | risk if done badly | confidence. Do not recommend a production indicator from one
selected-case investigation or opaque commercial evaluation.

**Register metadata (YAML).** Emit a compact block using only supported information; `not-stated`
where unknown; do not invent an ID (`register_id: pending`):

```yaml
register_id: pending
source_type:            # official-data | tool-product | country-register-review | use-case-evidence | governance | method
title:
authors_or_operator:
year_or_version:
jurisdiction: []
source_artifact:
extraction_file:
main_question:
evidence_role:          # official-definition | capability | claimed | observed | measured | interpretive | not-applicable
operational_proximity:  # capability | claimed | observed | measured | not-applicable
access_class:           # open-bulk | open-api | free-search | free-limited | paid | request-only | restricted | inaccessible | mixed
main_data_or_method:
outcome_or_purpose:
validation_type:        # none | in-sample | cross-validated | temporal | grouped-entity | external | case-evidence | not-stated | not-applicable
current_repo_relevance: # high | medium | low | none
future_research_relevance:
actionability_now:      # documentation | schema | test | diagnostic | pilot | baseline | candidate-indicator | production | none
supports_production_change: # yes | no | conditional
main_limit:
review_status:          # solid | conditional | needs-review | screening-only | rejected | inaccessible | superseded
secondary_review_needed:
reviewed_on:
recheck_by:
tags: []
notes:
```

**Delivery.** If file creation is available, write to
`research/extractions/<data-sources|tools|countries|use-cases>/` using a name like
`data-review-<short-name>-<YYYY>.md` / `tool-review-<short-name>-<YYYY>.md` /
`country-review-<jurisdiction>-<YYYY>.md` / `use-review-<author-or-org>-<year>-<short-title>.md`,
then present it. Otherwise return raw Markdown in one copy-safe block. No surrounding prose.

---

## 4. Evidence register — schema + update prompt

The detailed §3 extractions remain the evidence records. The register is a compact,
append-only inventory + routing layer: what has been read, what it establishes, how close it
is to observed/measured use, and where it affects the project.

### Inventory schema (one row per finished source)

`register_id` · `source_type` · `title` · `authors_or_operator` · `year_or_version` ·
`jurisdiction` · `source_artifact` · `extraction_file` · `main_question` · `evidence_role` ·
`operational_proximity` · `access_class` · `main_data_or_method` · `outcome_or_purpose` ·
`validation_type` · `current_repo_relevance` · `future_research_relevance` ·
`actionability_now` · `supports_production_change` · `main_limit` · `review_status` ·
`secondary_review_needed` · `reviewed_on` · `recheck_by` · `notes`.

ID prefixes: `DATA-` official dataset/API/register · `TOOL-` tool/product · `REG-` country
register review · `USE-` paper/report/investigation/repo · `GOV-` law/licence/governance ·
`METH-` general method/entity-resolution/validation. IDs identify register entries, not
universal claims.

Review-status semantics: `solid` (checked; reliable for its role) · `conditional` (usable with
an explicit caveat/small check) · `needs-review` (do not rely on without revisiting) ·
`screening-only` (not accessible enough for detailed extraction) · `rejected` (reviewed, not
suitable) · `inaccessible` (could not acquire/check) · `superseded` (access/schema/pricing/law
changed — preserve the old observation, link the replacement).

### Update prompt

> **Inputs (all required):** §1 dossier · the current evidence register file · one or more
> finished §3 extraction files.
>
> You are updating the Open UK Company evidence register from completed extractions. **The
> extraction files are the evidence for this task.** Do not re-research the web, reinterpret
> inaccessible material, or add claims from general knowledge.
>
> Tasks: (1) add one inventory row per extraction; (2) add thematic evidence only where an
> extraction directly supports it; (3) record negative evidence, non-transferable methods,
> important cautions; (4) add project actions only when supported by an extraction and
> consistent with the dossier; (5) update coverage gaps and the source queue; (6) preserve all
> existing rows and IDs.
>
> Rules: append-only by default; do not silently change an earlier judgement (add a dated note
> or a superseding row); do not upgrade `claimed` to `observed`/`measured`; an official source
> defines a field/access rule but does not thereby validate an analytical indicator; a vendor
> source supports what the vendor *claims to offer*, not independent effectiveness; keep
> current vs future relevance separate; keep data-existence, capability, observed use and
> measured validity separate; preserve `screening-only`/`needs-review` status; do not add a
> production TODO from one weak or selected-case source; if a field/method already exists in the
> plan, recommend documenting/testing/comparing rather than "adding" it again.
>
> **Return, without editing the register file directly unless explicitly asked:**
>
> - *Proposed inventory additions* — rows in the schema above.
> - *Proposed thematic additions* — each tagged with register section + exact source ID.
> - *Proposed negative evidence / cautions* — table: source ID | tempting interpretation | why
>   unsupported | safer treatment.
> - *Proposed project actions* — table: TODO ID | action | type | source IDs | why supported |
>   effort | risk | priority.
> - *Coverage / source-queue changes.*
> - *Existing entries that may need a dated note.*

**Per-source metadata helper.** To get just a register row from a single finished extraction:
"Create one compact register metadata record from the attached extraction. Use only
information present in it; `not-stated` if unknown. Return valid YAML in the §3 register-metadata
schema. Do not invent an ID (`register_id: pending`)."

---

## 5. Audit prompt (quality gate)

**Independence caveat.** A meaningful audit needs the checker to be independent of the writer.
In a single chat/Codex session, an extraction and its audit share context, so the audit tends
to ratify its own earlier output. For load-bearing sources, run the audit in a **separate
session** (ideally a different model) with only the source + extraction attached — not the
prior reasoning. Otherwise treat the audit as a self-check, not independent verification.

### Lightweight check (default)

> Check the attached extraction against its original source. Return only:
>
> **Major problems** — serious unsupported claims, evidence-role errors, time/missingness
> mistakes, incorrect data-access claims, entity-resolution overstatement, unsafe
> transferability.
>
> **Minor corrections.**
>
> **Safe to use?** yes / yes with caveats / no — with the reason.
>
> Do not rewrite the extraction. If the source was not fully accessible, state that the audit
> cannot verify inaccessible content.

### Escalated check (load-bearing sources)

Add these tables to the lightweight check: *Unsupported claims* (section | claim | why
unsupported | correct/remove | source evidence); *Missing important evidence*; *Evidence-role
errors* (claim | current role | correct role | reason); *Time/missingness/entity-resolution
errors*; *Overstated transferability or project action*; *Fields that should be `Not stated`/
`Not verified`*. End with a verdict: reliability high/medium/low; safe for register metadata
yes/with caveats/no; secondary check still needed; main corrections. Be conservative.

### Landscape / synthesis claim audit

For a broad report after per-source extraction: audit claim by claim; do not improve prose.
Return *Citation mismatches* (claim | citation | what the source actually supports |
correction); *Unsupported synthesis*; *Stale/mutable claims* (missing/old access date);
*Source-role problems* (vendor claim as effectiveness; official schema as data accuracy;
technical capability as observed use; selected case as prevalence; non-UK source generalised
to UK; current state as historical availability); *Missing counterevidence/limitations*; and a
verdict (safe to publish yes/after corrections/no; load-bearing claims needing manual check;
highest-risk section).

---

## 6. Synthesis prompt (late, by question)

> **Inputs:** finished §3 extraction files and/or the evidence register only. Do **not** use
> raw discovery notes as equal evidence.
>
> Synthesise the attached Open UK Company evidence by research question. Do not summarise each
> source in sequence. Do not count sources as votes; do not treat multiple vendor claims as
> independent validation. Weight evidence by what it can establish. Preserve jurisdiction,
> sample, access date and validation design. Do not synthesise beyond the attached extractions.
>
> Return:
>
> - **Data that exists and how to access it** — separate current list-level sources; population
>   snapshots/bulk/deltas; documents needing parsing; restricted/paid/request-only; non-UK.
> - **Tool and product landscape** — separate open-source capability; free lookup; paid
>   batch/API/data; opaque derived analytics; independently evaluated methods.
> - **How the data have been used** — descriptive/economic; investigations/network mapping;
>   operational due-diligence/KYB; predictive/rule-based indicators; monitoring/change
>   detection.
> - **Evidence for candidate indicators** — table: candidate | direct field/context | evidence
>   role | supporting sources | limiting sources | alternative explanations | current project
>   status.
> - **Cross-country transferability** — direct mappings, partial mappings, non-comparable
>   concepts.
> - **Validation and evidence limits** — labels, temporal validity, entity resolution, false
>   positives, selected cases, missingness, independent evaluation.
> - **Governance and publication limits** — only supported legal/guidance conclusions.
> - **Contradictions and uncertainty.**
> - **Evidence-backed project actions** — §2 action discipline.
> - **Remaining gaps and next source searches.**
>
> Rules: every material conclusion cites source/register IDs; preserve access dates for mutable
> claims; absence of published evaluation is **not** evidence of ineffectiveness; do not
> recommend a trust score; do not convert an investigative red flag into a general predictive
> indicator without independent validation.

### Source-queue gap helper

> Inspect the register and identify coverage gaps. Do not invent citations — return search
> questions and source types unless you can verify an exact source from the supplied material.
> Group by: official UK source definitions; tools/products; international registers; uses/
> evaluated methods; entity resolution; temporal/historical validity; governance/licensing/
> personal data; negative evidence and false-positive analysis. For each: gap | why it matters |
> existing source IDs | exact question | preferred source type | suggested queries | priority.
> Distinguish a missing source from a genuine absence of available evidence.

---

## 7. Human review checklist

Before accepting an extraction as final, verify:

- Exact source artefact, version and access date recorded; source was actually accessible at
  the claimed level.
- Official definition, capability, claim, observed use and measured outcome are not conflated;
  provider marketing is labelled as provider evidence.
- Mutable access/pricing/schema claims are dated.
- Direct register fields separated from derived values.
- Current / historic / event / snapshot / retrieval times distinguished.
- No-record / lawful absence / unsupported entity / fetch failure distinguished.
- Entity joins use identifiers or disclose uncertain matching.
- Predictive claims have an outcome, base rate, split design and appropriate comparator; no
  current data leaked into a historical prediction.
- Selected investigations not generalised to prevalence.
- Cross-country field mappings preserve legal/semantic differences.
- Personal-data, retention and publication issues recorded.
- Transferability decomposed across data, method, label and scale.
- Repo actions no stronger than the evidence; unknowns say `Not stated`/`Not verified`.
- Important numbers and citations checked against the source.

Do not mark an extraction final merely because it is polished or complete-looking.
