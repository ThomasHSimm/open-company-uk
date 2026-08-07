# Companies House data for company screening: data, attributes, and product landscape

*Working synthesis, August 2026. Purpose: identify auditable Companies House (CH) attributes for transparent screening rules, document their interpretation and limitations, and map the open-source, free, and commercial product landscape. This is not an evidence register; claims should be linked to completed source extractions before publication.*

**Companion documents:** `open-uk-company-research-pack.md` defines the extraction method and
`open-company-uk-source-queue-2026-08.md` holds candidate sources and priorities. This file is the
readable synthesis; it should cite evidence-register IDs once extractions are accepted.

---

## 1. Access routes to Companies House data

| Route | Cost | Coverage | Best for |
|---|---|---|---|
| **Public Data API** | Free (API key) | Per-company: profile, officers, PSC, filing history, charges, insolvency, registered office | Lookups for a known list of company numbers. Rate limit 600 requests / 5 min. |
| **Free Company Data Product** | Free download | Monthly snapshot of live companies, split across CSV zip files | Whole-population features: address frequency, SIC distributions, cohort baselines. Record the snapshot date and observed population in each run. |
| **PSC snapshot** | Free download | Daily snapshot of publicly available persons-with-significant-control data (JSON) | Ownership-structure features at scale, subject to the PSC regime’s scope and protected-information rules. |
| **Accounts bulk data** | Free download | Daily/monthly zips of filed digital accounts (iXBRL) | Financial features — but iXBRL parsing is genuinely messy and micro-entity accounts contain little. |
| **Streaming API** | Free | Real-time change events | Monitoring, not backfill. |
| **Document API** | Free | Original filed documents (PDF/iXBRL) | Deep-dive on flagged companies only. |
| **Find and update company information (web)** | Free | Everything, manually | Spot checks. |

Developer hub: https://developer.company-information.service.gov.uk/
Bulk products: https://download.companieshouse.gov.uk/

**Key point for a bulk screening pipeline:** for hundreds of known company numbers, the Public Data API is likely sufficient. Runtime depends on which conditional endpoints are fetched, cache hits, retries and the published rate limit, so it should be measured rather than fixed in the design. The monthly bulk snapshot becomes useful when population-relative features are required (for example, how many companies share a registered address).

---

## 2. Attributes: what is registrar-derived, filed, and self-declared

This is the part that matters for explaining what a parameter actually represents. The tiers below describe **provenance and interpretation**, not inherent accuracy, fairness or predictive value.

### Tier 1 — Registrar-recorded or registrar-derived states

| Field | Endpoint | Meaning |
|---|---|---|
| `type` (company type: ltd, plc, llp, CIC, etc.) | `/company/{n}` | Legal form recorded on the register. Changes normally require a formal filing, but the field remains an administrative record rather than independent verification of the company’s activity. |
| `company_status` (active, liquidation, administration, dissolved, etc.) | `/company/{n}` | Current administrative state recorded by CH from formal processes. It may lag an underlying event and should not be expanded into a broader claim about trading or solvency. |
| `date_of_creation` | `/company/{n}` | Recorded incorporation date. It is not evidence of when trading began; shelf companies can make company age differ from operating history. |
| `has_insolvency_history`, `has_charges` | `/company/{n}` | Summary indicators that relevant records exist. They do not classify the seriousness or current status of those records: fetch the detailed resources. In particular, `has_charges` does not mean a charge is outstanding. |
| `accounts.overdue`, `confirmation_statement.overdue` | `/company/{n}` | CH-computed deadline states. They are clear compliance indicators, but their predictive relationship with distress or misconduct requires separate validation. |
| Charge records | `/company/{n}/charges` | Formal registered records with per-charge status. Use the status field; the presence of a charges link or historical charge is not evidence of an outstanding charge. |
| Insolvency cases | `/company/{n}/insolvency` | Recorded formal proceedings. Classify the case before assigning severity; missing or unfetched case detail should remain unknown rather than adverse. |
| Filing history (event dates, types) | `/company/{n}/filing-history` | Evidence that CH recorded a filing of a given type and date. This does not independently verify the substantive content filed. |

### Tier 2 — Filed within legal and reporting constraints

| Field | Caveat |
|---|---|
| `accounts.last_accounts.type` (micro-entity, small, full, dormant) | Records the accounts category filed, reflecting eligibility rules and filing choices where alternatives exist. It is primarily a disclosure-level and company-size signal, not an adverse indicator by itself. |
| Accounts financial content (iXBRL) | Audit and disclosure requirements depend on company type, size, accounting period and the rules then in force. Extract and date the current statutory thresholds before making audit-status claims. Even correctly parsed figures are filed statements, not automatically independently verified values. |
| Officers / PSC records | Identity verification is being introduced through a phased ECCTA transition. Interpret verification fields using the role, applicability and due date in force at retrieval time. Historic or currently unverified entries are register assertions, but absence of a verification block is not automatically non-compliance. |
| Registered office address | ECCTA "appropriate address" rules apply from March 2024, and CH now has powers to query/remove addresses, but mass-registration formation-agent addresses remain common and legitimate. |

### Tier 3 — Self-declared, weakly constrained (use with explicit caution)

| Field | Problem |
|---|---|
| **SIC codes** (`sic_codes` — "nature of business") | Company-supplied classifications can be coarse, stale or represented by catch-all codes. If SIC is used as a feature, quantify missingness, instability and disagreement with another source where possible; do not assume that its error pattern is random or that it is the project’s largest measurement-error source without evidence. |
| Company name | No constraint on describing activity. |
| PSC statements | Filed statements with defined statutory meanings, including cases where no registrable PSC has been identified or required steps have not been completed. They are not direct proof that the natural ultimate beneficial owner has been found. Interpret the exact enumeration rather than treating all absence as one adverse state. |

### Bias considerations for model features

- **Late filing** correlates with company size and admin resources, not only with distress. A one-person company filing 3 days late is different from a 50-person company doing so. Consider severity (days overdue, repeat pattern) rather than a binary flag.
- **Address-derived features** can proxy for socioeconomic geography, company-formation channels, sector and company size. Shared addresses also include legitimate accountants, formation agents, virtual offices and corporate groups. Their meaning requires population context and false-positive analysis.
- **Company age** penalises legitimate startups. Fine as a *context* variable, dangerous as a standalone score component.
- **Micro-entity accounts** penalise small honest companies. Disclosure level ≈ size, not trustworthiness.
- The clean framing: Tier 1 fields are auditable records of administrative states or events. Rules using them can be reproducible and evidence-emitting, but that does not establish fairness, predictive validity or an appropriate universal severity. Tier 2/3 fields need additional measurement and interpretation caveats.

---

## 3. Open-source tools

| Tool | What it is | Fit |
|---|---|---|
| **companies-house-cli / companies-house-mcp** (aicayzer) | CLI (`ch`) + MCP server over the Public Data API, including combined reports and a register-based due-diligence summary. CLI works without an LLM. https://github.com/aicayzer/companies-house-mcp | Closest identified functional comparator. Inspect its implementation and tests at a fixed commit, especially evidence, unknown states and screening semantics. Its output is explicitly a screening summary rather than verification or clearance. |
| **stefanoamorelli/companies-house-mcp** | MCP server exposing a broad portion of the API, including officer, PSC and disqualification operations. https://github.com/stefanoamorelli/companies-house-mcp | Useful as an API-surface and agent-interface reference, but an MCP/LLM path is inefficient for deterministic bulk processing. Tool counts and endpoint coverage are mutable and should be dated. |
| **chpy** (specialprocedures) | Python wrapper + networkx corporate-network builder (officers/PSC graphs from a seed company). https://github.com/specialprocedures/chpy | Network-feature comparator rather than bulk screening. Inspect maintenance at a fixed commit, and evaluate fuzzy person matching against labelled links before relying on graph results. |
| **CompaniesHouse** (MatthewSmith430, R) | R package for API extraction + interlocking directorate networks. https://github.com/MatthewSmith430/CompaniesHouse | R ecosystem equivalent of the above. |
| **ONSBigData/parsing_company_accounts** | Experimental XBRL/iXBRL and scanned-PDF accounts parsers. https://github.com/ONSBigData/parsing_company_accounts | Useful methodological prior art. The repository describes the code as under development and advises checking outputs, so it is not a production dependency or accuracy benchmark. |
| **pometry-archive/companies_house_scraper** | PSC/officers JSON scraper for lists of company numbers (built for Raphtory examples). Archived. | Simple pattern to copy, not to depend on. |
| Various notebook repos (e.g. MarckK/companies-house-api) | Jupyter notebooks looping company numbers to retrieve officer or company JSON. | Useful as small implementation examples, but maintenance, endpoint semantics, rate-limit handling and reproducibility need individual review. |

**Current assessment:** no identified tool has yet been demonstrated to satisfy the project’s complete combination of deterministic bulk input, raw-response caching, documented rule semantics, explicit unknown/data-quality states and per-company evidence output. Some projects are active, so the gap is functional rather than simply “unmaintained.” A small bespoke client may still be appropriate, but that should be decided after fixed-commit code and maintenance review rather than assumed from repository size.

---

## 4. Free / freemium products

| Product | Notes |
|---|---|
| **Companies House web service** | Free, canonical, includes free document images. No scoring. |
| **The Gazette** (thegazette.co.uk) | Official notices, including insolvency and winding-up material. It can provide a different or earlier formal event record than the company profile, but the relevant notice type, timing and reproducible acquisition/licensing route must be established before ingestion. Free web search and the commercial Data Service should be distinguished. |
| **Insolvency Service / individual insolvency register** | Official individual-insolvency records. Cross-referencing a company officer is an entity-resolution task; a name match alone is not a verified identity match. |
| **Disqualified directors register** | Official searchable register. It is a valuable formal-status source, but linking a returned person to an officer record still requires identifiers and matching QA. |
| **OpenCorporates** | Aggregated cross-jurisdiction registry data including the UK. Its main comparative value is normalisation and global entity coverage; current API eligibility, terms and limits depend on the use case and account. |
| **Endole, Company Check, Pomanda, etc.** | Freemium company-information services combining public data with varying enrichment and derived scores. Useful as product comparators, but API access, provenance and score documentation must be assessed individually. |

## 5. Commercial products

These products commonly combine registry and other public records with proprietary layers such as payment-experience data, contributed credit data, monitoring and derived scores. Exact inputs vary by provider and product tier.

| Product | Positioning | Relevance |
|---|---|---|
| **Creditsafe** | International company credit, monitoring and compliance products. | Relevant comparator for the additional private/public data and workflow sold above raw CH records. Coverage, score range, outcome definition and horizon require dated provider documentation; methodology is proprietary. |
| **Experian (Business Express / Commercial CAIS)** | UK business-credit products combining public records with contributed credit-account information. | Relevant where actual credit-account behaviour matters. Claims about network size, access and predictive performance require dated sources and independent evaluation where possible. |
| **Dun & Bradstreet** | Global company-reference, failure-risk and payment-experience products. | Useful cross-border commercial comparator. Product coverage, pricing and suitability should be recorded rather than inferred. |
| **Company Watch** | UK-focused financial-risk and distress-monitoring products, including its H-Score. | Potential comparator for explainability claims, but vendor descriptions do not establish transparency, calibration or superior performance. |
| **Red Flag Alert** | UK company-risk, insolvency and monitoring product. | Relevant monitoring comparator; feature provenance, outcome definitions and independent performance evidence need verification. |
| **FullCircl (ex-DueDil), Doorda, etc.** | API-first company data platforms for KYB/onboarding. | Relevant if embedding checks in a product rather than doing research. |

**Two caveats on commercial data:**
1. **Licensing.** Commercial licences may restrict redistribution, publication and use of scores as model-training inputs. Check the actual contract before acquisition or comparison work.
2. **Opacity.** A provider may explain the broad outcome or contributing data without exposing the full calculation, calibration or error profile. Commercial products can still add court data, contributed payment experience, cross-border normalisation or monitoring infrastructure, but vendor capability claims do not establish independent effectiveness.

---

## 6. Suggested position for this project

1. **v1:** Public Data API → registrar-recorded/derived fields → transparent rule-based flag list per company number → CSV. Every flag should map to a documented field or classified formal record and retain the raw evidence. This is traceable, but not automatically unbiased or predictively valid.
2. **v1.5:** consider Gazette notices and disqualified-director cross-checks after establishing acquisition terms, notice semantics and entity-resolution QA.
3. **v2 (only if needed):** bulk snapshot for address-frequency and population-relative features; PSC snapshot for ownership opacity flags — with documented bias caveats.
4. **Parked unless essential:** iXBRL financials (parsing cost, audit-threshold caveats), commercial scores (opacity, licensing).
5. **External comparison idea:** for a dated sample, compare the flag list with a commercial product’s classifications to identify disagreement and potentially missing data classes. This is concordance or gap analysis, not validation: the proprietary score may use a different target, private data and an unknown error profile. Validation requires a predefined outcome, information available before that outcome, temporal or entity-grouped testing, and false-positive analysis.

## Known gaps in this document

- Complete dated extractions are still needed for the ECCTA identity-verification rollout and current audit/disclosure thresholds before either is cited.
- Commercial pricing and contract terms are not covered; capture dated quotations or published terms rather than relying on historical estimates.
- No fixed-commit, hands-on evaluation of the listed open-source tools or independent evaluation of the commercial products has yet been completed.
