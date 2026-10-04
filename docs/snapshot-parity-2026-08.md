# Snapshot feature parity vs derive_profile (2026-08-01)

API-cached companies with a profile: **1,013**; in both the cache and the snapshot feature table (parity set): **714**; in cache but not the snapshot: **299**.

API cache fetch dates span **2026-08-03 → 2026-08-07**; snapshot date **2026-08-01**.

## Agreement per feature

| feature | compared | agree | agree % |
|---|---:|---:|---:|
| `date_of_creation` | 714 | 709 | 99.30% |
| `age_months` | 714 | 709 | 99.30% |
| `n_previous_names` | 714 | 689 | 96.50% |
| `sic_sections` | 714 | 691 | 96.78% |
| `has_charges` | 714 | 714 | 100.00% |
| `accounts_overdue` | 714 | 696 | 97.48% |
| `confirmation_statement_overdue` | 714 | 694 | 97.20% |

## Disagreement timing & direction

| feature | disagree | cache newer | cache older | same day |
|---|---:|---:|---:|---:|
| `date_of_creation` | 5 | 5 | 0 | 0 |
| `age_months` | 5 | 5 | 0 | 0 |
| `n_previous_names` | 25 | 25 | 0 | 0 |
| `sic_sections` | 23 | 23 | 0 | 0 |
| `accounts_overdue` | 18 | 18 | 0 | 0 |
| `confirmation_statement_overdue` | 20 | 20 | 0 | 0 |

## Findings

- **96 of 96** disagreements have the API cache newer than the snapshot (it was fetched a few days later); none have it older. All are consistent with change in that window, not a definition difference.
- **5 of 5** `date_of_creation` disagreements have the API value missing while the bulk carries a date. These are Charitable Incorporated Organisations (`charitable-incorporated-organisation` / `scottish-charitable-incorporated-organisation`): the API profile omits `date_of_creation` for CIOs, the bulk file records it. A source field-availability difference, not a parsing error (and it carries into `age_months`, which derives from it).
- `n_previous_names`, `sic_sections` and the two overdue flags differ only where the company changed (a rename, a SIC change, or a due date passing) in the gap between the snapshot and the API fetch.

## Vocabulary cross-tabs (not equality-compared)

`company_status` and `company_type` use different vocabularies in the register (category text) and the API (slug). Top (API, snapshot) value-pairs in the overlap, to show they correspond:

**company_status**

| API | snapshot | n |
|---|---|---:|
| active | Active | 499 |
| liquidation | Liquidation | 197 |
| administration | In Administration | 6 |
| None | Active | 5 |
| active | Active - Proposal to Strike off | 3 |
| liquidation | Active | 2 |
| dissolved | Liquidation | 1 |
| registered | Active | 1 |

**company_type**

| API | snapshot | n |
|---|---|---:|
| ltd | Private Limited Company | 680 |
| limited-partnership | Limited Partnership | 9 |
| llp | Limited Liability Partnership | 7 |
| private-limited-guarant-nsc | PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital) | 4 |
| charitable-incorporated-organisation | Charitable Incorporated Organisation | 4 |
| private-limited-guarant-nsc-limited-exemption | PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption) | 3 |
| private-limited-guarant-nsc | Community Interest Company | 3 |
| private-unlimited | Private Unlimited Company | 1 |
