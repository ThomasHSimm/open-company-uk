# PSC bulk per-company feature table

One row per company that appears in the Companies House PSC bulk snapshot, carrying the same
ownership/control features the per-company API path (`ukcompany.derive.derive_psc`) produces,
under the **same definitions**. The nature-of-control decomposition, kind classification and
UK-company-number format test are reused verbatim from `ukcompany.psc_natures` — there is one
definition of each rule, shared by the API path, the bulk loader (`psc_noc`) and this feature
table. Built by `ukcompany.psc.features.build_psc_features` (CLI: `ukcompany-psc features`).

## How it is built

```
ukcompany-psc refresh  --snapshot-date YYYY-MM-DD    # download, verify, prune, extract, load
ukcompany-psc features --snapshot-date YYYY-MM-DD    # governed tier (default)
ukcompany-psc features --snapshot-date YYYY-MM-DD --no-data-governance   # private tier
```

Features are built from the **governed load** (`psc_records.parquet` + `psc_noc.parquet`),
which carries the pseudonymous `person_key` plus every non-PII feature input. The heavy
grouping runs in DuckDB; the `psc_natures` functions are applied in Python over the small
*distinct* vocabularies (the ~13k distinct nature code-sets, the ~10 kinds, the distinct
corporate registration numbers) and joined back by key, so the result is identical to calling
the function per company without iterating ~11M rows.

## Two tiers

| Tier | Flag | Contents |
|---|---|---|
| **governed** (default) | `--data-governance` | every feature below **except** the companies-per-person bands — no person-derived linkage. The written schema is asserted to not contain either band column. |
| **private** | `--no-data-governance` | adds `companies_per_person_band_ever` and `companies_per_person_band_active` (person linkage). |

## Columns

All of the following carry the **same definition and caveats** as the matching
`derive_psc` field — see `FIELD_DOCS` in `src/ukcompany/derive.py` (and the generated
`docs/data-dictionary.md`). Scope: counts of individuals/corporates/legal-persons/super-secure
and the nature-of-control features are over **active** records; `psc_n_records`/`psc_n_ceased`
and the identity-verification counts are over all (active + ceased) records. Active/ceased uses
`derive_psc`'s exact rule: ceased is the per-item `ceased` boolean when present, else the
presence of `ceased_on` (the loader extracts the `ceased` boolean for this).

`psc_n_records`, `psc_n_ceased`, `psc_natures_of_control`, `psc_max_ownership_band`,
`psc_max_voting_band`, `psc_has_appointment_rights`, `psc_has_significant_influence`,
`psc_n_distinct_natures`, `psc_n_individual`, `psc_n_corporate`, `psc_n_legal_person`,
`psc_n_super_secure`, `psc_corporate_reg_numbers`, `psc_n_corporate_uk_format_regno`,
`psc_unmapped_natures`, `n_psc_id_verified`, `n_psc_id_verification_due`,
`n_psc_id_statement_filed`, `active_psc_statement_codes`, `psc_information_state`.

`psc_fetch_status` is **not** carried: it is API-pipeline state (did we fetch the list), and
every company in the snapshot was by definition present — there is no "not_fetched" case.

### `companies_per_person_band_ever` and `companies_per_person_band_active` (private tier only)

For each company, the **maximum** over its in-scope individual PSCs of the band of how many
companies that person controls, where the person is identified by the **baseline key**
(lower-cased forename + surname + DOB year + month) and the bands are `1` / `2-10` / `11+`. The
private tier emits **both** scopes: `_ever` counts companies over active + ceased roles (the
scope Task C used, `docs/psc-checks-results.md`) across the company's individual records;
`_active` counts over active roles only (current control footprint) across the company's active
individual records. The governed tier carries **neither**.

Caveats (this is a weak identity signal, never a clean person identity):

- **Baseline-key collisions.** Common names collide; the key has no name-frequency control.
  ≤2.07% of baseline keys show a *detectable* split into >1 strict key (adding the middle
  name), and that bound misses no-middle-name and shared-middle-name collisions — see
  `docs/psc-checks-results.md`. Read the band only alongside name-commonness.
- **Pseudonymous.** Linkage uses the HMAC `person_key` (keyed by `PSC_PERSON_KEY_SECRET`); the
  band output exposes no name, DOB or key.
- **Governance.** Person-derived linkage, so it is **in the private (ungoverned) tier only** and
  **absent from the governed tier** (maintainer-confirmed). No PSC data is published from this
  project at all — code and suppressed site aggregates only — so "governed" here means the
  shareable-aggregate basis, not a public upload.

## Validation

- **Parity vs the API path** — `scripts/psc_parity_check.py`, written to
  `docs/psc-parity-2026-09-25.md` (with per-disagreement fetch-date/direction detail in the
  `.json` sidecar). On the 999 companies in both the API cache and the snapshot, agreement is
  99.8–100% on 18 of 20 features; `n_psc_id_verification_due`/`n_psc_id_statement_filed` sit at
  94.7%. Every disagreement is **temporal** (the API cache is ~7 weeks older than the snapshot),
  not a definition difference — the synthetic parity unit test (`tests/test_psc_features.py`)
  agrees 100% on identical input. The monotonicity check surfaced one data-semantics finding:
  `n_psc_id_statement_filed` is **not** a cumulative count (it fell between the cache and the
  snapshot for 53 companies with no membership change) because
  `appointment_verification_statement_date` reflects the current verification cycle and clears on
  reset; `n_psc_id_verified` (block presence) is cumulative and shows zero violations.
- **Coverage vs the register** — `scripts/psc_coverage_check.py`, written to
  `docs/psc-coverage-2026-09-25.md`. 97.32% of register companies (97.63% of Active-status) have
  a PSC row. Types shown ~100% uncovered (Charitable Incorporated Organisations, Registered
  Societies, Royal Charter companies, ICVCs, …) are outside the PSC regime; PSC-regime types are
  near-fully covered.

## Snapshot-vs-register caveats

- The snapshot is a single dated instant; corrections over time are not captured unless
  archived (see the D1 retention policy in `ukcompany.psc.archive`).
- Active/ceased uses `derive_psc`'s rule (per-item `ceased` boolean first, else `ceased_on`
  presence); the loader now extracts the boolean, so the earlier `ceased_on`-only gap is closed.
  The one residual difference is that the bulk snapshot has no top-level `active_count`/
  `ceased_count`, which `derive_psc` would prefer when present — a minor source of parity drift.
- The identity-verification counts use a **block-presence proxy** (any extracted `iv_*` field
  present), because the raw JSON is dropped in governed mode. This matched the API path on 99.9%
  of `n_psc_id_verified`; the `due`/`statement_filed` counts drift more, driven by the live
  ECCTA rollout.
- The snapshot retains PSC records for **dissolved** companies: it has ~10.93M companies vs
  ~5.69M on the live register, and the register excludes dissolved companies.
