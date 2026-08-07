# Open Company UK — literature and source queue

**Discovery date:** 7 August 2026  
**Repository reviewed:** [`ThomasHSimm/open-company-uk`](https://github.com/ThomasHSimm/open-company-uk) at commit [`b478513`](https://github.com/ThomasHSimm/open-company-uk/commit/b478513cee82a0a3c7b1db14c4f69b28dd43b3be)  
**Context used:** `open-uk-company-research-pack.md`

This is a **discovery queue**, not an evidence register. None of the entries should receive a
register ID until the source has been read and extracted using the appropriate §3 prompt in the
research pack. Mutable API, product, pricing and legal-transition claims need an access date in
their eventual extraction.

## Main conclusion from discovery

The strongest starting evidence is not a conventional academic literature. It is a combination
of:

1. official Companies House schemas and guidance, which establish what fields and legal states
   mean;
2. official evaluations and administrative statistics, which establish coverage, use and known
   limitations;
3. a smaller empirical literature on PSC data, filing timeliness, company-law research and
   director disqualification; and
4. investigative and vendor material, which shows possible uses but usually cannot validate an
   indicator or estimate its false-positive rate.

The current rule set should therefore be defended primarily as a transparent representation of
registrar-recorded states. The literature does **not** currently justify treating the rules as a
validated fraud, trustworthiness, credit or insolvency-prediction model.

## Recommended first extraction order

| Priority | Source | Type / evidence role | Why it should be read first | Important limit |
|---:|---|---|---|---|
| 1 | [Companies House Public Data API reference](https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference) and downloadable OpenAPI specification | Official data · `official-definition` | Canonical endpoint and resource inventory for profile, officers, charges, insolvency, filing history, PSC and disqualifications. It should anchor the data dictionary. | Defines the interface, not the accuracy of filed information or the validity of a rule. |
| 2 | [Companies House `api-enumerations`](https://github.com/companieshouse/api-enumerations) | Official repository · `official-definition` | Canonical meanings for status, PSC statement and other enumeration constants; useful for schema-drift tests and literal matching. | Extract at a fixed commit/tag; `main` is mutable. |
| 3 | [Charges list resource](https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/resources/chargelist?v=latest) | Official data · `official-definition` | Directly relevant to the current `CHARGES_OUTSTANDING` rule. Charge records have explicit `status` values including `outstanding`, `fully-satisfied`, `part-satisfied` and `satisfied`. | The presence of `links.charges` alone does not establish an outstanding charge. |
| 4 | [Companies House data products](https://www.gov.uk/guidance/companies-house-data-products), [download portal](https://download.companieshouse.gov.uk/) and [daily PSC snapshot](https://download.companieshouse.gov.uk/en_pscdata.html) | Official data · `official-definition` | Establishes monthly company snapshot, daily PSC snapshot and other bulk routes for population context. | Snapshot dates, release dates and current API retrieval times are different; products have different populations and support levels. |
| 5 | [Streaming API overview](https://developer-specs.company-information.service.gov.uk/streaming-api/guides/overview) | Official data · `official-definition` | Establishes the change-stream alternative to polling and the resources available for later monitoring work. | It is future work for this list-based v1 and should not complicate the initial implementation. |
| 6 | [Developer rate-limiting guidance](https://developer-specs.company-information.service.gov.uk/guides/rateLimiting) | Official data · `official-definition` | Supports the client design, conservative token bucket and 429 handling. | A published quota is not an uptime or service-level guarantee. |
| 7 | [Companies House PSC guidance](https://www.gov.uk/guidance/people-with-significant-control-pscs) | Official guidance · `official-definition` | Establishes applicability, PSC conditions, required statements, protection and the current identity-verification process. | Legal concepts do not map one-to-one to a claim that the natural beneficial owner has been found. |
| 8 | [Identity-verification transition plan](https://www.gov.uk/government/publications/economic-crime-and-corporate-transparency-act-outline-transition-plan-for-companies-house/economic-crime-and-corporate-transparency-act-outline-transition-plan-for-companies-house) and [approach to non-compliance](https://www.gov.uk/government/publications/companies-house-approach-to-non-compliance-with-mandatory-identity-verification/companies-house-approach-to-non-compliance-with-mandatory-identity-verification) | Official policy · `official-definition` | Needed before interpreting new officer/PSC identity-verification fields during the 2025–26 transition. | Absence of a verification field may mean not yet due, not in scope, unavailable or non-compliant; it is not a safe adverse flag by itself. |
| 9 | [Review of the implementation of the PSC Register](https://www.gov.uk/government/publications/people-with-significant-control-psc-register-review-of-implementation) (BEIS Research Paper 2019/005) | Official commissioned evaluation · `measured` | Mixed-method evidence: survey of 500 businesses plus stakeholder interviews; covers engagement, costs, use and areas for improvement. | Self-report and stakeholder evidence; not a validation of company-level adverse indicators. |
| 10 | [Second Post-Implementation Review of the PSC Regulations](https://www.legislation.gov.uk/ukia/2025/184/pdfs/ukia_20250184_en.pdf) | Official evaluation · `measured` / `interpretive` | Updates the first review and should supersede or qualify older statements about the PSC regime. | Read methodology and dates carefully; it spans a changing legal regime. |
| 11 | Jofre, M. & Knobel, A. (2025), [*Insights from the United Kingdom’s People with Significant Control register*](https://www.openownership.org/en/publications/insights-from-the-united-kingdoms-people-with-significant-control-register/) | Applied research · `measured` | The closest methodological match to the project: analyses UK PSC data, standardises it using BODS, and discusses identifiers, inactive records, ownership ranges and historical-data handling. | Analysis uses a dated republished dataset; conclusions do not automatically apply to the current API state. |
| 12 | Clatworthy, M. A. & Peel, M. J. (2016), [“The timeliness of UK private company financial reporting: Regulatory and economic influences”](https://doi.org/10.1016/j.bar.2016.05.001), *The British Accounting Review*, 48(3), 297–315 | Academic paper · `measured` | Direct evidence about UK private-company filing timeliness and regulatory deadlines. Useful for reconstructing repeat late filing and understanding alternative explanations. | It studies filing behaviour, not whether late filing predicts fraud, insolvency or untrustworthiness. |
| 13 | [Valuing the user benefits of Companies House data](https://www.gov.uk/government/publications/companies-house-data-valuing-the-user-benefits) (BEIS Research Paper 2019/015, especially Reports 2–4) | Official commissioned research · `measured` | Documents how direct users, intermediaries and public-good providers use Companies House data, including due diligence, research and law enforcement. | Willingness-to-pay and reported use establish value and use, not data correctness or indicator effectiveness. |
| 14 | [Your personal information on the Companies House register](https://www.gov.uk/guidance/your-personal-information-on-the-companies-house-register), [personal information charter](https://www.gov.uk/government/organisations/companies-house/about/personal-information-charter) and [removal guidance](https://www.gov.uk/guidance/removing-your-home-address-from-the-companies-house-register) | Official governance · `official-definition` | Essential for distinguishing Companies House’s publication duty from a downstream user’s data-protection responsibilities and for understanding suppression/removal. | Public availability is not blanket permission to republish personal data or named analytical flags without a lawful and proportionate purpose. |

## Additional UK official sources

| Source | What it can establish | Suggested treatment |
|---|---|---|
| [Companies register activities, April 2025 to March 2026](https://www.gov.uk/government/statistics/companies-register-activities-statistical-release-april-2025-to-march-2026/companies-register-activities-statistical-release-april-2025-to-march-2026) | Current register size, company-type composition, incorporations, dissolutions, liquidation and age distributions. | Extract as population context and denominator evidence; do not use national age distributions to make a two-year-old company adverse. |
| [Quality and methods guide for Companies House statistics](https://www.gov.uk/government/publications/incorporated-companies-in-the-uk-by-jurisdiction-and-month-quality-and-methods-guide/quality-and-methods-guide) | Administrative-data provenance, quality assurance, revisions and operational/statistical distinctions. | Use to shape provenance, revision and data-quality notes. |
| [Companies House annual report and accounts 2025–26](https://www.gov.uk/government/publications/companies-house-annual-report-and-accounts-2025-to-2026/companies-house-annual-report-and-accounts-2025-to-2026) | Current reform activity, identity verification, register-cleaning and operational examples. | Useful current context; agency reporting about its own performance is not independent evaluation. |
| [Companies House business plan 2026–27](https://www.gov.uk/government/publications/companies-house-business-plan-2026-to-2027/companies-house-business-plan-2026-to-2027) | Planned automated quality metrics, validation, register cleansing and cross-government data sharing. | Record as planned/claimed activity, not completed effectiveness. |
| [Late filing penalties](https://www.gov.uk/government/publications/late-filing-penalties-from-companies-house/late-filing-penalties) | Current statutory deadline and penalty rules, including special treatment of first accounts and changed accounting periods. | A required source for deadline reconstruction tests; version/date the rules and account for temporary historical changes such as COVID extensions. |
| [Companies House sandbox test-data generator](https://developer-specs.company-information.service.gov.uk/sandbox-test-data-generator-api/reference/company-test-data/create) | Supported synthetic company states and edge-case fields, including PSC, insolvency, disputed address and undeliverable address. | Useful for fixtures and capability tests; it does not prove production prevalence or semantics beyond the documented field. |
| [The Gazette: search guidance](https://www.thegazette.co.uk/all-notices/content/116), [official-record description](https://www.thegazette.co.uk/place-notice) and [Data Service](https://www.thegazette.co.uk/dataservice) | Legal/public-record role of Gazette notices and available search/commercial data routes. | Separate free web viewing/OGL content from the commercial Data Service; investigate a reproducible open acquisition route before planning ingestion. |
| [Economic Crime and Corporate Transparency Act 2023](https://www.legislation.gov.uk/ukpga/2023/56) and [explanatory notes](https://www.legislation.gov.uk/ukpga/2023/56/notes/division/3/index.htm) | Registrar objectives and legal basis for the changing role of Companies House. | Legal-definition/governance source; do not turn policy objectives into measured claims of reduced crime. |
| [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | General Crown-information reuse terms and attribution requirements. | Read alongside product-specific terms and the personal-data exclusions/caveats; do not assume every dataset or document is wholly covered. |
| [NAO, *Using data analytics to tackle fraud and error* (2025)](https://www.nao.org.uk/wp-content/uploads/2025/07/using-data-analytics-to-tackle-fraud-and-error.pdf) | Independent public-audit discussion of the value and historical limitations of Companies House data for counter-fraud analytics. | Strong limitation/context source; it does not validate this repository’s rules. |

## Evidence on uses, methods and limitations

| Source | Evidence role and relevance | Main caution |
|---|---|---|
| Open Ownership & Global Witness (2017), [*Learning the lessons from the UK’s public beneficial ownership register*](https://www.openownership.org/en/publications/learning-the-lessons-from-the-uks-public-beneficial-ownership-register/areas-for-improvement/) | `observed` bulk-data analysis; documents validation failures, anomalous dates and non-compliant ownership structures and how analysis prompted form validation changes. | Advocacy research and anomaly detection; suspicious or impossible values are not prevalence estimates of criminal ownership. |
| Global Witness, [*The companies we keep*](https://globalwitness.org/en/campaigns/corruption-and-money-laundering/the-companies-we-keep/) | `observed` use of PSC/register data to find suspicious or inaccurate records and support reform recommendations. | Selected investigative findings, not a representative validation sample. |
| Transparency International UK (2022), [*Partners in Crime*](https://www.transparency.org.uk/sites/default/files/2025-02/Partners%20in%20Crime.pdf) | `observed` use of Companies House data with more than 50 corruption and money-laundering cases to study LLP misuse. | Case-selected denominator; useful for patterns and hypotheses, not company-level probabilities. |
| Transparency International UK (2019), [*At Your Service*](https://archive.transparency.org.uk/sites/default/files/pdf/publications/TIUK_AtYourService_WEB.pdf) | `observed` investigation of UK shell companies and company-formation services. | Strong for documented mechanisms and examples, weak for general prevalence or ranking one entity type as uniquely highest risk. |
| Haans, R. F. J. & van den Oever, K. (2021), [“Foreign entrepreneurs engage in less misconduct than native entrepreneurs: Evidence from U.K. director disqualifications”](https://doi.org/10.1016/j.jbvi.2021.e00281) | `measured`; combines Companies House director data with formal disqualification outcomes and a matched comparison design. Useful for label design and the danger of intuitive demographic proxies. | Narrow outcome and study population; nationality must not become a project indicator. |
| Hardman, J. (2023), [“Empirical Evidence for the Continuing Need to ‘Think Small First’ in UK Company Law”](https://pmc.ncbi.nlm.nih.gov/articles/PMC9366833/) | `measured`/`interpretive`; demonstrates population-scale use of Companies House data for company-law research. | Research design is transferable; substantive company-law conclusions are not indicator evidence. |
| Buckley, L., Grant, G. & Hardman, J. (2025), [“The case for expanded access to corporate registry data: empirical and comparative insights”](https://www.pure.ed.ac.uk/ws/files/545715688/BuckleyEtalAJCL2025TheCaseForExpandedAccess.pdf), *Australian Journal of Corporate Law*, 40(3), 261–287 | Comparative analysis of registry access and research potential; useful for the open-data and cross-country sections. | Mainly access/governance/method evidence rather than validation of operational due-diligence flags. |
| Open Ownership (2021), [*Early impacts of public beneficial ownership registers: United Kingdom*](https://www.openownership.org/en/publications/early-impacts-of-public-beneficial-ownership-registers-uk/uk-leading-approach/) | Synthesis of documented uses of the UK register by civil society, government and the private sector. | Secondary synthesis by an advocacy organisation; follow its citations to original evidence before using load-bearing claims. |
| Open Ownership (2022), [*Measuring the economic impact of beneficial ownership transparency*](https://www.openownership.org/en/publications/measuring-the-economic-impact-of-beneficial-ownership-transparency-summary-report/what-has-already-been-done-to-measure-the-economic-impacts-of-beneficial-ownership-transparency/) | Maps evidence and measurement gaps around the economic effects of beneficial-ownership transparency. | Absence of evaluation is not ineffectiveness; avoid treating estimated aggregate value as company-level predictive performance. |
| [Value of corporate transparency in tackling economic crime: policy summary (2024)](https://assets.publishing.service.gov.uk/media/670e554d366f494ab2e7b88c/policy_summary_report_value_corporate_transparency_tackling_crime_october_2024.pdf) | Official economic assessment of the potential value of greater corporate transparency. | Policy modelling and valuation, not observed effectiveness of particular fields or rules. |

## Tool and product landscape sources

Provider pages establish capabilities and current commercial claims only. Each mutable access,
coverage or price claim should be dated. A useful review should compare provenance, raw-evidence
visibility, history, entity resolution, batch/API access, export, monitoring and whether derived
scores are inspectable.

| Tool/product | Access class | Why review it | Evidence status |
|---|---|---|---|
| [Open Ownership `bods-uk-psc-pipeline`](https://github.com/openownership/bods-uk-psc-pipeline) and [BODS specification](https://github.com/openownership/data-standard) | Open-source | Closest inspectable comparison for ingesting Companies House PSC/company data and mapping it to a standard ownership model. | Code capability; inspect at a fixed commit and test against a dated input. |
| [OpenCorporates API](https://api.opencorporates.com/documentation/API-Reference) and [UK register page](https://opencorporates.com/registers/270) | Free/open-project access plus commercial plans | Cross-jurisdiction normalisation, provenance and company-number lookup; relevant comparator for non-UK expansion. | Provider capability/claim; API terms and limits vary by account. |
| [OCCRP Aleph](https://github.com/alephdata/aleph) | Open-source | Investigative ingestion, document/structured-data search, entity cross-referencing and provenance. | Inspectable capability, not a list-screening product or validation of matching accuracy. |
| [OpenSanctions `yente`](https://github.com/opensanctions/yente) | Open-source core; hosted API has separate access terms | Reusable entity matching/search architecture, batch queries and explicit match thresholds. Relevant future method source for cross-register matching. | Capability; matching performance depends on data and evaluation design. Out of scope for v1. |
| [Companies House MCP server](https://github.com/stefanoamorelli/companies-house-mcp) | Open-source community tool | A direct comparator showing broad endpoint exposure through an agent interface. | Capability only; not official, and an LLM/agent path should not replace the deterministic batch pipeline. |
| [Endole API documentation](https://www.endole.co.uk/developers/dashboard/api/documentation/) | Freemium/commercial | UK company enrichment and pay-per-call access; useful for identifying what convenience/derived fields are sold above raw Companies House data. | Provider claim; provenance, scoring method and current pricing require verification. |
| [Beauhurst Companies API](https://beauhurst.readme.io/reference/v1-1) and [G-Cloud service description](https://www.applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/683445940907143) | Commercial | Enriched UK company, transaction, people and news data, including lookup by Companies House ID. | Provider claim; broader product purpose than transparent register-only indicators. |
| [Creditsafe Connect API](https://www.creditsafe.com/gb/en/enterprise/integrations/company-data-api.html) | Commercial | Shows how official registry data is combined with credit scores, compliance data, monitoring and other private sources. | Provider claim; opaque/commercial scores are explicitly non-transferable to v1. |
| [Moody’s Orbis](https://www.moodys.com/web/en/us/capabilities/company-reference-data/orbis.html) | Commercial | Major cross-country private-company and ownership comparator, including corporate trees and normalisation. | Provider claim; data, calculation and licensing are not reproducible from free UK sources. |
| [FullCircl business-search API](https://docs.fullcircl.com/reference/post_business-search) | Commercial | KYB-oriented global business lookup and normalised status/identifier fields. | Provider capability; inspect actual source provenance and evidence exposure rather than assuming “official status” means verified. |

## Non-UK and cross-border comparison queue

These sources are for ecosystem comparison and future mapping, not production ingestion in v1.
They demonstrate that “company-register data” is not one internationally consistent object.

| Jurisdiction/system | Official source | Comparison value | Main non-comparability |
|---|---|---|---|
| Norway | [Brønnøysund Register Centre datasets and API](https://www.brreg.no/en/use-of-data-from-the-bronnoysund-register-centre/datasets-and-api/) and [OpenAPI documentation](https://data.brreg.no/enhetsregisteret/api/dokumentasjon/no/index.html) | Strong open-data comparator: search APIs, complete downloads, roles and beneficial-owner datasets under an open-government-data licence. | Entity types, person-role access rules and national identifiers differ from Companies House. |
| Estonia | [e-Business Register open-data/API information](https://www.rik.ee/en/e-business-register/company-registration-api) and [official register](https://ariregister.rik.ee/) | Machine-readable JSON/XML downloads across companies, associations, foundations and public bodies. | Coverage and identity infrastructure reflect Estonian law and digital-ID systems. |
| New Zealand | [Companies Office data access routes](https://www.companiesoffice.govt.nz/data-services/ways-to-get-our-data/), [APIs](https://www.companiesoffice.govt.nz/data-services/ways-to-get-our-data/using-our-data-through-apis/) and [NZBN API](https://www.nzbn.govt.nz/using-the-nzbn/nzbn-services/api/) | Useful comparison of individual search, bulk access and business identifiers beyond incorporated companies. | NZBN population includes entity types and voluntary registrations not equivalent to the UK company register. |
| Canada (federal corporations) | [Corporations Canada data services](https://ised-isde.canada.ca/site/corporations-canada/en/data-services) and [JSON API](https://ised-isde.canada.ca/site/corporations-canada/en/accessing-federal-corporation-json-datasets) | Open dataset and real-time API with status, addresses, directors, annual returns and event history. | Covers federally incorporated entities, not all Canadian provincial/territorial companies. |
| European Union | [EU business-register search](https://e-justice.europa.eu/topics/registers-business-insolvency-land/business-registers-search-company-eu_en) and [BRIS description](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/blog/2017/09/19/533365899/Business%2BRegister%2BInterconnection%2BSystem%2BBRIS) | Cross-border discovery and the European Unique Identifier/interconnection model. | BRIS connects national registers; it is not a harmonised open bulk company/beneficial-ownership database. |
| United States (federal securities filings) | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [data.sec.gov](https://data.sec.gov/) | Exemplary open submissions/XBRL API and bulk-file design for reporting companies. | EDGAR is a securities-filing system, not a national register of all US companies; state incorporation remains fragmented. |
| Global LEI system | [GLEIF API](https://www.gleif.org/en/lei-data/gleif-api), [access and use](https://www.gleif.org/en/lei-data/access-and-use-lei-data) and [Level 2 ownership data](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-who-owns-whom) | Open, standardised cross-border legal-entity identifiers, mapped identifiers and direct/ultimate-parent relationships. | LEI coverage is selective and relationship reporting contains exceptions; it is not a comprehensive company register. |
| Denmark | [Danish Business Authority / CVR](https://danishbusinessauthority.dk/) and [EU e-Justice country description](https://e-justice.europa.eu/topics/registers-business-insolvency-land/business-registers-eu-countries/dk_en) | Strong jurisdiction for comparing company, accounting, management and ownership disclosure. | The English overview is not enough for a technical access extraction; obtain the current Danish data/API documentation before recording access claims. |

## Immediate implications for the current repository

### 1. `CHARGES_OUTSTANDING` is not supported by the field currently used

The rule fires when `links.charges` is present. The official charge-list schema exposes each
charge’s actual `status`, including `outstanding`, `fully-satisfied`, `part-satisfied` and
`satisfied`. A link therefore means “a charges resource is available”, not “an outstanding charge
exists”. Until the charge resource is fetched, the defensible attribute/rule name is closer to
`CHARGES_RECORDED` or `CHARGES_RESOURCE_PRESENT`. This is a schema correction, not a literature
judgement.

### 2. Unclassified insolvency should not silently become a high-severity company state

`INSOLVENCY_ADVERSE` currently fires as high when insolvency is indicated but case data are not
cached. That can combine two different states: a genuinely adverse case and an unfetched or
unclassified case, including a possible members’ voluntary liquidation. The research-pack
guardrail is right: fetch/data incompleteness should remain a data-quality state. Prefer fetching
and classifying the cases; if still unavailable, emit an `unknown/unclassified` diagnostic rather
than an adverse conclusion.

### 3. Indicator severity remains an analytical judgement

Official documentation can establish that accounts are overdue, a strike-off proposal is active,
or an address is disputed/undeliverable. It does not establish that `high`, `medium` or `low` is a
validated universal ranking. Keep severity explicitly scoped to the seriousness of the recorded
formal state and do not imply a probability of fraud, insolvency or loss.

### 4. The SLP wording needs softer treatment or comparative evidence

Transparency International and related investigations provide strong evidence that SLPs have been
used in significant money-laundering cases and that ownership transparency has been weak. They do
not, without a representative comparison and denominator, establish that SLPs are *the*
“highest-risk vehicle for concealed ownership”. “Documented as repeatedly misused in selected
investigations” is supportable; a superlative risk ranking is not yet supported.

### 5. Identity-verification missingness is transitional

The 2025–26 guidance shows phased legal obligations and role-specific due periods. Preserve the
current repository’s distinction between verification, a filed verification statement and a due
date. Do not turn absence of an `identity_verification_details` block into non-compliance without
establishing applicability and timing.

## Gaps still worth searching

1. **Prospective validation of register-only indicators.** Search for studies that predict a
   clearly dated outcome using only information available before that outcome, with temporal or
   entity-grouped validation and a simple baseline. Much company-failure literature uses private
   financial/credit data and will not transfer to v1.
2. **False-positive analysis for address concentration.** Find population-based studies that
   distinguish formation agents, accountants, virtual offices and legitimate group structures
   from abusive address reuse.
3. **Strike-off trajectories.** Look for administrative research on active proposals that are
   discontinued versus completed, by reason and company type. A current proposal is a real state,
   but its downstream meaning is not yet quantified here.
4. **Historical deadline reconstruction.** Locate archived statutory guidance and COVID filing
   extension rules, then construct regime-dated unit tests rather than applying today’s deadline
   retrospectively.
5. **Registered-office dispute/undeliverable fields.** Obtain the exact legal/operational guidance
   for who sets each flag, what evidence triggers it, when it clears and how historical changes are
   represented.
6. **Entity-resolution evaluation.** Before any officer graph or sanctions cross-check, find
   measured precision/recall work using company numbers, officer IDs, dates of birth and addresses;
   names alone are not stable linkage.
7. **Commercial product provenance and evaluation.** Vendor pages describe capability. Search for
   independent audits, benchmark datasets or procurement evaluations before claiming that a paid
   product improves accuracy or outcomes.

## Suggested next action

Start with separate §3A extractions for the API/OpenAPI specification, `api-enumerations`, charges,
bulk data products and PSC/identity-verification guidance. Then extract the 2019 and 2025 PSC
reviews and Jofre & Knobel (2025) under §3D. This gives enough evidence to build the first register
without allowing the advocacy reports or vendor landscape to define production rules.
