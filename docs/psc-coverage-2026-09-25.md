# PSC bulk-snapshot coverage vs the register (2026-09-25 snapshot)

PSC snapshot: **2026-09-25**. Register: Basic Company Data one-file, **2026-09-01**. Join key: company number. Aggregates only.

- Register companies: **5,689,366**
- Feature-table companies (any PSC record in the snapshot): **10,932,116**
- Register companies **covered** (have a PSC row): **5,536,892** (**97.32%**)
- Register companies **uncovered**: **152,474**
- Register **Active**-status companies covered: **5,049,044 / 5,171,599** (**97.63%**)
- Snapshot companies **absent from the register** (dissolved / historical): **5,395,224**

## Uncovered register companies by company type

| CompanyCategory | register | covered | uncovered | uncovered % |
|---|---:|---:|---:|---:|
| Charitable Incorporated Organisation | 40,416 | 0 | 40,416 | 100.0% |
| Limited Partnership | 61,003 | 20,637 | 40,366 | 66.2% |
| Private Limited Company | 5,261,978 | 5,227,892 | 34,086 | 0.6% |
| Other company type | 15,508 | 32 | 15,476 | 99.8% |
| Registered Society | 10,811 | 0 | 10,811 | 100.0% |
| Scottish Charitable Incorporated Organisation | 7,923 | 0 | 7,923 | 100.0% |
| Royal Charter Company | 909 | 0 | 909 | 100.0% |
| Public Limited Company | 4,506 | 3,715 | 791 | 17.6% |
| Investment Company with Variable Capital | 637 | 0 | 637 | 100.0% |
| United Kingdom Economic Interest Grouping | 263 | 0 | 263 | 100.0% |
| Limited Liability Partnership | 50,333 | 50,136 | 197 | 0.4% |
| Industrial and Provident Society | 159 | 0 | 159 | 100.0% |
| Private Unlimited Company | 4,713 | 4,569 | 144 | 3.1% |
| PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital) | 118,771 | 118,652 | 119 | 0.1% |
| Investment Company with Variable Capital(Umbrella) | 67 | 0 | 67 | 100.0% |
| PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption) | 35,964 | 35,916 | 48 | 0.1% |
| Old Public Company | 30 | 0 | 30 | 100.0% |
| Community Interest Company | 44,829 | 44,817 | 12 | 0.0% |
| Investment Company with Variable Capital (Securities) | 8 | 0 | 8 | 100.0% |
| Other Company Type | 3 | 0 | 3 | 100.0% |
| Protected Cell Company | 3 | 0 | 3 | 100.0% |
| Further Education and Sixth Form College Corps | 2 | 0 | 2 | 100.0% |
| Overseas Entity | 30,184 | 30,182 | 2 | 0.0% |
| PRIV LTD SECT. 30 (Private limited company, section 30 of the Companies Act) | 15 | 14 | 1 | 6.7% |
| Converted/Closed | 1 | 0 | 1 | 100.0% |
| Private Unlimited | 85 | 85 | 0 | 0.0% |
| United Kingdom Societas | 6 | 6 | 0 | 0.0% |
| Scottish Partnership | 239 | 239 | 0 | 0.0% |

> **Reading this.** The register contains no dissolved companies, so the snapshot companies absent from it are dissolved / struck-off entities whose PSC records the snapshot still carries. Company types shown ~100% uncovered (Charitable Incorporated Organisations, Registered Societies, Scottish CIOs, Royal Charter companies, Investment Companies with Variable Capital, UK Economic Interest Groupings, Industrial & Provident Societies) are **outside the PSC regime** - they have no PSCs to file, so their absence is expected. PSC-regime types (private limited, LLP, PLC, CIC, guarantee companies, overseas entities) are near-fully covered. Uncovered counts are a data-completeness measure, not a compliance finding.
