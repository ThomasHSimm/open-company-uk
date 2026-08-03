# Data dictionary: derived company attributes

*Generated from `src/ukcompany/derive.py` - do not edit by hand.*

Verification tier is a property of each field: 1 = registrar-recorded status/event/
compliance field; 2 = filed-but-constrained; 3 = self-declared, weakly constrained.
Companies House registers most information without verifying it; no field is
described as verified.

| field | tier | source | definition | caveats |
|---|---|---|---|---|
| company_number | 1 | profile:company_number | Registrar-assigned identifier. |  |
| observed_at | 1 | cache envelope fetched_at | Timestamp of the cached API response all values derive from. | Distinct from event dates and from any bulk snapshot_date. |
| company_name | 3 | profile:company_name | Registered name. | No constraint on describing activity. |
| company_status | 1 | profile:company_status | Registrar-recorded status from formal events. |  |
| company_status_detail | 1 | profile:company_status_detail | Status detail, e.g. active-proposal-to-strike-off. |  |
| company_type | 1 | profile:type | Legal form, assigned at registration. |  |
| jurisdiction | 1 | profile:jurisdiction | Registering jurisdiction. |  |
| date_of_creation | 1 | profile:date_of_creation | Incorporation date. | Shelf companies mean age is not trading history. |
| age_months | 1 | derived | Whole months from date_of_creation to observed_at. | Derived transformation, not a registrar event. |
| sic_codes | 3 | profile:sic_codes | Self-declared nature-of-business codes. | Never verified; often stale; catch-all codes common; measurement error is non-random (newer/smaller/agent-formed companies noisier). |
| n_previous_names | 1 | profile:previous_company_names | Count of recorded previous names. |  |
| accounts_overdue | 1 | profile:accounts.next_accounts.overdue (fallback deprecated accounts.overdue) | CH-computed overdue flag vs statutory deadline. | Correlates with company size/resources, not only distress. |
| last_accounts_type | 2 | profile:accounts.last_accounts.type | Category of last filed accounts (micro-entity/small/full/dormant/...). | Reflects the company's disclosure choice within size thresholds; a size signal, not a risk signal. |
| has_charges_link | 1 | profile:links.charges | Charges resource exists for the company. | Presence of registered charges is normal for financed businesses. |
| has_insolvency_link | 1 | profile:links.insolvency | Insolvency resource exists for the company. | Case types must be classified before severity: MVL is solvent. |
| has_charges | 1 | profile:has_charges (deprecated) | Deprecated boolean; retained as fallback for older cached responses. | Spec: 'Please use links.charges'. |
| has_insolvency_history | 1 | profile:has_insolvency_history (deprecated) | Deprecated boolean; fallback only. | Spec: 'Please use links.insolvency'. |
| insolvency_case_types | 1 | insolvency:cases[].type | Distinct case types on the fetched insolvency resource. | members-voluntary-liquidation is a solvent winding-up. |
| registered_office_is_in_dispute | 1 | profile:registered_office_is_in_dispute | Registrar-set dispute flag (ECCTA powers). |  |
| undeliverable_registered_office_address | 1 | profile:undeliverable_registered_office_address | Registrar-set undeliverable-address flag. |  |
| office_postcode | 2 | profile:registered_office_address | Registered office postcode. | Shared/agent addresses are common and legitimate; address-derived features proxy socioeconomic geography. |
| excluded_status | 1 | derived from company_status | True when status is dissolved/converted-closed/closed/removed: not screenable, reported separately. |  |
| n_corporate_annotations | 1 | profile:corporate_annotation[] | Count of registrar-published corporate annotations (messages by Companies House about the company or its information). | Rare; types in corporate_annotation_types. Semantically adjacent to the address-dispute flags - review when present. |
| partial_data_available | 1 | profile:partial_data_available | Set when Companies House is not the primary data source for this company (e.g. FCA, Department for the Economy). | Completeness caveat: other indicators are weaker where this is set. |
| date_of_cessation | 1 | profile:date_of_cessation | Date the company was converted/closed, dissolved or removed (see company_status for which). |  |
| ard_day / ard_month | 1 | profile:accounts.accounting_reference_date | Accounting reference date (day, month). | Captured now as the anchor for phase-1.2 deadline reconstruction. |
| next_accounts_period_end | 1 | profile:accounts.next_accounts.period_end_on | Last day of the next accounting period to be filed. | Captured for phase-1.2 deadline reconstruction. |
| n_officers_total | 2 | officers:items[] (paginated, merged) | Total officer appointments on record (active + resigned). | Officer identities historically unverified; ECCTA identity verification is mid-rollout (2025-2026), so this is filed-but-constrained, not verified. Count of appointments, not distinct persons. |
| n_officers_active | 2 | officers:items[] with no resigned_on | Appointments with no resignation date recorded. | Missing resigned_on is read as active; older records omit dates. |
| n_officers_resigned | 2 | officers:items[] with resigned_on | Appointments carrying a resignation date. | Depends on resigned_on being filed; tolerated absent. |
| n_appointments_last_24m | 2 | derived from officers:items[].appointed_on | Appointments dated within 24 months before observed_at. | Windowed against the response fetched_at, not now. appointed_on tolerated absent (not counted). |
| n_resignations_last_24m | 2 | derived from officers:items[].resigned_on | Resignations dated within 24 months before observed_at. | Windowed against the response fetched_at, not now. |
| officer_churn_24m | 2 | derived | n_appointments_last_24m + n_resignations_last_24m. | A movement count, not a risk signal; high churn is normal for some legitimate structures. Attribute only - no rule keys off it in this phase. |
| psc_fetch_status | 1 | pipeline state (PSC list endpoint fetch outcome) | ok / not_found / not_fetched for the persons-with-significant-control list resource. | PIPELINE STATE, never a company signal: it records whether we fetched the resource, not anything about the company. Never appears as flag evidence. The company's PSC posture is psc_information_state + active_psc_statement_codes. |
| psc_n_records | 1 | psc:items[] | Count of PSC records on the list resource (active + ceased). | None (not 0) when the list was not fetched, so a missing fetch is not read as 'no PSCs'. 0 on a cached 404 (legitimately none filed). |
| psc_n_ceased | 1 | psc:items[] with ceased_on | PSC records carrying a ceased_on date. | Ceased PSCs are historical; active beneficial ownership is n_records - n_ceased. |
| active_psc_statement_codes | 1 | psc_statements:items[].statement where ceased_on absent | Comma-joined verbatim statement constants for statements with no ceased_on (e.g. steps-to-find-psc-not-yet-completed). | VERBATIM official values from psc_descriptions.yml, incl. upstream misspellings - never normalised, because rules match these literals. Ceased statements excluded. |
| psc_information_state | 1 | derived from psc + psc_statements | identified (>=1 active PSC record) / statement_only (no records, >=1 active statement) / none_reported (neither) / unknown (a resource not fetched). | Derived transformation over both PSC resources. 'unknown' is fetch incompleteness, distinct from 'none_reported'. |
