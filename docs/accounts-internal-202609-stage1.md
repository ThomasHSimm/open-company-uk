# Internal accounts extension through 2026-09 — Stage 1

> **Internal only. Not the published Kaggle dataset.** Published accounts WIDE remains v2 through
> 2026-08. Nothing in this run was copied to Kaggle or a staging directory. Internal artifacts are
> under `data/accounts/v2-internal-202609/` and are gitignored.

## Baseline and parser provenance

The run started from `main` at `32be69eebe208377c35e806e2b43615ba87aa770` on branch
`feature/handoff-10-stage1-202609`. The parser, XML adapter, pivot and reviewed column map are byte-
for-byte the same Git objects as accounts-parser v2 commit
`2e0ca8a889db3fedd51e8e843d9fa33209f32a46`:

| file | Git object at HEAD and `2e0ca8a` |
|---|---|
| `src/ukcompany/accounts/core.py` | `8b207833f7aa6bf214b776fe9e4789d32d49fb27` |
| `src/ukcompany/accounts/extract.py` | `1f94340f5f7ca12e4115ecb344947bff71164e48` |
| `src/ukcompany/accounts/xml_adapter.py` | `908b0f48e8047faffa49706c491286ab764927f6` |
| `src/ukcompany/accounts/pivot.py` | `95288f5804271817dd16ae3508a7a2f11bf5a822` |
| `config/accounts-wide-columns.json` | `4080f81b37d9be4190a18efa9ece28bead9a9a27` |

The actual v2 baseline used here is the newer parser-v2 build described in
`docs/accounts-parser-check.md`: 33,733,097 `as_first_reported` rows and 36,931,122 `latest` rows.
The older 33,513,017 / 36,710,673 figures in the original rebuild note refer to the pre-parser-v2
build, not `data/accounts/v2/`.

Published-v2 SHA-256 values, rechecked after the internal build:

| file | SHA-256 |
|---|---|
| `accounts-wide-as_first_reported.parquet` | `b2fe4eeae3e9e95dfaf7c18ef8bd53d40cb834375deae2b0fb6341026fadbbc3` |
| `accounts-wide-provenance-as_first_reported.parquet` | `e9904272fd3db45aaa49e3dcd9bc9dc6898e5967053e9c2a7e722db84bea51a0` |
| `accounts-wide-latest.parquet` | `ce62def86287001a7c8fc136c207f3736f4ec8a0104d7a783ed9beab79a5e37a` |
| `accounts-wide-provenance-latest.parquet` | `dc682da207243e1bea8da731d79fcd26e8eba54b42a126228415dc241dc5a1db` |

## Archive-month cutoff finding

The Companies House [monthly product page](https://download.companieshouse.gov.uk/en_monthlyaccountsdata.html)
says the filename identifies the month/year the data relates to, but a new monthly file is added
within five working days **after** the previous month ends. The
[daily product page](https://download.companieshouse.gov.uk/en_accountsdata.html) is more precise:
each daily file contains accounts data registered on the previous day (with the Tuesday weekend
exception). The September object returned `Last-Modified: Fri, 09 Oct 2026 09:00:08 GMT` when
checked on 9 October.

Therefore archive month M is a month-grained **registration-month** boundary; the consolidated
monthly ZIP is not itself downloadable by the end of M. This build retains the project's specified
`row_available_yyyymm <= T` convention, so T means registered in or before month T, not “the monthly
ZIP had already been released by T”. A strict artifact-publication timestamp would require daily
archives (and would retain a next-morning edge for the final day) or would lag the monthly archive.

## September source and LONG

- URL/object: `Accounts_Monthly_Data-September2026.zip`, 3,361,700,393 bytes.
- SHA-256: `f3b281232ab6f9370a6449498af45e98c68d09549a1ba64d4e75090b9bdf6c75`.
- Full CRC test: passed; 382,323 unique members, no duplicate names (381,973 HTML, 350 nested ZIP).
- Only September was parsed. The internal LONG uses links to the 152 unchanged v2 monthly files plus
  one new `accounts-long-2026-09.parquet` (216,803,386 bytes; SHA-256
  `cd78e1ceb9fc58852dd17abbd3fec0313bd54501924931652df4674ae79a0567`).
- September manifest: 382,323 members, 23,525,366 exported observations, complete and reconciled.
- Extraction: 10m25s wall, 2.49 GiB peak RSS, disposable-store mode.

September is a normal deadline peak: 382,323 members are 39.2% above the April–August 2026 mean
(274,748), 45.2% above that period's median (263,295), but only 1.39% above September 2025
(377,098). Its 23,525,366 observations are only 0.23% above September 2025.

## Internal WIDE outputs

| mode | WIDE rows | provenance rows | WIDE bytes | provenance bytes | build |
|---|---:|---:|---:|---:|---|
| `as_first_reported` | 34,114,584 | 199,580,207 | 716,234,482 | 628,989,416 | 14m12s, 13.8 GB peak |
| `latest` | 37,326,988 | 228,321,746 | 791,079,693 | 672,582,206 | 22m26s, 19.2 GB peak |

The first `latest` attempt failed cleanly at the 12 GB DuckDB limit before producing a usable file;
the successful retry used a 16 GB DuckDB limit. The four successful outputs total 2,808,885,797
bytes. Their SHA-256 values are recorded in the gitignored run directory.

### `as_first_reported` append-only gate

Baseline rows all remain and 381,487 rows were added. **Previously filled cells changed: 0. Newly
null cells: 0. Removed rows: 0.** The fail-loud audit would have stopped on any non-zero count.

“Existing-row fill” means a baseline `(company, period_end)` existed with a null value. “New-row
cells” are populated values on the 381,487 wholly new rows.

| column | existing-row fills | new-row cells | total newly filled |
|---|---:|---:|---:|
| `Equity` | 2 | 323,564 | 323,566 |
| `NetCurrentAssetsLiabilities` | 2 | 319,864 | 319,866 |
| `CurrentAssets` | 3 | 296,671 | 296,674 |
| `Creditors` | 0 | 30,393 | 30,393 |
| `CashBankOnHand` | 2 | 165,682 | 165,684 |
| `Debtors` | 2 | 104,981 | 104,983 |
| `PropertyPlantEquipment` | 3 | 105,927 | 105,930 |
| `TotalAssetsLessCurrentLiabilities` | 2 | 299,182 | 299,184 |
| `AverageNumberEmployeesDuringPeriod` | 3 | 339,934 | 339,937 |
| `equity_share_capital` | 1 | 145,250 | 145,251 |
| `equity_retained_earnings` | 1 | 139,645 | 139,646 |
| `creditors_within_one_year` | 2 | 138,543 | 138,545 |
| `creditors_after_one_year` | 2 | 60,550 | 60,552 |
| `employees_unit_anomaly` | 3 | 339,934 | 339,937 |
| **total** | **28** | **2,810,120** | **2,810,148** |

### `latest` changes

Baseline rows all remain and 395,866 rows were added. There were 178,973 changed non-null cells
(expected restatements), 2,998,437 newly filled cells and zero newly null cells.

| column | changed non-null cells |
|---|---:|
| `Equity` | 24,374 |
| `NetCurrentAssetsLiabilities` | 32,100 |
| `CurrentAssets` | 20,135 |
| `Creditors` | 701 |
| `CashBankOnHand` | 2,657 |
| `Debtors` | 4,152 |
| `PropertyPlantEquipment` | 2,336 |
| `TotalAssetsLessCurrentLiabilities` | 27,667 |
| `AverageNumberEmployeesDuringPeriod` | 31,583 |
| `equity_share_capital` | 566 |
| `equity_retained_earnings` | 5,426 |
| `creditors_within_one_year` | 11,606 |
| `creditors_after_one_year` | 2,515 |
| `employees_unit_anomaly` | 13,155 |

## Features and aligned register reconciliation

Features were built at **T = 2026-09** from internal `as_first_reported`, paired to the existing
**2026-10-01** register snapshot. Both governed and ungoverned outputs contain 6,891,277 companies
and the same 20-column schema; the combined build took 16.4s and peaked at 7.45 GiB RSS. The register
manifest's seven ZIP hashes all passed before extraction. Its feature report records 5,704,711
companies plus one blank/other row, closing the manifest total of 5,704,712.

Aligned reconciliation against register `Accounts.LastMadeUpDate`:

| bucket | companies |
|---|---:|
| exact | 3,932,469 |
| both absent | 1,464,569 |
| no accounts feature, register date present | 223,206 |
| register newer | 84,331 |
| accounts newer | 105 |
| accounts feature present, register date absent | 31 |

Among the 4,016,905 companies with dates present in both sources, the exact-match rate is
**97.89798% (97.90%)**. The 105 accounts-newer cases are 0.0026% of both-present companies, consistent
with the aligned comparison remaining effectively free of the one-month mismatch seen in the old
misaligned run. The accounts feature table also includes 2,874,341 companies absent from this live
register snapshot (principally dissolved/removed companies); Stage 2 will exclude them by using the
register as its base population.

## Reproducibility and validation

- `scripts/audit_accounts_wide_extension.py` writes the per-mode JSON and fails first-reported mode
  if any previously filled value changes or any row disappears.
- `scripts/reconcile_accounts_register.py` writes the aligned bucket report and asserts the buckets
  close exactly to the one-row-per-company register population.
- All new tests use synthetic fixtures only. No real company record or secret is committed.

Stage 2 has not started.
