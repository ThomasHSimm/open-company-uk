# Project plan: `open-company-uk` — batch Companies House extraction and company-status, compliance and ownership indicators

*Plan v0.3, August 2026. Naming: repository `open-company-uk` (fits the open-road-risk / openbotrisk family), Python package/CLI `ukcompany` (PyPI deferred; note a `ukcompanies` package likely already exists — check before publishing). "Batch" not "bulk": v1 processes a supplied list, not the register. Goal: given a list of UK company numbers, produce (a) a full structured attribute table and (b) a transparent, rule-documented indicator table — from free Companies House data, no LLM in the bulk path, no paid subscriptions.*

*Positioning: "an open, reproducible pipeline for analysing UK company-register data and deriving transparent company-status, compliance and ownership indicators." Not a "trustworthiness" measure — CH records support due-diligence signals; they cannot establish that a company is trustworthy, solvent or non-fraudulent.*

---

## 1. Scope

**In scope (v1):**
- Input: CSV/list of company numbers.
- Fetch + cache raw JSON from the CH Public Data API (profile, officers; filing history optional).
- Derive a wide attribute table (everything useful, not just risk fields).
- Apply a documented rule registry producing per-company flags with severity and provenance.
- Outputs: `companies.parquet`/`.csv` (attributes), `flags.csv` (long format: company, rule_id, severity, evidence), plus a short markdown summary per run.

**Explicitly out of scope (v1), revisit later:**
- iXBRL financial accounts parsing (messy, low content for micro-entities).
- Company-name → number resolution (assume numbers supplied; fuzzy matching is its own project).
- Officer network graphs.
- Any LLM component (optional post-hoc summariser could be a v3 extra, never in the bulk path).
- Non-UK registries.

**Why the word "trustworthy" is avoided (stated in README):** the indicators are presence/absence of registrar-recorded adverse statuses, events and filing-compliance indicators — *not* creditworthiness, solvency, or fraud detection. Absence of flags is weak evidence; the signal is asymmetric.

---

## 2. Architecture

Three strictly separated layers. Scoring must be replayable from cache without network access.

```
input list ─▶ [fetch] ─▶ cache/raw JSON ─▶ [derive] ─▶ attributes table ─▶ [score] ─▶ flags
                │                                                            ▲
                └── rate limiter, retry, resume                              └── rules.py (registry)
```

```
ch-screen/
├── src/chscreen/
│   ├── client.py        # requests session, auth, 600/5min token bucket, 429/5xx backoff
│   ├── fetch.py         # endpoints, pagination, cache write, resume logic
│   ├── cache.py         # read/write data/raw/{company_number}/{endpoint}.json + fetch metadata
│   ├── derive.py        # raw JSON -> flat attribute dict (pure functions, .get() everything)
│   ├── rules.py         # rule registry: id, tier, definition, severity, function
│   ├── score.py         # apply registry to attributes -> flags long table
│   ├── validate.py      # company number normalisation (zero-padding, prefixes), input checks
│   └── cli.py           # `chscreen fetch|derive|score|run` (argparse or typer)
├── config/settings.yaml # paths, endpoints on/off, input file — runtime config only
├── data/                # gitignored; raw/, processed/
├── tests/
│   ├── fixtures/        # anonymised/synthetic JSON responses per endpoint + edge cases
│   ├── test_validate.py test_derive.py test_rules.py test_client.py
├── docs/
│   ├── rules.md         # THE key document — every rule: definition, CH field, tier, caveats
│   └── data-notes.md    # attribute dictionary incl. verification-tier classification
├── .github/workflows/ci.yml   # pytest + ruff, no live API calls
├── .pre-commit-config.yaml    # ruff, detect-secrets, large-file check
├── pyproject.toml
└── README.md
```

Conventions carried over from existing projects: ruff (line length 100, relaxed docstring/naming rules), pytest, pre-commit with detect-secrets, methodological constants in code with comments, runtime config in `settings.yaml`, no YAML overkill. API key via `CH_API_KEY` env var only — never in config. Dataframes: Polars for bulk/snapshot work, converting to pandas at the analysis boundary only where needed; no Spark.

**Design decisions locked in:**
- **Cache is the source of truth, and versioned.** Envelope metadata: fetched_at, URL, HTTP status, ETag, sha256 content hash. Refreshes archive the superseded response to history/ when content changed (archive-on-change), so register changes stay observable and past runs replayable. fetched_at (retrieval), event dates (register), and any snapshot_date (bulk product) are distinct and never conflated. Re-scoring after rule changes = zero API calls; runs resume via a staleness window.
- **Rules live in code, not YAML.** Each rule is a small function + metadata dataclass (`rule_id`, `name`, `tier`, `severity`, `definition`, `caveats`). `docs/rules.md` is generated from the registry so documentation cannot drift from implementation (adopt the lesson from ORR documentation-drift).
- **Attributes ≠ flags.** The attribute table carries everything (SIC, type, age, accounts category…); verification tier is a property of each FIELD, documented in a generated field-level data dictionary (docs/data-dictionary.md, from FIELD_DOCS in derive.py) — not a per-row column. The flag registry only ever uses Tier-1 fields in v1. Users can build their own features from attributes; the shipped flags stay defensible.
- **Source precedence.** The API is authoritative for freshness-sensitive current state; the monthly snapshot (phase 2) is dated population context only. Every stored value carries its observation date; conflicting values across sources are surfaced, never silently coalesced.

## 3. v1 rule registry (draft)

| rule_id | Definition (CH field) | Severity | Notes |
|---|---|---|---|
| STATUS_INSOLVENT | `company_status` in {liquidation, administration, receivership, voluntary-arrangement, insolvency-proceedings} (full spec enum), EXCEPT status=liquidation where all cached cases are solvent types | high | Spec-checked 2026-08 |
| STATUS_STRIKEOFF | active-proposal-to-strike-off in status/status_detail | high | |
| INSOLVENCY_ADVERSE | insolvency resource (via `links.insolvency`, fetched+cached) contains ≥1 case of non-solvent type; or insolvency indicated but cases uncached (fires 'unclassified') | high | Members' voluntary liquidation is a SOLVENT winding-up and never triggers this — it gets its own info rule SOLVENT_WINDING_UP. `has_insolvency_history`/`has_been_liquidated` CONFIRMED deprecated per spec ('Please use links.insolvency'); fallback only |
| ACCOUNTS_OVERDUE | `accounts.next_accounts.overdue` = true (`accounts.overdue`/`accounts.next_due` ALSO deprecated per spec; fallback for old cache) | medium | Spec-checked 2026-08 |
| CS_OVERDUE | `confirmation_statement.overdue` = true | medium | |
| REPEAT_LATE_FILER | ≥2 accounts filed after their reconstructed statutory deadline | medium | v1.1+. Historical deadline reconstruction, not a filing-history count: first-accounts rule, deadline-rule changes over time, COVID extensions. Bigger than it looks; also needs pagination |
| ADDR_DISPUTE | `registered_office_is_in_dispute` or `undeliverable_registered_office_address` | medium | |
| CHARGES_OUTSTANDING | `links.charges` present (`has_charges` CONFIRMED deprecated per spec; fallback only) | info | Normal for financed businesses — context, not risk |
| YOUNG_COMPANY | age < 24 months | info | Context only; never counts toward a risk total |
| PSC_IDENTIFICATION_INCOMPLETE (and siblings) | Derived from SEPARATE fields, not one enum: `psc_fetch_status` (pipeline state, never a company signal), `psc_records_state` (from the PSC list), `active_psc_statement_codes` (verbatim official codes from psc_descriptions.yml, incl. their misspellings), derived `psc_information_state` | low/medium per statement | v1.1. Material statement codes go beyond steps-not-yet-completed: PSC exists but unidentified, details unconfirmed, no response to notice, failure to confirm changed details, restrictions notices. Rules key off specific codes; the representation itself is not a rule |

Severity semantics documented in rules.md: `high` = registrar-recorded adverse status or event; `medium` = compliance failure; `info` = context, excluded from any aggregate count. Dissolved/converted/closed statuses live in a separate **exclusions/status table**, not the flag registry — they gate whether a company is screenable at all, and belong in input-list hygiene reporting. **No composite single score in v1.** Source events are recorded facts; flag definitions, thresholds, severities and any aggregation are documented analytical judgements — the in-code registry with generated rules.md is what keeps those judgements auditable. If a composite is ever added it gets its own methodology page.

## 4. Phases and effort

| Phase | Content | Est. effort | Exit criterion |
|---|---|---|---|
| **0 — plumbing** | validate.py (number normalisation — the leading-zero bug class), client.py with token bucket + backoff, fetch/cache for `/company/{n}`, resume | 1 evening | 10 test numbers fetched, cached, re-run makes 0 calls |
| **1 — attributes + flags** | derive.py over profile JSON + linked insolvency resource (fetched when `links.insolvency` present), rule registry above, score.py, CSV outputs, generated rules.md + data-dictionary.md, fixtures + tests | 1–2 evenings | 100-company run end-to-end; every flag traceable to a cached response |
| **1.1 — officers, PSC, filing history** | pagination (35–100/page — test on an old PLC, not a young Ltd), officer churn attribute, PSC fields + statement-code rules | 2–3 evenings | Pagination test passes on a company with >100 filings |
| **1.2 — late-filing reconstruction** | REPEAT_LATE_FILER via historical statutory-deadline reconstruction (first-accounts rule, rule changes over time, COVID extensions) | 2–3 evenings | Deadline logic unit-tested against known cases across regimes |
| **1.5 — external free Tier-1 sources** | Gazette winding-up petitions (separate API, same cache pattern); disqualified-directors cross-check | 2–3 evenings | Documented join keys and match-confidence handling |
| **2 — population features** | Monthly snapshot ingest (~470 MB compressed as of Aug 2026) via Polars lazy scan → Parquet; schema + provenance manifest + data-quality report; registered-address concentration (a high-frequency address may be an accountant, virtual office or legitimate shared premises — concentration is the fact; interpretation is separate); SIC/type cohort baselines | 2–4 evenings + storage | Explicit bias caveats written before shipping; snapshot values never override API current-state (see source precedence) |
| **3 — extras (optional)** | LLM summariser for top-N flagged; PyPI packaging (ukgeo pattern); Quarto methodology page | as desired | — |

Phases 0–1 give the usable tool. Everything after is additive.

## 5. Testing strategy

- **No live API in CI.** All tests run against `tests/fixtures/` JSON: a normal active company, an insolvent one, a dissolved one, a minimal old-record with missing fields, a paginated officers response, a 429 response.
- Unit-test the token bucket with a fake clock; test resume by pre-seeding cache.
- One `@pytest.mark.live` smoke test, skipped in CI, run manually against 2–3 real numbers.
- Property-style checks on validate.py: round-trip normalisation, rejection of malformed numbers.

## 6. Risks and open issues

1. **Input number quality.** If company numbers ever passed through Excel, leading zeros are gone — and the loss is non-random (hits English companies, spares SC/NI prefixes). Phase 0 validation must hard-fail with a clear report, not silently 404.
2. **GDPR.** Officer records are personal data (names, partial DOB, addresses). Caching locally for analysis is defensible; **publishing** officer-level data or named flag lists in the repo/site is a different legal posture. Rule: repo ships code + methodology + synthetic fixtures only; never real bulk outputs, never officer data. State this in README.
3. **Defamation exposure.** Publicly labelling named companies as red-flagged is a liability risk even when factually grounded. Same rule as above: methodology public, results private.
4. **Schema drift / ECCTA transition.** Identity-verification rollout is changing officer data semantics mid-2025→2026; pin API version assumptions in data-notes.md with a checked-on date. `.get()` everything.
5. **CH API terms.** Free for use including commercial, but confirm current attribution requirements before publishing the repo; note the API is "unverified register data" per CH's own disclaimers — quote that framing in README, it does the caveat work for you.
6. **Scope creep magnet.** iXBRL, name-matching, and network graphs are each bigger than the whole v1. The out-of-scope list at the top is the defence; keep it in the README.
7. **Rate-limit fragility.** 600/5min is per key; other tools using the same key (e.g. an MCP server) share the budget. Token bucket should be conservative (~500/5min).

## 7. What v1 deliberately does not claim

- Not a credit score; no financials.
- Not fraud detection; a clean CH record is cheap to obtain.
- Not verified identity data for anything pre-ECCTA.
- No opinion embedded in a composite number. Every indicator is traceable to specified source fields or events and a documented transformation; otherwise it does not ship.
