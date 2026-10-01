# Task register

Living record of built work, next actions, parked decisions, and known limits.
The audit log remains append-only; move items between sections here as work is verified.

## Done (built and verified)

- Core pipeline: strict input handling; rate-limited fetch/cache with ETag, SHA-256,
  archive-on-change and provenance; derivation; rule registry; scoring; generated
  `rules.md` and `data-dictionary.md`.
- Officers and PSC: paginated officer appointments, PSC list and statements, categorical
  ownership states, corporate annotations and cessation. ECCTA identity-verification and
  statement-filing fields remain distinct.
- Accounts and accounting-reference-date attributes, plus the existing registrar-recorded
  status, compliance, insolvency and address indicators.
- Insolvency validation harness: cache-only evaluation; conditional recall by case type;
  solvent/MVL guard; recent-positive sampler; snapshot control stratified by SIC section
  and age band; explicit positive-cohort scoping; pipeline-consistent dissolved/closed
  exclusions; PU framing and age-band flag rates in the report.
- Snapshot infrastructure: dynamic part discovery, complete-set validation, lazy full-width
  Polars scanning, string-preserved `CompanyNumber` despite the real leading-space header,
  and a dated/hash provenance manifest.
- Baseline Quarto methodology site under `docs/site/` (local build only).

## In progress / needs a real run

- Run the first representative validation study: draw and fetch approximately 500 recent
  adverse positives and 500 stratified controls, then evaluate. Interpret the genuine-miss
  list and control flag rate by age band. This is an operator/network run; no results are
  claimed until it is complete.

## Ready to build (specified, not started)

- Gazette winding-up integration. The detailed specification is
  `validation-and-gazette-specs.md` (the Gazette prompt). Notice JSON-LD at
  `/notice/{id}/data.jsonld` has a structured `companyNumber`. Limit ingestion to corporate
  category 24: code 2450 petition is medium/early warning and must check for dismissal code
  2461; code 2452 order is high and largely redundant with Companies House status. Exclude
  personal category 25 for data protection. Whitelist the `LimitedCompany` node and never
  emit insolvency-practitioner PII.
- Publish the Quarto site through CI. The skeleton builds locally; CI and hosting
  configuration were deliberately outside the scaffolding task.

## Parked / backlog

### Class A: more structure from registrar-recorded facts

- Directorship networks: follow officers to other appointments and count prior
  dissolved/liquidated companies. This is the largest single extension; keep officer PII
  cache-only.
- Registered-address **concentration**: detect mass registration using the snapshot. Do not
  turn addresses into deprivation/geodemographic proxies; that is the biased-parameter trap,
  whereas concentration is a recorded fact.
- Previous-name/name-change churn: a cheap recorded-fact opacity signal.

### Class B: inferred proxies

- Test catch-all SIC counts (`82990`, `74990`, `99999`) as an opacity/distress hypothesis;
  this is the cheapest Class B candidate.
- Explore SIC-section-stratified attributes.
- Hard rule: every Class B feature ships as a documented **attribute first**. It may become
  a rule only after the validation harness demonstrates separation. Data-driven SIC
  clustering must be fit on the broad snapshot population, never a single-sector input
  list, or it will overfit.

### Architectural and semantic decisions

- ECCTA semantics: `identity_verified_on` records the verification act;
  `appointment_verification_statement_date` records a filed statement. They remain separate
  counts and no rule keys off either while rollout matures.
- Two stages: deterministic bulk screening identifies a flagged minority; an optional
  per-company agentic deep read may inspect accounts or document API filings for the handful
  worth reviewing. That second stage is not part of `ukcompany run`.
- Sanctions/PEP matching is parked because name-only matching has high false-positive and
  defamation risk. It requires confidence and human review. Disqualified-director matching
  is the cleaner in-family alternative because it is registrar-recorded Tier 1 evidence.

### Explicitly rejected for the bulk pass

- Trustpilot/review data: scraping/terms risk, gameable evidence, wrong evidence class, and
  fragile entity resolution.
- Contracts Finder as a trust signal: awards proxy sector and company size, not reliability.
- Bulk accounts-PDF financial extraction: iXBRL parsing cost, self-reported or unaudited
  small-company data, and sparse micro-entity accounts. It belongs in an optional
  per-company deep-read stage.
- SIC-name/business-description agreement: NLP-noisy and too thin a signal.

## Open questions / known limits

- Validation is positive-only/PU. Conditional recall is measurable; precision is not,
  because no negative labels exist and the control is only assumed not labelled positive.
- Insolvency is adjacent to, not identical with, "trustworthiness". The study can validate
  insolvency detection, not establish company trustworthiness.
- Officer and PSC identities are unverified before ECCTA. Same-person joins based on name
  and birth month are fuzzy.
- Keep three time bases separate: API current state, monthly snapshot date, and the
  Insolvency Service label window (2012–2024).
