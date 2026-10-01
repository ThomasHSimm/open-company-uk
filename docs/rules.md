# Indicator rules

*Generated from `src/ukcompany/rules.py` - do not edit by hand.*

Indicators are built from registrar-recorded statuses, events and filing-compliance
fields (Companies House registers most information without verifying it). Source events
are recorded facts; rule definitions, thresholds, severities and any aggregation are
documented analytical judgements. Every indicator is traceable to specified source
fields or events and a documented transformation.
Severity grades the SERIOUSNESS of the recorded state, not confidence in it
(confidence belongs in evidence and caveats): `high` = registrar-recorded adverse
status or event; `medium` = compliance failure (missed statutory deadline or
registrar-set problem flag); `low` = minor compliance irregularity - a recorded
incomplete or unresolved statutory obligation, less serious than a missed deadline;
`info` = context, excluded from every aggregate count. Dissolved/converted/closed
companies are handled as exclusions (not screenable), not as flags.

| rule_id | severity | tier | definition | caveats |
|---|---|---|---|---|
| STATUS_INSOLVENT | high | 1 | `company_status` is one of ['administration', 'insolvency-proceedings', 'liquidation', 'receivership', 'voluntary-arrangement'], except where the status is `liquidation` and all cached insolvency cases are solvent types (see SOLVENT_WINDING_UP). | Registrar-recorded status from formal proceedings. |
| STATUS_STRIKEOFF | high | 1 | `company_status_detail` = `active-proposal-to-strike-off`. | Often triggered by non-filing; can be discontinued. Still a strong current-state signal. |
| INSOLVENCY_ADVERSE | high | 1 | Insolvency resource (linked from the profile via `links.insolvency`, fetched and cached) contains at least one case whose type is not a solvent winding-up; or insolvency is indicated on the profile but no case data is cached (fires as 'unclassified'). | Case types listed in evidence. Members' voluntary liquidation is classified as solvent and never triggers this rule. The `has_insolvency_history`/`has_been_liquidated` booleans are deprecated per the spec and used only as fallback indicators for older cached responses. |
| SOLVENT_WINDING_UP | info | 1 | All cached insolvency cases are solvent types (members-voluntary-liquidation). | Routine for retirement/reorganisation - context, not an adverse event. Never counts toward totals. |
| ACCOUNTS_OVERDUE | medium | 1 | `accounts.next_accounts.overdue` = true (falling back to the deprecated `accounts.overdue` for older cached responses). Computed by Companies House against the statutory deadline. | Correlates with company size/admin resources, not only distress. |
| CS_OVERDUE | medium | 1 | `confirmation_statement.overdue` = true. | As ACCOUNTS_OVERDUE. |
| ADDR_DISPUTE | medium | 1 | `registered_office_is_in_dispute` = true or `undeliverable_registered_office_address` = true. | Registrar-set flags (ECCTA powers). Evidence names which flag fired. |
| CHARGES_OUTSTANDING | info | 1 | `links.charges` present on the profile (the deprecated `has_charges` boolean is a fallback for older cached responses). | Normal for financed businesses - context, not risk. Never counts toward totals. |
| YOUNG_COMPANY | info | 1 | Age at observation date < 24 months, derived from `date_of_creation` and the response's fetch timestamp. | Derived transformation, not a registrar event. Context only; penalises legitimate startups if misused. Never counts toward totals. |
| PSC_UNRESOLVED | low | 1 | `active_psc_statement_codes` contains any of `steps-to-find-psc-not-yet-completed`, `psc-exists-but-not-identified` or `psc-details-not-confirmed`, or their `-partnership` variants (the Scottish Limited Partnership form of the same condition) - verbatim official statement constants from the persons-with-significant-control-statements resource; ceased statements are excluded. | PSC identification is mid-rollout under ECCTA; an unresolved statement is a transparency gap, not proof of wrongdoing. Statement constants are matched literally - official spellings (incl. any upstream misspellings) are never normalised. Evidence names which statement(s) fired. SLP `-partnership` statements are included because SLPs are a high-risk concealed-ownership vehicle. |
