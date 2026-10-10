# Internal joined company table at T = 2026-09 — Stage 2

> **Internal only. Nothing is published.** These outputs are under
> `data/join/v1-internal-202609/` (gitignored). The published Kaggle accounts WIDE remains v2,
> and its documentation is unchanged.

## Point-in-time inputs

The register is the base population: 5,704,711 unique normalised company numbers from the
2026-10-01 snapshot. The left joins use PSC 2026-09-25 and the internal accounts features at
T=202609. PSC is six days before the end-of-month register boundary and therefore introduces no
look-ahead. Every input key was unique after `upper(trim(company_number))`; both outputs retain
exactly the register's 5,704,711 rows and one unprefixed `company_number` key.

The accounts boundary is a **registration-month** availability boundary:
`row_available_yyyymm <= 202609`. It is not an archive-publication boundary. The consolidated
September ZIP was published/downloadable after September ended; this join does not claim that it
was available at 2026-09-30.

Run both tiers with:

```console
ukcompany join --t 202609
```

The command resolves the first-of-next-month register, the latest PSC snapshot on or before that
date, and `data/accounts/v2-internal-202609/`. It fails on metadata/date mismatches, missing inputs,
null/blank keys, duplicate normalised keys, changed register row counts, or governed-schema leaks.

## Schema and missingness

All register, PSC and accounts attributes are prefixed `reg_`, `psc_` and `acc_`. The join adds two
unprefixed coverage flags:

- `has_psc=true` means a PSC source row matched, even if a particular PSC attribute is null.
  `false` means no source row in this PSC snapshot. Companies outside the PSC regime are one reason;
  it does not mean that a present row merely has null values.
- `has_accounts=true` means an iXBRL-derived accounts-feature row available by T matched, even if a
  particular accounts attribute is null. `false` means no such source row by T. Non-iXBRL filings
  and the documented strong size skew limit accounts coverage.

The governed output has 63 columns and excludes both companies-per-person bands and
`reg_n_companies_same_address`; this is asserted against the written Parquet schema. The
ungoverned output has 66 columns and includes those three attributes. These are attributes only:
there are no rules or composite scores.

## Coverage

All figures in this document are **internal**. The mutually exclusive combinations close exactly
to the 5,704,711-company register population:

| combination | companies | share of register |
|---|---:|---:|
| all three sources | 4,014,892 | 70.3785% |
| register + PSC only | 1,524,236 | 26.7190% |
| register + accounts only | 2,044 | 0.0358% |
| register only | 163,539 | 2.8667% |
| **total** | **5,704,711** | **100.0000%** |

Source totals within the register are 5,704,711 register, 5,539,128 PSC (97.0974%) and 4,016,936
accounts (70.4144%). The source tables additionally contain 5,392,988 PSC companies and 2,874,341
accounts companies **absent from the selected register**. That label is deliberate: absence alone
does not establish dissolution, so the join does not classify those companies as dissolved without
supporting status evidence.

### By register company type

The complete exact breakdown, including every small category, is in each `join_manifest.json`.
The material categories (at least 1,000 register companies) are:

| register company type | register | PSC | accounts | all three |
|---|---:|---:|---:|---:|
| Private Limited Company | 5,276,662 | 5,230,150 | 3,853,862 | 3,851,852 |
| Private limited by guarantee, no share capital | 118,855 | 118,589 | 94,594 | 94,568 |
| Limited Partnership | 61,086 | 20,685 | 0 | 0 |
| Limited Liability Partnership | 50,171 | 49,939 | 29,650 | 29,648 |
| Community Interest Company | 45,328 | 45,151 | 15,114 | 15,114 |
| Charitable Incorporated Organisation | 40,659 | 0 | 0 | 0 |
| Private LBG, limited-name exemption | 35,840 | 35,778 | 21,986 | 21,980 |
| Overseas Entity | 30,207 | 30,189 | 0 | 0 |
| Other company type | 15,518 | 32 | 0 | 0 |
| Registered Society | 10,757 | 0 | 0 | 0 |
| Scottish Charitable Incorporated Organisation | 7,988 | 0 | 0 | 0 |
| Private Unlimited Company | 4,722 | 4,577 | 814 | 814 |
| Public Limited Company | 4,490 | 3,697 | 896 | 896 |

### By register accounts category

| register accounts category | register | PSC | accounts | all three |
|---|---:|---:|---:|---:|
| MICRO ENTITY | 1,868,115 | 1,867,870 | 1,855,127 | 1,854,892 |
| NO ACCOUNTS FILED | 1,464,595 | 1,329,783 | 31 | 31 |
| TOTAL EXEMPTION FULL | 1,339,786 | 1,338,496 | 1,295,012 | 1,294,915 |
| DORMANT | 628,483 | 626,065 | 595,088 | 594,759 |
| UNAUDITED ABRIDGED | 165,258 | 165,237 | 163,197 | 163,178 |
| FULL | 86,925 | 75,977 | 29,150 | 29,145 |
| SMALL | 67,937 | 64,757 | 44,004 | 44,000 |
| AUDIT EXEMPTION SUBSIDIARY | 34,490 | 34,490 | 12,310 | 12,310 |
| GROUP | 28,299 | 27,104 | 13,990 | 13,989 |
| TOTAL EXEMPTION SMALL | 8,871 | 1,297 | 2,387 | 1,035 |
| MEDIUM | 6,458 | 6,259 | 5,593 | 5,591 |
| ACCOUNTS TYPE NOT AVAILABLE | 3,790 | 110 | 0 | 0 |
| AUDITED ABRIDGED | 1,143 | 1,143 | 1,002 | 1,002 |
| FILING EXEMPTION SUBSIDIARY | 531 | 531 | 41 | 41 |
| PARTIAL EXEMPTION | 27 | 9 | 4 | 4 |
| INITIAL | 3 | 0 | 0 | 0 |

## The 31-company reconciliation difference

The join correctly finds 4,016,936 accounts-feature companies in the register. Stage 1's aligned
date reconciliation reported 4,016,905 companies in its `both_present` denominator because that
calculation requires both an accounts `latest_period_end` and register `LastMadeUpDate`. The other
31 companies match by company number and have accounts features, but their register
`LastMadeUpDate` is absent. They remain in the join with `has_accounts=true`; they are neither an
error nor silently discarded. The manifest asserts `4,016,936 - 4,016,905 = 31` against the Stage 1
reconciliation report.

## Outputs and provenance

| tier | rows | columns | bytes | build time | SHA-256 |
|---|---:|---:|---:|---:|---|
| governed | 5,704,711 | 63 | 199,085,870 | 3.60s | `909414cb617ce3862954cb55dff1bde54983a7898cb7ec0c02f15026e098e031` |
| ungoverned | 5,704,711 | 66 | 206,304,904 | 3.77s | `ce016dd11307da6ae0dcd94b3c835861fe1bab2e24274ca9b1e479a2a8bffbfc` |

Combined output size is 405,390,774 bytes; measured DuckDB build time was 7.37 seconds. Each tier's
`join_manifest.json` records T, source dates, feature/report paths and SHA-256 hashes, source and
output row counts, coverage flags and breakdowns, excluded-source counts, schema assertions, output
size/hash and build time. The root manifest links both tier manifests and output hashes.

Synthetic tests cover schema prefixing and governed exclusions, presence-based coverage flags,
date pairing/no PSC look-ahead, duplicate normalised-key rejection, the CLI, and an accounts row
whose `row_available_yyyymm` is after T being excluded by the existing accounts-feature pipeline
before the join.
