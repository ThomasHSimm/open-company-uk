# Accounts monthly data reconnaissance

Generated from an evenly spread sample of up to 300 ZIP members per archive. Filings were read in memory; no archive was extracted. Percentages use all sampled members as the denominator.

## Sample and format split

| Year (month) | ZIP members | Sampled | iXBRL HTML | XBRL XML | Other | Unparseable |
|---|---:|---:|---:|---:|---:|---:|
| 2019 (January) | 221334 | 300 | 296 (98.7%) | 4 (1.3%) | 0 (0.0%) | 0 |
| 2020 (January) | 235244 | 300 | 299 (99.7%) | 1 (0.3%) | 0 (0.0%) | 0 |
| 2021 (January) | 264188 | 300 | 300 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 |
| 2022 (January) | 249427 | 300 | 296 (98.7%) | 4 (1.3%) | 0 (0.0%) | 0 |
| 2025 (August) | 261995 | 300 | 300 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 |

## Concept fill-rate matrix

| Concept | 2019 | 2020 | 2021 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|
| `CashBankOnHand` | 44.0% | 47.3% | 42.7% | 41.0% | 32.7% |
| `CurrentAssets` | 75.7% | 71.7% | 73.7% | 71.3% | 72.0% |
| `Creditors` | 78.3% | 76.3% | 79.7% | 77.7% | 74.0% |
| `NetCurrentAssetsLiabilities` | 82.7% | 77.7% | 82.7% | 81.3% | 78.0% |
| `Equity` | 96.7% | 95.7% | 97.0% | 97.3% | 97.0% |
| `TotalAssetsLessCurrentLiabilities` | 77.0% | 75.3% | 77.0% | 75.0% | 74.7% |
| `Debtors` | 32.0% | 31.3% | 30.7% | 28.0% | 24.3% |
| `PropertyPlantEquipment` | 28.0% | 29.7% | 26.3% | 25.3% | 23.0% |
| `AverageNumberEmployeesDuringPeriod` | 24.3% | 33.0% | 84.7% | 84.0% | 82.0% |
| `UKCompaniesHouseRegisteredNumber` | 98.7% | 99.3% | 100.0% | 98.7% | 100.0% |

## Taxonomy and namespace drift

### 2019 (January)

- `http://xbrl.frc.org.uk/reports/2014-09-01/direp` — 293 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/business` — 293 sampled filings
- `http://xbrl.frc.org.uk/fr/2014-09-01/core` — 293 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/countries` — 185 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/currencies` — 133 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/accrep` — 121 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/aurep` — 120 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/common` — 117 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/ref` — 101 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2014-09-01` — 101 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/languages` — 101 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/types` — 99 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc/2015-02-14` — 75 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc-core/2015-02-14` — 67 sampled filings

### 2020 (January)

- `http://xbrl.frc.org.uk/reports/2014-09-01/direp` — 273 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/business` — 273 sampled filings
- `http://xbrl.frc.org.uk/fr/2014-09-01/core` — 273 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/countries` — 170 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/currencies` — 116 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/accrep` — 114 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/aurep` — 112 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/common` — 108 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/languages` — 91 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/ref` — 90 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2014-09-01` — 88 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/types` — 86 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc/2015-02-14` — 79 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc-core/2015-02-14` — 71 sampled filings
- `http://xbrl.frc.org.uk/fr/2019-01-01/core` — 24 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/business` — 24 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/direp` — 24 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/countries` — 22 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/accrep` — 21 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2019-01-01` — 20 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/aurep` — 18 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/common` — 18 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/types` — 18 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/languages` — 18 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/ref` — 18 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/currencies` — 18 sampled filings
- `http://xbrl.frc.org.uk/char/2016-01-01` — 2 sampled filings
- `http://xbrl.frc.org.uk/char/2016-01-01/ref` — 2 sampled filings
- `http://xbrl.frc.org.uk/general/2018-01-01/ref` — 1 sampled filings
- `http://xbrl.frc.org.uk/reports/2018-01-01/accrep` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2018-01-01/business` — 1 sampled filings
- `http://xbrl.frc.org.uk/fr/2018-01-01/core` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2018-01-01/countries` — 1 sampled filings
- `http://xbrl.frc.org.uk/general/2018-01-01/common` — 1 sampled filings
- `http://xbrl.frc.org.uk/general/2018-01-01/types` — 1 sampled filings
- `http://xbrl.frc.org.uk/reports/2018-01-01/direp` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2018-01-01/currencies` — 1 sampled filings
- `http://xbrl.frc.org.uk/reports/2018-01-01/aurep` — 1 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2018-01-01` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2018-01-01/languages` — 1 sampled filings

### 2021 (January)

- `http://xbrl.frc.org.uk/cd/2019-01-01/business` — 161 sampled filings
- `http://xbrl.frc.org.uk/fr/2019-01-01/core` — 161 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/direp` — 161 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/countries` — 155 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/direp` — 139 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/business` — 139 sampled filings
- `http://xbrl.frc.org.uk/fr/2014-09-01/core` — 139 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/aurep` — 126 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/common` — 124 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/accrep` — 124 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/currencies` — 109 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2019-01-01` — 108 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/languages` — 106 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/ref` — 106 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/types` — 103 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/countries` — 43 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/currencies` — 25 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/accrep` — 8 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/types` — 4 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2014-09-01` — 4 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/common` — 4 sampled filings
- `http://xbrl.frc.org.uk/general/2014-09-01/ref` — 3 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/languages` — 3 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/aurep` — 3 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc/2015-02-14` — 3 sampled filings
- `http://xbrl.frc.org.uk/char/2019-01-01` — 1 sampled filings
- `http://xbrl.frc.org.uk/char/2019-01-01/ref` — 1 sampled filings
- `http://www.govtalk.gov.uk/uk/fr/tax/dpl-frc-core/2015-02-14` — 1 sampled filings

### 2022 (January)

- `http://xbrl.frc.org.uk/cd/2019-01-01/business` — 237 sampled filings
- `http://xbrl.frc.org.uk/fr/2019-01-01/core` — 237 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/direp` — 237 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/countries` — 129 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/aurep` — 89 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/common` — 86 sampled filings
- `http://xbrl.frc.org.uk/reports/2019-01-01/accrep` — 86 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/currencies` — 67 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2019-01-01` — 63 sampled filings
- `http://xbrl.frc.org.uk/cd/2019-01-01/languages` — 62 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/ref` — 62 sampled filings
- `http://xbrl.frc.org.uk/general/2019-01-01/types` — 59 sampled filings
- `http://xbrl.frc.org.uk/reports/2021-01-01/direp` — 58 sampled filings
- `http://xbrl.frc.org.uk/cd/2021-01-01/business` — 58 sampled filings
- `http://xbrl.frc.org.uk/fr/2021-01-01/core` — 58 sampled filings
- `http://xbrl.frc.org.uk/cd/2021-01-01/countries` — 57 sampled filings
- `http://xbrl.frc.org.uk/cd/2021-01-01/currencies` — 53 sampled filings
- `http://xbrl.frc.org.uk/reports/2021-01-01/accrep` — 33 sampled filings
- `http://xbrl.frc.org.uk/general/2021-01-01/ref` — 33 sampled filings
- `http://xbrl.frc.org.uk/general/2021-01-01/common` — 33 sampled filings
- `http://xbrl.frc.org.uk/reports/2021-01-01/aurep` — 33 sampled filings
- `http://xbrl.frc.org.uk/general/2021-01-01/types` — 33 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2021-01-01` — 33 sampled filings
- `http://xbrl.frc.org.uk/cd/2021-01-01/languages` — 33 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/accrep` — 2 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/direp` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/countries` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/business` — 1 sampled filings
- `http://xbrl.frc.org.uk/cd/2014-09-01/currencies` — 1 sampled filings
- `http://xbrl.frc.org.uk/fr/2014-09-01/core` — 1 sampled filings

### 2025 (August)

- `http://xbrl.frc.org.uk/fr/2023-01-01/core` — 186 sampled filings
- `http://xbrl.frc.org.uk/cd/2023-01-01/business` — 186 sampled filings
- `http://xbrl.frc.org.uk/reports/2023-01-01/direp` — 186 sampled filings
- `http://xbrl.frc.org.uk/cd/2023-01-01/countries` — 90 sampled filings
- `http://xbrl.frc.org.uk/cd/2024-01-01/business` — 63 sampled filings
- `http://xbrl.frc.org.uk/reports/2024-01-01/direp` — 63 sampled filings
- `http://xbrl.frc.org.uk/fr/2024-01-01/core` — 63 sampled filings
- `http://xbrl.frc.org.uk/cd/2023-01-01/currencies` — 61 sampled filings
- `http://xbrl.frc.org.uk/cd/2024-01-01/countries` — 60 sampled filings
- `http://xbrl.frc.org.uk/reports/2023-01-01/aurep` — 58 sampled filings
- `http://xbrl.frc.org.uk/reports/2023-01-01/accrep` — 57 sampled filings
- `http://xbrl.frc.org.uk/general/2023-01-01/common` — 56 sampled filings
- `http://xbrl.frc.org.uk/cd/2023-01-01/languages` — 55 sampled filings
- `http://xbrl.frc.org.uk/general/2023-01-01/ref` — 54 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2023-01-01` — 51 sampled filings
- `http://xbrl.frc.org.uk/dpl/2023-01-01` — 51 sampled filings
- `http://xbrl.frc.org.uk/general/2023-01-01/types` — 50 sampled filings
- `http://xbrl.frc.org.uk/reports/2025-01-01/accrep` — 48 sampled filings
- `http://xbrl.frc.org.uk/fr/2025-01-01/core` — 48 sampled filings
- `http://xbrl.frc.org.uk/reports/2025-01-01/direp` — 48 sampled filings
- `http://xbrl.frc.org.uk/reports/2025-01-01/aurep` — 48 sampled filings
- `http://xbrl.frc.org.uk/cd/2025-01-01/business` — 48 sampled filings
- `http://xbrl.frc.org.uk/general/2025-01-01/common` — 48 sampled filings
- `http://xbrl.frc.org.uk/cd/2025-01-01/countries` — 48 sampled filings
- `http://xbrl.frc.org.uk/cd/2024-01-01/currencies` — 42 sampled filings
- `http://xbrl.frc.org.uk/reports/2024-01-01/accrep` — 34 sampled filings
- `http://xbrl.frc.org.uk/general/2024-01-01/common` — 32 sampled filings
- `http://xbrl.frc.org.uk/general/2024-01-01/types` — 31 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2024-01-01` — 30 sampled filings
- `http://xbrl.frc.org.uk/cd/2024-01-01/languages` — 30 sampled filings
- `http://xbrl.frc.org.uk/general/2024-01-01/ref` — 30 sampled filings
- `http://xbrl.frc.org.uk/reports/2024-01-01/aurep` — 30 sampled filings
- `http://xbrl.frc.org.uk/cd/2025-01-01/languages` — 21 sampled filings
- `http://xbrl.frc.org.uk/cd/2025-01-01/currencies` — 21 sampled filings
- `http://xbrl.frc.org.uk/general/2025-01-01/types` — 21 sampled filings
- `http://xbrl.frc.org.uk/general/2025-01-01/ref` — 21 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2025-01-01` — 21 sampled filings
- `http://xbrl.frc.org.uk/dsep/2025-01-01` — 16 sampled filings
- `http://xbrl.frc.org.uk/cic/2025-01-01` — 16 sampled filings
- `http://xbrl.frc.org.uk/dpl/2025-01-01` — 13 sampled filings
- `http://xbrl.frc.org.uk/secr/2024-04-01` — 9 sampled filings
- `http://xbrl.frc.org.uk/secr/2023-04-01` — 7 sampled filings
- `http://xbrl.frc.org.uk/cd/2022-01-01/countries` — 3 sampled filings
- `http://xbrl.frc.org.uk/FRS-102/2022-01-01` — 3 sampled filings
- `http://xbrl.frc.org.uk/cd/2022-01-01/business` — 3 sampled filings
- `http://xbrl.frc.org.uk/reports/2022-01-01/aurep` — 3 sampled filings
- `http://xbrl.frc.org.uk/reports/2022-01-01/direp` — 3 sampled filings
- `http://xbrl.frc.org.uk/reports/2022-01-01/accrep` — 3 sampled filings
- `http://xbrl.frc.org.uk/general/2022-01-01/types` — 3 sampled filings
- `http://xbrl.frc.org.uk/dpl/2022-01-01` — 3 sampled filings
- `http://xbrl.frc.org.uk/general/2022-01-01/common` — 3 sampled filings
- `http://xbrl.frc.org.uk/cd/2022-01-01/currencies` — 3 sampled filings
- `http://xbrl.frc.org.uk/general/2022-01-01/ref` — 3 sampled filings
- `http://xbrl.frc.org.uk/cd/2022-01-01/languages` — 3 sampled filings
- `http://xbrl.frc.org.uk/fr/2022-01-01/core` — 3 sampled filings
- `http://xbrl.frc.org.uk/dpl/2024-01-01` — 2 sampled filings
- `http://xbrl.frc.org.uk/reports/2014-09-01/accrep` — 1 sampled filings
- `http://xbrl.frc.org.uk/char/2024-01-01` — 1 sampled filings
- `http://xbrl.frc.org.uk/char/2024-01-01/ref` — 1 sampled filings

## Magnitude and formatting conventions

### 2019 (January)

Across 1299 captured CashBankOnHand/Equity facts: scales `(missing)`, `0`; decimals `0`, `2`. Comma-formatted: 777; negative/parenthesised: 8. Units: `GBP` (1297), `u1` (2).
Representative `CashBankOnHand` facts: raw `1,968`, scale `0`, decimals `0`, unit `GBP`; raw `982`, scale `0`, decimals `0`, unit `GBP`; raw `387,802`, scale `(missing)`, decimals `0`, unit `GBP`; raw `313,662`, scale `(missing)`, decimals `0`, unit `GBP`; raw `372`, scale `(missing)`, decimals `0`, unit `GBP`.
Representative `Equity` facts: raw `202,465`, scale `0`, decimals `0`, unit `GBP`; raw `202,465`, scale `0`, decimals `0`, unit `GBP`; raw `192,130`, scale `0`, decimals `0`, unit `GBP`; raw `193,116`, scale `0`, decimals `0`, unit `GBP`; raw `10,335`, scale `0`, decimals `0`, unit `GBP`.
Detected period-end/instant values from `2015-05-31` to `2019-02-28` (86 distinct values).

### 2020 (January)

Across 1270 captured CashBankOnHand/Equity facts: scales `(missing)`, `0`; decimals `0`, `2`. Comma-formatted: 727; negative/parenthesised: 9. Units: `GBP` (1232), `u1` (38).
Representative `CashBankOnHand` facts: raw `3,042`, scale `0`, decimals `0`, unit `GBP`; raw `1,968`, scale `0`, decimals `0`, unit `GBP`; raw `186,129`, scale `0`, decimals `0`, unit `GBP`; raw `375,221`, scale `0`, decimals `0`, unit `GBP`; raw `2`, scale `(missing)`, decimals `0`, unit `GBP`.
Representative `Equity` facts: raw `202,465`, scale `0`, decimals `0`, unit `GBP`; raw `202,465`, scale `0`, decimals `0`, unit `GBP`; raw `191,056`, scale `0`, decimals `0`, unit `GBP`; raw `192,130`, scale `0`, decimals `0`, unit `GBP`; raw `11,409`, scale `0`, decimals `0`, unit `GBP`.
Detected period-end/instant values from `2016-03-31` to `2020-01-06` (79 distinct values).

### 2021 (January)

Across 1255 captured CashBankOnHand/Equity facts: scales `(missing)`, `0`; decimals `0`, `2`. Comma-formatted: 780; negative/parenthesised: 10. Units: `GBP` (1227), `u1` (26), `currencyUnit` (2).
Representative `CashBankOnHand` facts: raw `262,929`, scale `(missing)`, decimals `0`, unit `u1`; raw `269,524`, scale `(missing)`, decimals `0`, unit `u1`; raw `262,929`, scale `(missing)`, decimals `0`, unit `u1`; raw `269,524`, scale `(missing)`, decimals `0`, unit `u1`; raw `8,391`, scale `0`, decimals `0`, unit `GBP`.
Representative `Equity` facts: raw `8,000`, scale `(missing)`, decimals `0`, unit `u1`; raw `8,000`, scale `(missing)`, decimals `0`, unit `u1`; raw `3,453,845`, scale `(missing)`, decimals `0`, unit `u1`; raw `3,511,590`, scale `(missing)`, decimals `0`, unit `u1`; raw `3,461,845`, scale `(missing)`, decimals `0`, unit `u1`.
Detected period-end/instant values from `2017-10-31` to `2020-12-31` (85 distinct values).

### 2022 (January)

Across 1256 captured CashBankOnHand/Equity facts: scales `(missing)`, `0`; decimals `0`, `2`, `9`. Comma-formatted: 734; negative/parenthesised: 6. Units: `GBP` (1214), `u1` (24), `u0` (10), `U-GBP` (8).
Representative `CashBankOnHand` facts: raw `115`, scale `0`, decimals `0`, unit `GBP`; raw `-`, scale `0`, decimals `0`, unit `GBP`; raw `100`, scale `(missing)`, decimals `0`, unit `GBP`; raw `100`, scale `(missing)`, decimals `0`, unit `GBP`; raw `574,560`, scale `0`, decimals `0`, unit `GBP`.
Representative `Equity` facts: raw `0`, scale `(missing)`, decimals `2`, unit `GBP`; raw `0`, scale `(missing)`, decimals `2`, unit `GBP`; raw `50,000`, scale `0`, decimals `0`, unit `GBP`; raw `50,000`, scale `0`, decimals `0`, unit `GBP`; raw `285,781`, scale `0`, decimals `0`, unit `GBP`.
Detected period-end/instant values from `2018-10-01` to `2022-01-31` (90 distinct values).

### 2025 (August)

Across 1139 captured CashBankOnHand/Equity facts: scales `(missing)`, `0`; decimals `0`, `2`, `9`, `INF`. Comma-formatted: 720; negative/parenthesised: 4. Units: `GBP` (1117), `currencyUnit` (12), `u1` (10).
Representative `CashBankOnHand` facts: raw `324,550`, scale `0`, decimals `0`, unit `GBP`; raw `226,968`, scale `0`, decimals `0`, unit `GBP`; raw `2,943`, scale `0`, decimals `0`, unit `GBP`; raw `5,408`, scale `0`, decimals `0`, unit `GBP`; raw `66,211`, scale `(missing)`, decimals `0`, unit `GBP`.
Representative `Equity` facts: raw `7,500`, scale `0`, decimals `0`, unit `GBP`; raw `7,500`, scale `0`, decimals `0`, unit `GBP`; raw `616,724`, scale `0`, decimals `0`, unit `GBP`; raw `678,788`, scale `0`, decimals `0`, unit `GBP`; raw `624,224`, scale `0`, decimals `0`, unit `GBP`.
Detected period-end/instant values from `2022-05-31` to `2025-07-31` (93 distinct values).

## Filename and company-number checks

### 2019 (January)

Filename-pattern exceptions across all filing members: 0.
Tag-vs-filename company-number mismatches in the sample: 0.

### 2020 (January)

Filename-pattern exceptions across all filing members: 0.
Tag-vs-filename company-number mismatches in the sample: 0.

### 2021 (January)

Filename-pattern exceptions across all filing members: 0.
Tag-vs-filename company-number mismatches in the sample: 0.

### 2022 (January)

Filename-pattern exceptions across all filing members: 0.
Tag-vs-filename company-number mismatches in the sample: 0.

### 2025 (August)

Filename-pattern exceptions across all filing members: 0.
Tag-vs-filename company-number mismatches in the sample: 0.

## Candidate longitudinal companies

Companies appearing in at least three sampled years. Sampling means omission here does not imply absence from an archive.

None found in the sampled filings.
