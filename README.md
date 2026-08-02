# open-company-uk

An open, reproducible pipeline for analysing UK company-register data and deriving
transparent company-status, compliance and ownership indicators, from free
Companies House data.

Given a CSV of company numbers, it fetches and caches raw Companies House API
responses, derives a wide attribute table, and applies a documented rule
registry producing per-company indicator flags with severity and evidence.

**What this is not.** Companies House records can support due-diligence
signals; they cannot establish that a company is trustworthy, solvent or
non-fraudulent. There is no composite score: source events are recorded facts,
while rule definitions, severities and any aggregation are analytical
judgements — documented in [docs/rules.md](docs/rules.md), which is generated
from the rule registry in code so documentation cannot drift from
implementation. Absence of flags is weak evidence: the signal is asymmetric.
Companies House itself describes the register as unverified information
supplied by companies; identity verification (ECCTA) is still rolling out.

## Quickstart

```bash
pip install -e .[dev]
export CH_API_KEY=...   # free key: developer.company-information.service.gov.uk

ukcompany run --input companies.csv        # CSV with a company_number column
ukcompany run --input companies.csv --no-fetch   # re-derive/score from cache only
ukcompany rules-doc                        # regenerate docs/rules.md
ukcompany data-dict                        # regenerate docs/data-dictionary.md
```

Outputs in `data/processed/`:

| file | content |
|---|---|
| `companies.csv` | one row per company: all derived attributes (Tier 2/3 fields like SIC included — see verification-tier notes in the plan) |
| `flags.csv` | long format: company_number, rule_id, severity, evidence, observed_at |
| `excluded.csv` | dissolved/converted/closed companies — not screenable, not scored |
| `not_found.csv` | numbers with no register entry (check input hygiene first) |

Input validation is deliberately strict: company numbers damaged by
spreadsheets (stripped leading zeros, trailing `.0`) are repaired and
*reported*; unrepairable rows hard-fail the run unless `--allow-invalid` is
passed. Silent dropping would bias results by jurisdiction (digit-only
English/Welsh numbers are the ones spreadsheets damage).

## Design

```
input list -> [validate] -> [fetch] -> data/raw JSON cache -> [derive] -> attributes -> [score] -> flags
```

- **The cache is the source of truth.** Every raw response is stored with fetch
  metadata; every derived value is traceable to a timestamped response;
  re-scoring after rule changes needs zero network access; runs resume for free.
- **API-first for current state.** The REST API is authoritative for
  freshness-sensitive fields (status, overdue flags, insolvency). The monthly
  bulk snapshot is planned as a *dated population-context* source (address
  frequency, cohort baselines) and never silently overrides API values.
- **Rules are code with metadata.** `src/ukcompany/rules.py` is the judgement
  layer; `docs/rules.md` is generated from it. v1 rules use registrar-recorded
  (Tier 1) fields only; verification tiers per field are in the generated
  docs/data-dictionary.md. `info`-severity rules are context and never count
  toward any aggregate.
- Rate limiting is conservative (500 req/300s vs the published 600) because
  API keys may be shared across tools.

## Data protection and publication policy

Officer/PSC records are personal data. This repository publishes **code,
methodology and synthetic fixtures only** — never bulk outputs, officer-level
data, or named flag lists. Run outputs stay in the gitignored `data/`
directory. Publicly labelling named companies as flagged is a defamation
exposure even when factually grounded; keep methodology public and results
private.

## Status / roadmap

Phase 0–1 (this): validation, rate-limited client, cache, profile-derived
attributes, profile-based rules, CLI, tests (fixture-based, no live calls in CI).

Planned: officers + filing history with pagination (officer churn,
statutory-deadline reconstruction for repeat late filing), PSC statement
categorical, Gazette winding-up petitions, disqualified-directors cross-check,
monthly snapshot ingest via Polars for population-relative features. See
`docs/plan.md`.

Not affiliated with or endorsed by Companies House. Contains public sector
information licensed under the Open Government Licence v3.0.
