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
cp .env.example .env    # then put your key in .env (gitignored), or export CH_API_KEY
# free key: developer.company-information.service.gov.uk -> sign in ->
# Manage applications -> Create application (Live) -> New REST API key

ukcompany run --input companies.csv        # CSV with a company_number column
#   (see examples/companies.sample.csv - extra columns ignored, header case-insensitive,
#    single-column headerless files also accepted)
ukcompany run --input companies.csv --no-fetch   # re-derive/score from cache only
ukcompany snapshot fetch --month 2026-08         # cache + manifest a monthly bulk snapshot
ukcompany snapshot info                          # inspect the latest cached snapshot
ukcompany validate --labels record-level-data.csv \
  --control-from-snapshot --control-n 500 \
  --write-positives-sample data/positives-sample.csv --positives-n 500
# Fetch the generated lists with `ukcompany run`, then evaluate cache-only:
ukcompany validate --labels record-level-data.csv \
  --positives data/positives-sample.csv --control data/control-numbers.csv \
  --out data/insolvency-validation.md
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
  freshness-sensitive fields (status, overdue flags, insolvency). Officer and
  PSC endpoints are fetched in full across pages, including PSC statements and
  distinct ECCTA identity-verification/statement fields. The monthly bulk
  snapshot supplies *dated population context* and never silently overrides API
  values.
- **Rules are code with metadata.** `src/ukcompany/rules.py` is the judgement
  layer; `docs/rules.md` is generated from it. v1 rules use registrar-recorded
  (Tier 1) fields only; verification tiers per field are in the generated
  docs/data-dictionary.md. `info`-severity rules are context and never count
  toward any aggregate.
- Rate limiting is conservative (500 req/300s vs the published 600) because
  API keys may be shared across tools.
- **Validation is cache-only and positive-unlabelled (PU).** It measures
  conditional recall against Insolvency Service adverse labels and reports flag
  rates in a snapshot control stratified by SIC section and age band. With no
  negative labels, that flag rate is not precision or a false-positive rate.
- **Snapshots are reproducible inputs.** All dynamically discovered monthly
  parts must be complete; archives are hashed in a provenance manifest and
  scanned full-width and lazily with Polars, preserving company numbers as
  strings.

## Data protection and publication policy

Officer/PSC records are personal data. This repository publishes **code,
methodology and synthetic fixtures only** — never bulk outputs, officer-level
data, or named flag lists. Run outputs stay in the gitignored `data/`
directory. Publicly labelling named companies as flagged is a defamation
exposure even when factually grounded; keep methodology public and results
private.

## Status / roadmap

Built: the core fetch/cache/derive/rule pipeline; paginated officers and PSC
records and statements; ECCTA verification attributes; the insolvency
validation harness and samplers; and the manifested, lazy Polars monthly
snapshot loader. The first representative validation run still needs to be
performed and interpreted.

Next specified integration: corporate Gazette winding-up petitions and orders.
Other candidate features and their evidence/bias constraints are tracked in
[`docs/TASKS.md`](docs/TASKS.md); methodology pages live in
[`docs/site/`](docs/site/). Filing-history deadline reconstruction and the
Gazette/disqualified-director extensions are not yet built.

Not affiliated with or endorsed by Companies House. Contains public sector
information licensed under the Open Government Licence v3.0.
