# Accounts member and reconciliation QA

Source LONG table: `long.parquet` (evenly spread 1,000-member samples from January and February 2022).

## Total versus component sums

This is diagnostic only. No reported value is corrected or replaced. Agreement uses an absolute tolerance of max(£1, 1e-6 × |total|). Components are summed only within the same dimension and source filing; parallel dimensional axes are never combined.

| Concept | Comparisons | Agreements | Agreement rate | Median absolute difference |
|---|---:|---:|---:|---:|
| `Creditors` | 63 | 21 | 33.3% | 9,833.00 |
| `Debtors` | 113 | 102 | 90.3% | 0.00 |
| `Equity` | 1,250 | 1,198 | 95.8% | 0.00 |
| `PropertyPlantEquipment` | 793 | 744 | 93.8% | 0.00 |

## Member-frequency histogram

All target concepts are included. Frequencies count only Stage 1 observations tagged `selected`; conflict rows remain in the archive for a Stage 2 policy. This table is the evidence for a human-selected WIDE member map.

| Concept | Dimension | Member | Observations | Companies | Company-periods |
|---|---|---|---:|---:|---:|
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `WithinOneYear` | 1,392 | 761 | 1,392 |
| `Creditors` | `FinancialInstrumentCurrentNon-currentDimension` | `CurrentFinancialInstruments` | 1,086 | 565 | 1,086 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `AfterOneYear` | 660 | 367 | 660 |
| `Creditors` | `FinancialInstrumentCurrentNon-currentDimension` | `Non-currentFinancialInstruments` | 453 | 234 | 453 |
| `Debtors` | `FinancialInstrumentCurrentNon-currentDimension` | `CurrentFinancialInstruments` | 95 | 54 | 95 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `WithinOneYear` | 43 | 23 | 43 |
| `Debtors` | `FinancialInstrumentCurrentNon-currentDimension` | `Non-currentFinancialInstruments` | 12 | 6 | 12 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `AfterOneYear` | 11 | 6 | 11 |
| `Equity` | `EquityClassesDimension` | `ShareCapital` | 1,356 | 706 | 1,356 |
| `Equity` | `EquityClassesDimension` | `RetainedEarningsAccumulatedLosses` | 1,301 | 680 | 1,301 |
| `Equity` | `EquityClassesDimension` | `RevaluationReserve` | 50 | 22 | 50 |
| `Equity` | `EquityClassesDimension` | `SharePremium` | 49 | 24 | 49 |
| `Equity` | `EquityClassesDimension` | `CapitalRedemptionReserve` | 35 | 17 | 35 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShares` | 23 | 12 | 23 |
| `Equity` | `EquityClassesDimension` | `OtherReservesSubtotal` | 22 | 12 | 22 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve3ComponentTotalEquity` | 18 | 9 | 18 |
| `Equity` | `EquityClassesDimension` | `OtherMiscellaneousReserve` | 11 | 5 | 11 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve1ComponentTotalEquity` | 8 | 4 | 8 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve2ComponentTotalEquity` | 6 | 3 | 6 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 3 | 3 | 3 |
| `Equity` | `EquityClassesDimension` | `CapitalReserve` | 2 | 1 | 2 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShares` | 2 | 1 | 2 |
| `Equity` | `EquityClassesDimension` | `TotalEquityAttributableToOwnersParentBeforeNon-controllingInterests` | 2 | 1 | 2 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 1 | 1 | 1 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 11 | 11 | 11 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `PlantMachinery` | 416 | 220 | 416 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ComputerEquipment` | 214 | 110 | 214 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `FurnitureFittings` | 199 | 104 | 199 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `MotorVehicles` | 171 | 90 | 171 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `LandBuildings` | 93 | 49 | 93 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OtherPropertyPlantEquipment` | 89 | 46 | 89 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `FurnitureFittingsToolsEquipment` | 65 | 36 | 65 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Vehicles` | 37 | 19 | 37 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OfficeEquipment` | 36 | 20 | 36 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `LeaseholdImprovements` | 18 | 9 | 18 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ToolsEquipment` | 11 | 6 | 11 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `LeasedAssetsHeldAsLessee` | 4 | 2 | 4 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `CommercialMotorVehicles` | 4 | 2 | 4 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `VehiclesPlantMachinery` | 4 | 2 | 4 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `InvestmentPropertyIncludedWithinPPE` | 2 | 1 | 2 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `MotorCars` | 2 | 1 | 2 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Buildings` | 2 | 1 | 2 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 12 | 12 | 12 |

## Reviewed decisions and remaining gates

- The v1 WIDE map is now reviewed: all nine genuine totals plus Share Capital and Retained Earnings Equity members.
- `PropertyPlantEquipment` members are deferred to v2 pending a reviewed class-normalisation map.
- Creditors members remain gated pending larger-sample reconciliation characterisation.
- Run reconnaissance around 2010, 2013, and 2016 before choosing an effective historical start year.
- Approve the Kaggle framing and OGL v3.0 attribution wording before publication.

## Draft Kaggle licensing and framing note — human approval required

Contains public Companies House accounts data used under the Open Government Licence v3.0. This derivative contains financial facts only, is not a complete representation of a company or its financial position, and retains documented coverage, filing-format, dimensional, currency, and restatement limitations. Companies House and the UK Government do not endorse this derivative.

## Limitations

- Pre-2019 archive behavior is not yet validated.
- Non-GBP monetary observations remain in LONG but are excluded from WIDE; no currency conversion is performed.
- Scale handling is synthetically tested, but real recon samples contained only missing or zero scale.
- Employee-count coverage has a 2019–2021 reporting-regime break and must not be treated as company signal.
- Equity missingness varies non-randomly by month.
- Predictive publication must use `as_first_reported`; `latest` incorporates later comparative restatements.
- Genuine Creditors totals are only about 4% in the two-archive sample because Creditors are dimensionally dominant. Null total does not imply an absent filing; users should rely on explicitly curated member columns.
- Run the random regex-versus-lxml parser-agreement audit before starting a full-history extraction.
