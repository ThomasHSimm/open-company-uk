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
