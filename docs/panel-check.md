# Accounts panel existence and reconciliation check

This report covers every iXBRL filing in the 24 monthly 2022–2023 archives. XML filings were skipped and counted. ZIP members were read in memory without extraction; aggregation used a disk-backed store.

> Parser audit note: these panel figures are valid minimum counts. The V4 monotonic regression reproduced every legacy observation and recovered 108 additional employee facts in the two-archive audit sample; all additions were independently confirmed with lxml.

## Recurrence: does a company panel exist?

Distinct companies: **3,837,237**.

| Counting method | 1 period | 2 periods | 3 periods | 4+ periods | Companies with 2+ |
|---|---:|---:|---:|---:|---:|
| Current period from distinct filings | 1,067,589 | 2,558,461 | 208,689 | 2,498 | 2,769,648 (72.18%) |
| All fact periods, including comparatives | 509,965 | 908,327 | 2,192,343 | 226,602 | 3,327,272 (86.71%) |

**Panel-existence answer:** Yes. Most observed companies have at least two distinct period ends once comparative facts are included.

## Restatement and reconciliation

Across 15,821,369 repeated company/period/concept keys, 14,564,477 (92.06%) agree exactly after applying scale and 1,256,892 (7.94%) disagree.

| Concept | Repeated keys | Exact match | Disagree |
|---|---:|---:|---:|
| `AverageNumberEmployeesDuringPeriod` | 2,195,146 | 2,017,591 (91.91%) | 177,555 (8.09%) |
| `CashBankOnHand` | 1,167,847 | 1,142,377 (97.82%) | 25,470 (2.18%) |
| `Creditors` | 1,393,444 | 1,281,961 (92.00%) | 111,483 (8.00%) |
| `CurrentAssets` | 2,217,153 | 2,051,652 (92.54%) | 165,501 (7.46%) |
| `Debtors` | 885,597 | 848,423 (95.80%) | 37,174 (4.20%) |
| `Equity` | 2,590,162 | 2,372,135 (91.58%) | 218,027 (8.42%) |
| `NetCurrentAssetsLiabilities` | 2,360,095 | 2,094,323 (88.74%) | 265,772 (11.26%) |
| `PropertyPlantEquipment` | 751,054 | 733,122 (97.61%) | 17,932 (2.39%) |
| `TotalAssetsLessCurrentLiabilities` | 2,260,871 | 2,022,893 (89.47%) | 237,978 (10.53%) |

Example disagreements (the most recently filed observation is the take-latest candidate):

- `00009117` / `2021-12-31` / `AverageNumberEmployeesDuringPeriod`: 0 (scale=0, filed=20211231); 9 (scale=0, filed=20221231)
- `00009918` / `2022-02-15` / `Equity`: 2,451 (scale=0, filed=20220215); 3,951 (scale=0, filed=20230215)
- `00009918` / `2022-02-15` / `TotalAssetsLessCurrentLiabilities`: 2,451 (scale=0, filed=20220215); 3,951 (scale=0, filed=20230215)
- `00010931` / `2021-03-31` / `NetCurrentAssetsLiabilities`: 244,937 (scale=0, filed=20210331); 197,203 (scale=0, filed=20220331)
- `00010931` / `2021-03-31` / `TotalAssetsLessCurrentLiabilities`: 727,344 (scale=0, filed=20210331); 679,610 (scale=0, filed=20220331)
- `00011066` / `2022-07-31` / `AverageNumberEmployeesDuringPeriod`: 6 (scale=0, filed=20220731); 7 (scale=0, filed=20230731)
- `00011462` / `2021-12-31` / `AverageNumberEmployeesDuringPeriod`: 4 (scale=0, filed=20211231); 5 (scale=0, filed=20221231)
- `00012851` / `2021-12-31` / `AverageNumberEmployeesDuringPeriod`: - (scale=0, filed=20211231); 0 (scale=0, filed=20221231)
- `00013606` / `2021-12-31` / `CurrentAssets`: 229,996 (scale=0, filed=20211231); 248,647 (scale=0, filed=20221231)
- `00013606` / `2021-12-31` / `Debtors`: 18,550 (scale=0, filed=20211231); 37,201 (scale=0, filed=20221231)
- `00013606` / `2021-12-31` / `NetCurrentAssetsLiabilities`: 186,564 (scale=0, filed=20211231); 205,215 (scale=0, filed=20221231)
- `00013882` / `2021-12-31` / `Creditors`: 0 (scale=0, filed=20211231); 300 (scale=0, filed=20221231)

## Population fill rates

Denominator: distinct company/period records containing at least one locked concept.

| Concept | Present records | Fill rate | Monthly range (2022–2023) |
|---|---:|---:|---:|
| `Equity` | 9,016,687 | 91.79% | 79.4%–93.6% ⚠ |
| `NetCurrentAssetsLiabilities` | 8,081,119 | 82.26% | 79.5%–85.6% |
| `CurrentAssets` | 7,595,647 | 77.32% | 74.1%–80.3% |
| `Creditors` | 5,144,658 | 52.37% | 49.1%–53.6% |
| `CashBankOnHand` | 4,209,084 | 42.85% | 39.7%–44.8% |
| `Debtors` | 3,166,121 | 32.23% | 28.4%–36.6% |
| `PropertyPlantEquipment` | 2,720,954 | 27.70% | 24.2%–31.8% |
| `TotalAssetsLessCurrentLiabilities` | 7,739,356 | 78.78% | 76.2%–81.7% |
| `AverageNumberEmployeesDuringPeriod` | 8,100,768 | 82.46% | 78.1%–84.1% |

⚠ marks a ≥10 percentage-point monthly range, a simple screen for filing-year/month-correlated missingness rather than a formal significance test. The recon sample benchmarks were approximately 96–97% for Equity and 41% (2022) to 33% (2025) for CashBankOnHand.

## Size and reduction

- Filings processed: 6,849,283
- Distinct company/period records: 9,823,456
- Long-format source observations: 71,643,039
- Input ZIP size: 52.90 GiB
- Reduced Parquet size: 0.56 GiB
- Reduction ratio: **94.8× smaller**

## Integrity

- XML filings skipped: 11,175
- Other/unsupported members skipped: 0
- Filename-pattern exceptions: 1
- Unparseable filings: 0
- Filename/tag company-number mismatches: 16
- Target facts with missing or invalid period-end contexts: 0
- Facts omitted because no unique consolidated value could be selected: 12,314,285

### Detail on omitted ambiguous facts

The 12,314,285 figure counts individual iXBRL fact elements, not company/period records. Within each filing, facts are grouped by concept and period end. A non-dimensional context is preferred over contexts containing a `<segment>` or `<scenario>`. If the preferred facts all represent the same scaled value, one is retained. If they contain different values, none is selected because choosing one would be arbitrary.

An evenly distributed follow-up sample of 24,000 filings across the 24 archives produced:

| Measure | Count |
|---|---:|
| Candidate concept/period groups | 264,223 |
| Retained groups | 248,734 |
| Ambiguous groups | 15,489 (5.86%) |
| Individual facts in ambiguous groups | 41,157 |
| Average facts per ambiguous group | 2.66 |

Of the 15,489 ambiguous groups, 15,485 (99.97%) used dimensional contexts. Only four contained conflicting non-dimensional values. Ambiguous group sizes were:

| Facts in group | Groups |
|---:|---:|
| 2 | 7,838 |
| 3 | 5,585 |
| 4 | 1,846 |
| 5+ | 220 |

The ambiguity was concentrated in a few concepts:

| Concept | Ambiguous groups | Share |
|---|---:|---:|
| `Creditors` | 12,679 | 81.86% |
| `Equity` | 2,592 | 16.73% |
| `PropertyPlantEquipment` | 172 | 1.11% |
| All other concepts | 46 | 0.30% |

These are primarily dimensional components rather than corrupt or contradictory data. Typical cases include creditor maturity/type categories, equity components such as share capital and retained earnings, and property/plant/equipment asset classes. When no non-dimensional total exists, the panel deliberately omits these values rather than treating a component as the consolidated company value.

Two caveats apply:

- Dimensional components ignored because a non-dimensional total was available are not included in the 12,314,285 counter.
- The exact full-run count of ambiguous groups was not retained in the Parquet output. Applying the sampled mean of 2.66 facts per group suggests approximately 4.6 million groups, but this is an estimate; an exact count requires another instrumented pass.
