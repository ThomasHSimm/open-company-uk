# Accounts restatement rate (month-ordered running tally)

Scope: **2014-2026 (continuous, 152 archives)** (continuous months only — a gap between archives makes "restated later" indistinguishable from "not resampled"; never aggregate this with the lone gap-separated months).

Same definition as the panel check (`docs/panel-check.md`'s 7.94%): non-dimensional (`dimension IS NULL`), `status == 'selected'` numeric facts for the nine target concepts, keyed by (company, period_end, concept). "Repeated" means the key appears in >=2 filings within scope; "disagree" means a later filing reports a different scale-normalised value than the first one seen.

- Distinct keys: 178,916,771
- Repeated keys: 115,847,972
- Disagree: 10,740,756 (9.27% of repeated)

## By concept

| Concept | Repeated keys | Exact match | Disagree |
|---|---:|---:|---:|
| `AverageNumberEmployeesDuringPeriod` | 13,161,648 | 11,944,442 (90.75%) | 1,217,206 (9.25%) |
| `CashBankOnHand` | 8,343,217 | 8,162,962 (97.84%) | 180,255 (2.16%) |
| `Creditors` | 798,498 | 764,741 (95.77%) | 33,757 (4.23%) |
| `CurrentAssets` | 19,750,320 | 18,012,173 (91.20%) | 1,738,147 (8.80%) |
| `Debtors` | 8,170,262 | 7,767,390 (95.07%) | 402,872 (4.93%) |
| `Equity` | 18,603,703 | 17,060,973 (91.71%) | 1,542,730 (8.29%) |
| `NetCurrentAssetsLiabilities` | 21,332,381 | 18,409,159 (86.30%) | 2,923,222 (13.70%) |
| `PropertyPlantEquipment` | 5,501,629 | 5,368,325 (97.58%) | 133,304 (2.42%) |
| `TotalAssetsLessCurrentLiabilities` | 20,186,314 | 17,617,051 (87.27%) | 2,569,263 (12.73%) |
