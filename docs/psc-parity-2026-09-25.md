# PSC bulk-vs-API feature parity (2026-09-25 snapshot)

API-cached companies: **1,013**. Of these, **999** are also in the bulk feature table (the parity set); **14** are not (of which **0** have live PSCs in the API - a temporal / coverage gap). Markdown is aggregates only; per-disagreement detail (company number, fetch date, direction) is in the `.json` sidecar.

API cache fetch dates span **2026-08-03 → 2026-08-07**; snapshot date **2026-09-25**.

## Agreement per feature (parity set)

| feature | compared | agree | agree % |
|---|---:|---:|---:|
| `psc_n_records` | 999 | 998 | 99.90% |
| `psc_n_ceased` | 999 | 997 | 99.80% |
| `psc_natures_of_control` | 999 | 997 | 99.80% |
| `psc_max_ownership_band` | 999 | 999 | 100.00% |
| `psc_max_voting_band` | 999 | 998 | 99.90% |
| `psc_has_appointment_rights` | 999 | 998 | 99.90% |
| `psc_has_significant_influence` | 999 | 999 | 100.00% |
| `psc_n_distinct_natures` | 999 | 997 | 99.80% |
| `psc_n_individual` | 999 | 998 | 99.90% |
| `psc_n_corporate` | 999 | 999 | 100.00% |
| `psc_n_legal_person` | 999 | 999 | 100.00% |
| `psc_n_super_secure` | 999 | 999 | 100.00% |
| `psc_corporate_reg_numbers` | 999 | 999 | 100.00% |
| `psc_n_corporate_uk_format_regno` | 999 | 999 | 100.00% |
| `psc_unmapped_natures` | 999 | 999 | 100.00% |
| `n_psc_id_verified` | 999 | 998 | 99.90% |
| `n_psc_id_verification_due` | 999 | 946 | 94.69% |
| `n_psc_id_statement_filed` | 999 | 946 | 94.69% |
| `active_psc_statement_codes` | 999 | 999 | 100.00% |
| `psc_information_state` | 999 | 999 | 100.00% |

## Disagreement timing & direction

For each disagreeing feature: how the API cache's fetch date sits relative to the snapshot, and which source carried the larger value.

| feature | disagree | cache newer | cache older | same day | api larger | bulk larger |
|---|---:|---:|---:|---:|---:|---:|
| `psc_n_records` | 1 | 0 | 1 | 0 | 0 | 1 |
| `psc_n_ceased` | 2 | 0 | 2 | 0 | 0 | 2 |
| `psc_natures_of_control` | 2 | 0 | 2 | 0 | 2 | 0 |
| `psc_max_voting_band` | 1 | 0 | 1 | 0 | 0 | 0 |
| `psc_has_appointment_rights` | 1 | 0 | 1 | 0 | 0 | 0 |
| `psc_n_distinct_natures` | 2 | 0 | 2 | 0 | 2 | 0 |
| `psc_n_individual` | 1 | 0 | 1 | 0 | 1 | 0 |
| `n_psc_id_verified` | 1 | 0 | 1 | 0 | 0 | 1 |
| `n_psc_id_verification_due` | 53 | 0 | 53 | 0 | 53 | 0 |
| `n_psc_id_statement_filed` | 53 | 0 | 53 | 0 | 53 | 0 |

## ECCTA accumulating-count monotonicity check

Hypothesis: `n_psc_id_verified` and `n_psc_id_statement_filed` only accumulate over time, so whichever of (API cache, snapshot) is later must not carry fewer. A violation is the later source carrying the smaller count. Broken down by feature:

| feature | disagreements checked | violations |
|---|---:|---:|
| `n_psc_id_verified` | 1 | 0 |
| `n_psc_id_statement_filed` | 53 | 53 ⚠️ |

> `n_psc_id_verification_due` is excluded: a 'due' is cleared when verification completes, so it legitimately falls over time.

**Finding.** All 53 violations are on `n_psc_id_statement_filed` (53 with the API cache older than the snapshot, i.e. the count *fell* between the cache date and the snapshot), and 0 of the 53 affected companies have any PSC membership change. `n_psc_id_verified` (block presence, which does not un-happen) shows **no** violations. This falsifies the accumulation assumption for `n_psc_id_statement_filed` specifically: `appointment_verification_statement_date` reflects the *current* ECCTA verification cycle and is cleared/reset when the cycle rolls, so like `n_psc_id_verification_due` it is **not** a cumulative total. It is a point-in-time field, not a parity defect — the feature logic is identical across paths (confirmed by the synthetic unit test).

