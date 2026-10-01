# Accounts member and reconciliation QA

Source LONG table: `data/accounts/long/accounts-long-*.parquet`.

## Total versus component sums

This is diagnostic only. No reported value is corrected or replaced. Agreement uses an absolute tolerance of max(£1, 1e-6 × |total|). Components are summed only within the same dimension and source filing; parallel dimensional axes are never combined.

| Concept | Comparisons | Agreements | Agreement rate | Median absolute difference |
|---|---:|---:|---:|---:|
| `AverageNumberEmployeesDuringPeriod` | 7,720 | 3,883 | 50.3% | 1.00 |
| `CashBankOnHand` | 22,649 | 8,696 | 38.4% | 112,406.00 |
| `Creditors` | 945,375 | 209,244 | 22.1% | 23,358.00 |
| `CurrentAssets` | 16,657 | 8,313 | 49.9% | 53.00 |
| `Debtors` | 1,363,539 | 1,230,885 | 90.3% | 0.00 |
| `Equity` | 17,768,225 | 16,701,860 | 94.0% | 0.00 |
| `NetCurrentAssetsLiabilities` | 20,103 | 8,091 | 40.2% | 157,281.00 |
| `PropertyPlantEquipment` | 11,957,928 | 11,188,366 | 93.6% | 0.00 |
| `TotalAssetsLessCurrentLiabilities` | 21,923 | 8,354 | 38.1% | 281,197.00 |

## Member-frequency histogram

All target concepts are included. Frequencies count only Stage 1 observations tagged `selected`; conflict rows remain in the archive for a Stage 2 policy. This table is the evidence for a human-selected WIDE member map.

| Concept | Dimension | Member | Observations | Companies | Company-periods |
|---|---|---|---:|---:|---:|
| `AverageNumberEmployeesDuringPeriod` | `OriginalRevisedDataDimension` | `Original` | 489,089 | 252,673 | 486,370 |
| `AverageNumberEmployeesDuringPeriod` | `GroupCompanyDataDimension` | `Consolidated` | 14,222 | 4,784 | 12,089 |
| `AverageNumberEmployeesDuringPeriod` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 136 | 84 | 129 |
| `AverageNumberEmployeesDuringPeriod` | `ConsolidationDimension` | `Consolidated` | 71 | 26 | 61 |
| `AverageNumberEmployeesDuringPeriod` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 20 | 18 | 20 |
| `AverageNumberEmployeesDuringPeriod` | `ContractTypeDimension` | `OtherContractType1` | 8 | 3 | 7 |
| `AverageNumberEmployeesDuringPeriod` | `SexDimension` | `SexPreferNotToDisclose` | 8 | 5 | 8 |
| `AverageNumberEmployeesDuringPeriod` | `ExceptionalsDimension` | `ExplicitlyIdentifiedAsNon-exceptional` | 6 | 3 | 6 |
| `AverageNumberEmployeesDuringPeriod` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 6 | 5 | 6 |
| `AverageNumberEmployeesDuringPeriod` | `SegmentReconciliationDimension` | `OriginalSegmentValueBeforeAdjustments` | 5 | 4 | 5 |
| `AverageNumberEmployeesDuringPeriod` | `GeographicSegmentsDimension` | `UnitedKingdom` | 5 | 3 | 5 |
| `AverageNumberEmployeesDuringPeriod` | `OperatingSegmentsDimension` | `TotalReportableOperatingSegmentsIncludingAnyUnallocatedAmount` | 5 | 4 | 5 |
| `AverageNumberEmployeesDuringPeriod` | `ContractDurationDimension` | `OtherDurationType1` | 4 | 1 | 4 |
| `AverageNumberEmployeesDuringPeriod` | `ContractTypeDimension` | `OtherContractType2` | 4 | 2 | 4 |
| `AverageNumberEmployeesDuringPeriod` | `ContractTypeDimension` | `FixedPrice` | 4 | 2 | 4 |
| `AverageNumberEmployeesDuringPeriod` | `OperatingSegmentsDimension` | `UnallocatedAmountReportableOperatingSegments` | 2 | 1 | 2 |
| `AverageNumberEmployeesDuringPeriod` | `ProductsServicesDimension` | `TotalBeforeUnallocatedAmountProductsServices` | 2 | 1 | 2 |
| `AverageNumberEmployeesDuringPeriod` | `ContractDurationDimension` | `Long-termContract` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `ContinuingDiscontinuedOperationsDimension` | `SpecificDiscontinuedOperation1` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `MajorCustomersDimension` | `TotalReportableMajorCustomersIncludingAnyUnallocatedAmount` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `OperatingSegmentsDimension` | `ReportableOperatingSegment1` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `ExceptionalsDimension` | `Exceptional` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `ProductsServicesDimension` | `TotalReportableProductsServicesIncludingAnyUnallocatedAmount` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `SexDimension` | `SexMale` | 1 | 1 | 1 |
| `AverageNumberEmployeesDuringPeriod` | `GeographicSegmentsDimension` | `TotalGeographicSegmentsIncludingAnyUnallocatedAmount` | 1 | 1 | 1 |
| `CashBankOnHand` | `OriginalRevisedDataDimension` | `Original` | 298,140 | 153,191 | 296,599 |
| `CashBankOnHand` | `GroupCompanyDataDimension` | `Consolidated` | 19,495 | 6,252 | 16,106 |
| `CashBankOnHand` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 8,402 | 2,633 | 8,398 |
| `CashBankOnHand` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 8,290 | 2,528 | 8,286 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 1,449 | 801 | 1,448 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 931 | 585 | 924 |
| `CashBankOnHand` | `FinancialInstrumentCurrentNon-currentDimension` | `CurrentFinancialInstruments` | 398 | 196 | 379 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 378 | 359 | 378 |
| `CashBankOnHand` | `MaturitiesOrExpirationPeriodsDimension` | `WithinOneYear` | 307 | 147 | 296 |
| `CashBankOnHand` | `CharityFundsDimension` | `TotalEndowmentFunds` | 219 | 75 | 219 |
| `CashBankOnHand` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 133 | 25 | 90 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 12 | 5 | 12 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 12 | 10 | 12 |
| `CashBankOnHand` | `FinancialAssetsClassesCategoriesDimension` | `Available-for-saleFinancialAssets` | 12 | 1 | 7 |
| `CashBankOnHand` | `ProductsServicesDimension` | `ProductService2` | 8 | 8 | 8 |
| `CashBankOnHand` | `ProductsServicesDimension` | `ProductService1` | 8 | 8 | 8 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 6 | 4 | 6 |
| `CashBankOnHand` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 6 | 3 | 6 |
| `CashBankOnHand` | `FinancialInstrumentCurrentNon-currentDimension` | `Non-currentFinancialInstruments` | 3 | 3 | 3 |
| `CashBankOnHand` | `MaturitiesOrExpirationPeriodsDimension` | `AfterOneYear` | 2 | 2 | 2 |
| `CashBankOnHand` | `CurrencyDenominationFinancialInstrumentsDimension` | `PoundSterling` | 2 | 1 | 2 |
| `CashBankOnHand` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 1 | 1 | 1 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `WithinOneYear` | 20,259,091 | 3,063,756 | 12,732,874 |
| `Creditors` | `FinancialInstrumentCurrentNon-currentDimension` | `CurrentFinancialInstruments` | 16,119,644 | 2,114,189 | 10,186,506 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `AfterOneYear` | 8,564,443 | 1,552,124 | 5,642,081 |
| `Creditors` | `FinancialInstrumentCurrentNon-currentDimension` | `Non-currentFinancialInstruments` | 5,512,424 | 804,307 | 3,635,486 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `MoreThanFiveYears` | 7,985 | 1,686 | 5,592 |
| `Creditors` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 1,549 | 650 | 1,549 |
| `Creditors` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 1,426 | 541 | 1,426 |
| `Creditors` | `GroupCompanyDataDimension` | `Consolidated` | 1,328 | 546 | 1,191 |
| `Creditors` | `OriginalRevisedDataDimension` | `Original` | 273 | 137 | 273 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `BetweenTwoFiveYears` | 46 | 21 | 43 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 25 | 21 | 25 |
| `Creditors` | `CharityFundsDimension` | `TotalEndowmentFunds` | 21 | 8 | 21 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `BetweenFive10Years` | 15 | 8 | 15 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `BetweenOneFiveYears` | 12 | 7 | 12 |
| `Creditors` | `ProductsServicesDimension` | `ProductService2` | 8 | 8 | 8 |
| `Creditors` | `ProductsServicesDimension` | `ProductService1` | 8 | 8 | 8 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 7 | 5 | 7 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 5 | 5 | 5 |
| `Creditors` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 4 | 2 | 4 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 4 | 3 | 4 |
| `Creditors` | `FinancialInstrumentValueTypeDimension` | `Cost` | 4 | 2 | 4 |
| `Creditors` | `ContinuingDiscontinuedOperationsDimension` | `Non-currentAssetsDisposalGroupsHeldForSale` | 3 | 2 | 3 |
| `Creditors` | `FinancialInstrumentsClassesCategoriesDimension` | `FinancialLiabilitiesAmortisedCost` | 2 | 1 | 2 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 2 | 1 | 2 |
| `Creditors` | `ProductsServicesDimension` | `OtherProductsServices` | 2 | 1 | 2 |
| `Creditors` | `FinancialInstrumentsClassesCategoriesDimension` | `FinancialInstrumentsCostLessImpairment` | 2 | 1 | 2 |
| `Creditors` | `GeographicSegmentsDimension` | `UnitedKingdom` | 2 | 1 | 2 |
| `Creditors` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 2 | 2 | 2 |
| `Creditors` | `FinancialInstrumentLevelDimension` | `Level1` | 2 | 1 | 2 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `Between6MonthsOneYear` | 2 | 1 | 2 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `Within30Days` | 1 | 1 | 1 |
| `Creditors` | `FinancialInstrumentValueTypeDimension` | `ContractualUndiscountedValue` | 1 | 1 | 1 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `AllPeriods` | 1 | 1 | 1 |
| `Creditors` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 1 | 1 | 1 |
| `Creditors` | `MaturitiesOrExpirationPeriodsDimension` | `Within3Months` | 1 | 1 | 1 |
| `Creditors` | `GeographicSegmentsDimension` | `EnglandWales` | 1 | 1 | 1 |
| `CurrentAssets` | `OriginalRevisedDataDimension` | `Original` | 407,463 | 208,809 | 405,442 |
| `CurrentAssets` | `GroupCompanyDataDimension` | `Consolidated` | 10,779 | 2,850 | 8,291 |
| `CurrentAssets` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 8,260 | 2,762 | 8,258 |
| `CurrentAssets` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 8,157 | 2,656 | 8,155 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 4,027 | 3,701 | 4,027 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 1,755 | 1,003 | 1,752 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 1,330 | 836 | 1,324 |
| `CurrentAssets` | `RestatementsDimension` | `RestatedAmount` | 418 | 407 | 416 |
| `CurrentAssets` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 281 | 42 | 182 |
| `CurrentAssets` | `CharityFundsDimension` | `TotalEndowmentFunds` | 208 | 74 | 208 |
| `CurrentAssets` | `ConsolidationDimension` | `Consolidated` | 113 | 42 | 99 |
| `CurrentAssets` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 17 | 9 | 17 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 14 | 11 | 14 |
| `CurrentAssets` | `ContinuingDiscontinuedOperationsDimension` | `Non-currentAssetsDisposalGroupsHeldForSale` | 10 | 2 | 7 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 9 | 5 | 9 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 9 | 5 | 9 |
| `CurrentAssets` | `CharityFundsDimension` | `RestrictedIncomeFunds` | 7 | 4 | 7 |
| `CurrentAssets` | `OriginalRevisedDataDimension` | `Revised` | 6 | 3 | 5 |
| `CurrentAssets` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 5 | 3 | 5 |
| `CurrentAssets` | `GeographicSegmentsDimension` | `EnglandWales` | 3 | 2 | 3 |
| `CurrentAssets` | `ConsolidationDimension` | `ShareJoint-ventures` | 2 | 1 | 2 |
| `Debtors` | `FinancialInstrumentCurrentNon-currentDimension` | `CurrentFinancialInstruments` | 2,000,318 | 375,695 | 1,349,701 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `WithinOneYear` | 582,495 | 129,206 | 416,686 |
| `Debtors` | `OriginalRevisedDataDimension` | `Original` | 265,825 | 135,587 | 264,554 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `AfterOneYear` | 129,880 | 46,071 | 106,097 |
| `Debtors` | `FinancialInstrumentCurrentNon-currentDimension` | `Non-currentFinancialInstruments` | 110,924 | 26,990 | 80,958 |
| `Debtors` | `GroupCompanyDataDimension` | `Consolidated` | 7,346 | 1,894 | 5,627 |
| `Debtors` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 6,855 | 2,279 | 6,853 |
| `Debtors` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 6,815 | 2,221 | 6,813 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 1,721 | 1,585 | 1,718 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 904 | 594 | 899 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `AllPeriods` | 658 | 138 | 485 |
| `Debtors` | `RestatementsDimension` | `RestatedAmount` | 389 | 378 | 387 |
| `Debtors` | `CharityFundsDimension` | `TotalEndowmentFunds` | 179 | 67 | 179 |
| `Debtors` | `GroupCompanyDimension` | `Consolidated` | 115 | 43 | 101 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 61 | 59 | 61 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 27 | 18 | 27 |
| `Debtors` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 27 | 17 | 27 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 25 | 14 | 25 |
| `Debtors` | `OperatingActivitiesDimension` | `ContinuingOperationsIncludingAcquisitions` | 23 | 5 | 16 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 17 | 12 | 17 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `BetweenOneFiveYears` | 9 | 2 | 7 |
| `Debtors` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 9 | 4 | 9 |
| `Debtors` | `ProductsServicesDimension` | `ProductService1` | 8 | 8 | 8 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `BetweenTwoFiveYears` | 5 | 4 | 5 |
| `Debtors` | `RestatementsDimension` | `PriorPeriodIncreaseDecrease` | 3 | 2 | 3 |
| `Debtors` | `OriginalRevisedDataDimension` | `Revised` | 3 | 3 | 3 |
| `Debtors` | `FinancialInstrumentsClassesCategoriesDimension` | `FinancialAssetsAmortisedCost` | 2 | 1 | 2 |
| `Debtors` | `GeographicSegmentsDimension` | `NorthernIreland` | 2 | 1 | 2 |
| `Debtors` | `RestatementsDimension` | `MaterialErrorIncreaseDecrease` | 2 | 1 | 2 |
| `Debtors` | `FinancialInstrumentLevelDimension` | `Level1` | 2 | 1 | 2 |
| `Debtors` | `CurrencyDenominationFinancialInstrumentsDimension` | `USDollar` | 2 | 1 | 2 |
| `Debtors` | `MaturitiesOrExpirationPeriodsDimension` | `MoreThanFiveYears` | 1 | 1 | 1 |
| `Debtors` | `FinancialInstrumentValueTypeDimension` | `ContractualUndiscountedValue` | 1 | 1 | 1 |
| `Debtors` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 1 | 1 | 1 |
| `Equity` | `EquityClassesDimension` | `ShareCapital` | 19,949,779 | 2,550,746 | 12,402,470 |
| `Equity` | `EquityClassesDimension` | `RetainedEarningsAccumulatedLosses` | 19,113,466 | 2,417,624 | 11,866,475 |
| `Equity` | `EquityClassesDimension` | `SharePremium` | 944,766 | 137,776 | 604,749 |
| `Equity` | `EquityClassesDimension` | `RevaluationReserve` | 790,305 | 121,630 | 504,100 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 675,493 | 188,376 | 501,442 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShares` | 592,121 | 137,979 | 433,702 |
| `Equity` | `EquityClassesDimension` | `CapitalRedemptionReserve` | 492,409 | 50,807 | 302,417 |
| `Equity` | `OriginalRevisedDataDimension` | `Original` | 480,533 | 247,322 | 477,867 |
| `Equity` | `EquityClassesDimension` | `OtherReservesSubtotal` | 261,735 | 67,175 | 191,744 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShareClass1` | 177,959 | 74,816 | 161,430 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve1ComponentTotalEquity` | 173,901 | 26,257 | 114,615 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve3ComponentTotalEquity` | 153,721 | 20,410 | 100,277 |
| `Equity` | `EquityClassesDimension` | `OtherMiscellaneousReserve` | 118,335 | 18,063 | 79,296 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShareClass2` | 41,609 | 17,470 | 37,783 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 40,135 | 27,143 | 38,651 |
| `Equity` | `EquityClassesDimension` | `TotalEquityAttributableToOwnersParentBeforeNon-controllingInterests` | 37,239 | 7,782 | 25,844 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve2ComponentTotalEquity` | 28,028 | 3,964 | 18,147 |
| `Equity` | `GroupCompanyDataDimension` | `Consolidated` | 23,160 | 6,271 | 17,674 |
| `Equity` | `EquityClassesDimension` | `CapitalReserve` | 22,817 | 5,049 | 15,947 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShareClass3` | 21,176 | 8,872 | 19,216 |
| `Equity` | `EquityClassesDimension` | `InvestmentPropertiesRevaluationReserve` | 16,384 | 2,396 | 11,213 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShareClass4` | 11,019 | 4,670 | 10,045 |
| `Equity` | `EquityClassesDimension` | `HedgingReserve` | 8,187 | 1,396 | 5,123 |
| `Equity` | `EquityClassesDimension` | `CapitalContributionReserve` | 6,856 | 1,897 | 5,101 |
| `Equity` | `EquityClassesDimension` | `OtherCapitalInstrumentsClassifiedAsEquity` | 6,098 | 1,229 | 4,311 |
| `Equity` | `EquityClassesDimension` | `PropertiesRevaluationReserve` | 5,654 | 871 | 4,237 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOrdinaryShareClass5` | 5,509 | 2,329 | 5,021 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 5,342 | 3,251 | 5,336 |
| `Equity` | `EquityClassesDimension` | `SharePremiumOrdinaryShares` | 5,001 | 980 | 3,435 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShares` | 4,881 | 1,321 | 3,745 |
| `Equity` | `EquityClassesDimension` | `OtherCapitalReserve` | 4,066 | 999 | 3,050 |
| `Equity` | `EquityClassesDimension` | `ForeignCurrencyTranslationReserve` | 3,278 | 592 | 2,474 |
| `Equity` | `EquityClassesDimension` | `MergerReserve` | 2,685 | 449 | 2,001 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShareClass1` | 2,324 | 1,040 | 2,128 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOtherShareTypes` | 1,585 | 496 | 1,325 |
| `Equity` | `EquityClassesDimension` | `TreasurySharesOwnSharesReserve` | 1,454 | 268 | 979 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 1,215 | 801 | 985 |
| `Equity` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 447 | 106 | 322 |
| `Equity` | `EquityClassesDimension` | `AssetRevaluationSurplusReserve` | 359 | 94 | 271 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 321 | 237 | 318 |
| `Equity` | `EquityClassesDimension` | `Share-basedPaymentsReserve` | 287 | 66 | 211 |
| `Equity` | `EquityClassesDimension` | `Non-controllingInterests` | 285 | 97 | 225 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalSharePremiumSubtotal` | 267 | 139 | 257 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShareClass2` | 205 | 118 | 197 |
| `Equity` | `EquityClassesDimension` | `ConvertibleDebtEquityComponentReserve` | 171 | 76 | 153 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShareClass3` | 102 | 46 | 94 |
| `Equity` | `EquityClassesDimension` | `FurtherSpecificReserve4ComponentTotalEquity` | 88 | 35 | 80 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 85 | 49 | 85 |
| `Equity` | `EquityClassesDimension` | `Available-for-saleInvestmentsReserve` | 69 | 7 | 36 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOtherShareClass1` | 55 | 25 | 52 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShareClass4` | 40 | 20 | 39 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOtherShareClass2` | 39 | 17 | 36 |
| `Equity` | `EquityClassesDimension` | `SharePremiumPreferenceShares` | 25 | 13 | 25 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalPreferenceShareClass5` | 25 | 12 | 24 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOtherShareClass3` | 25 | 12 | 24 |
| `Equity` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 20 | 5 | 15 |
| `Equity` | `EquityClassesDimension` | `SharePremiumOtherShareTypes` | 15 | 7 | 14 |
| `Equity` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 15 | 4 | 11 |
| `Equity` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 14 | 7 | 14 |
| `Equity` | `EquityClassesDimension` | `SpecialReserveInvestmentFundsOnly` | 13 | 6 | 13 |
| `Equity` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 12 | 5 | 11 |
| `Equity` | `EquityClassesDimension` | `RevenueReservesInvestmentFundsOnly` | 10 | 7 | 10 |
| `Equity` | `EquityClassesDimension` | `ShareBuy-backReserve` | 10 | 6 | 9 |
| `Equity` | `CharityFundsDimension` | `RestrictedIncomeFunds` | 9 | 4 | 8 |
| `Equity` | `ProductsServicesDimension` | `ProductService2` | 8 | 8 | 8 |
| `Equity` | `ProductsServicesDimension` | `ProductService3` | 8 | 8 | 8 |
| `Equity` | `ProductsServicesDimension` | `ProductService1` | 8 | 8 | 8 |
| `Equity` | `EquityClassesDimension` | `WarrantReserve` | 6 | 3 | 6 |
| `Equity` | `EquityClassesDimension` | `ShareCapitalOtherShareClass4` | 5 | 3 | 5 |
| `Equity` | `EquityClassesDimension` | `ESOPReserve` | 5 | 2 | 4 |
| `Equity` | `OriginalRevisedDataDimension` | `Revised` | 5 | 5 | 5 |
| `Equity` | `EquityClassesDimension` | `TaxationReserve` | 5 | 4 | 5 |
| `Equity` | `CharityFundsDimension` | `UnrestrictedFundsDesignated` | 4 | 2 | 4 |
| `Equity` | `EquityClassesDimension` | `LegalStatutoryReserve` | 4 | 1 | 4 |
| `Equity` | `CharityFundsDimension` | `EndowmentFundsPermanent` | 4 | 1 | 3 |
| `Equity` | `EquityClassesDimension` | `CapitalReservesInvestmentFundsOnly` | 4 | 3 | 4 |
| `Equity` | `EquityClassesDimension` | `GoodwillReserve` | 3 | 1 | 3 |
| `Equity` | `CharityFundsDimension` | `TotalEndowmentFunds` | 2 | 1 | 2 |
| `Equity` | `EquityClassesDimension` | `GeneralBankingRisksReserve` | 1 | 1 | 1 |
| `Equity` | `SegmentReconciliationDimension` | `IncreaseDecreaseFromMaterialReconcilingItems` | 1 | 1 | 1 |
| `Equity` | `CharityFundsDimension` | `RevaluationReserveUnrestricted` | 1 | 1 | 1 |
| `Equity` | `EquityClassesDimension` | `AssetsDisposalGroupsHeldForSaleReserve` | 1 | 1 | 1 |
| `Equity` | `SegmentReconciliationDimension` | `OriginalSegmentValueBeforeAdjustments` | 1 | 1 | 1 |
| `Equity` | `OperatingSegmentsDimension` | `UnallocatedAmountReportableOperatingSegments` | 1 | 1 | 1 |
| `NetCurrentAssetsLiabilities` | `OriginalRevisedDataDimension` | `Original` | 460,036 | 236,654 | 457,661 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 92,180 | 37,945 | 92,153 |
| `NetCurrentAssetsLiabilities` | `GroupCompanyDataDimension` | `Consolidated` | 11,948 | 3,295 | 9,356 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 8,426 | 2,639 | 8,422 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 8,321 | 2,535 | 8,316 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 2,280 | 1,308 | 2,277 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 1,207 | 753 | 1,199 |
| `NetCurrentAssetsLiabilities` | `RestatementsDimension` | `RestatedAmount` | 435 | 427 | 434 |
| `NetCurrentAssetsLiabilities` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 290 | 43 | 187 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `TotalEndowmentFunds` | 219 | 75 | 219 |
| `NetCurrentAssetsLiabilities` | `GroupCompanyDimension` | `Consolidated` | 113 | 42 | 99 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 15 | 11 | 15 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 9 | 4 | 8 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 7 | 4 | 7 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 7 | 3 | 7 |
| `NetCurrentAssetsLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 6 | 2 | 6 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `RestrictedIncomeFunds` | 3 | 2 | 3 |
| `NetCurrentAssetsLiabilities` | `CharityFundsDimension` | `UnrestrictedFundsDesignated` | 2 | 2 | 2 |
| `NetCurrentAssetsLiabilities` | `GeographicSegmentsDimension` | `EnglandWales` | 2 | 1 | 2 |
| `NetCurrentAssetsLiabilities` | `OriginalRevisedDataDimension` | `Revised` | 2 | 2 | 2 |
| `NetCurrentAssetsLiabilities` | `GeographicSegmentsDimension` | `UnitedKingdom` | 1 | 1 | 1 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `PlantMachinery` | 6,530,129 | 857,733 | 4,162,634 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `FurnitureFittings` | 3,462,991 | 468,728 | 2,234,805 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ComputerEquipment` | 3,312,020 | 484,699 | 2,166,626 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `MotorVehicles` | 2,715,341 | 365,939 | 1,746,734 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `LandBuildings` | 1,827,868 | 245,758 | 1,161,044 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OtherPropertyPlantEquipment` | 1,337,741 | 199,071 | 854,491 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `FurnitureFittingsToolsEquipment` | 840,371 | 147,858 | 555,231 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OfficeEquipment` | 521,020 | 111,139 | 362,762 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Vehicles` | 474,899 | 82,247 | 306,543 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `LeaseholdImprovements` | 318,071 | 41,911 | 205,462 |
| `PropertyPlantEquipment` | `OriginalRevisedDataDimension` | `Original` | 219,504 | 111,386 | 218,577 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `MotorCars` | 92,653 | 18,486 | 61,009 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Buildings` | 81,540 | 12,774 | 53,609 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ToolsEquipment` | 78,674 | 13,779 | 53,095 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `InvestmentPropertyIncludedWithinPPE` | 62,442 | 12,015 | 44,357 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `LeasedAssetsHeldAsLessee` | 58,498 | 10,267 | 40,068 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `CommercialMotorVehicles` | 47,164 | 7,522 | 31,153 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Non-standardPPEClass1ComponentTotalPropertyPlantEquipment` | 39,946 | 6,809 | 26,733 |
| `PropertyPlantEquipment` | `GroupCompanyDataDimension` | `Consolidated` | 35,119 | 7,588 | 25,483 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ConstructionInProgressAssetsUnderConstruction` | 23,991 | 4,677 | 15,986 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `VehiclesPlantMachinery` | 7,936 | 1,309 | 5,297 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 6,370 | 2,071 | 6,367 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 6,331 | 2,019 | 6,327 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Non-standardPPEClass2ComponentTotalPropertyPlantEquipment` | 4,057 | 652 | 2,666 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Land` | 2,310 | 414 | 1,579 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Non-standardPPEClass3ComponentTotalPropertyPlantEquipment` | 2,091 | 359 | 1,380 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OtherVehicles` | 1,677 | 325 | 1,177 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 1,603 | 1,392 | 1,599 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `CommunicationNetworkEquipment` | 1,391 | 366 | 1,034 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 1,050 | 581 | 1,048 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 728 | 460 | 719 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `TotalPropertyPlantEquipmentOtherThanExplorationEvaluationAssets` | 402 | 70 | 269 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ShipsBoats` | 346 | 72 | 245 |
| `PropertyPlantEquipment` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 267 | 171 | 257 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `OwnedOrFreeholdAssets` | 242 | 118 | 218 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `AssetsNotYetAvailableForUsePPE` | 201 | 104 | 180 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `LongLeaseholdAssets` | 188 | 180 | 186 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `NetworkAssets` | 186 | 72 | 155 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `TotalEndowmentFunds` | 166 | 61 | 166 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Aircraft` | 157 | 34 | 105 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OilGasProductionAssets` | 76 | 71 | 74 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `AssetsHeldForUseUnderLeasesLessor` | 64 | 32 | 61 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `Right-of-useAssets` | 37 | 21 | 34 |
| `PropertyPlantEquipment` | `PPEOwnershipDimension` | `ShortLeaseholdAssets` | 31 | 14 | 28 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 21 | 16 | 21 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `TangibleExplorationEvaluationAssets` | 16 | 8 | 14 |
| `PropertyPlantEquipment` | `SegmentReconciliationDimension` | `OriginalSegmentValueBeforeAdjustments` | 16 | 6 | 14 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 12 | 6 | 11 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 12 | 6 | 11 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `Non-standardPPEClass4ComponentTotalPropertyPlantEquipment` | 12 | 10 | 12 |
| `PropertyPlantEquipment` | `ProductsServicesDimension` | `ProductService1` | 11 | 10 | 11 |
| `PropertyPlantEquipment` | `ProductsServicesDimension` | `ProductService2` | 10 | 9 | 10 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 10 | 10 | 10 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OtherMiningAssets` | 10 | 8 | 10 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `TotalMineProperties` | 7 | 3 | 6 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `ProducingMines` | 6 | 6 | 6 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `RestrictedIncomeFunds` | 4 | 3 | 4 |
| `PropertyPlantEquipment` | `SegmentReconciliationDimension` | `DecreaseFromEliminationIntersegmentAmounts` | 4 | 1 | 3 |
| `PropertyPlantEquipment` | `SegmentReconciliationDimension` | `IncreaseDecreaseFromMaterialReconcilingItems` | 4 | 1 | 3 |
| `PropertyPlantEquipment` | `OriginalRevisedDataDimension` | `Revised` | 4 | 2 | 3 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `OilDepotsStorageTanksServiceStations` | 3 | 2 | 3 |
| `PropertyPlantEquipment` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 3 | 1 | 3 |
| `PropertyPlantEquipment` | `OperatingSegmentsDimension` | `TotalReportableOperatingSegmentsIncludingAnyUnallocatedAmount` | 2 | 1 | 2 |
| `PropertyPlantEquipment` | `GeographicSegmentsDimension` | `TotalGeographicSegmentsIncludingAnyUnallocatedAmount` | 2 | 1 | 2 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `DeferredStrippingExpendituresForMineProperties` | 2 | 2 | 2 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `UnrestrictedFundsDesignated` | 2 | 2 | 2 |
| `PropertyPlantEquipment` | `ProductsServicesDimension` | `OtherProductsServices` | 1 | 1 | 1 |
| `PropertyPlantEquipment` | `PropertyPlantEquipmentClassesDimension` | `MiningAssetsUnderConstruction` | 1 | 1 | 1 |
| `PropertyPlantEquipment` | `ContinuingDiscontinuedOperationsDimension` | `Non-currentAssetsDisposalGroupsHeldForSale` | 1 | 1 | 1 |
| `PropertyPlantEquipment` | `CharityFundsDimension` | `EndowmentFundsExpendable` | 1 | 1 | 1 |
| `TotalAssetsLessCurrentLiabilities` | `OriginalRevisedDataDimension` | `Original` | 486,331 | 250,714 | 483,616 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `RestatedAmount` | 94,523 | 39,307 | 94,495 |
| `TotalAssetsLessCurrentLiabilities` | `GroupCompanyDataDimension` | `Consolidated` | 14,324 | 4,311 | 11,584 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `TotalUnrestrictedFunds` | 8,396 | 2,639 | 8,392 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `TotalRestrictedIncomeFunds` | 8,286 | 2,534 | 8,282 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `IncreaseDecreaseDueToTransitionFromPreviousStandard` | 3,262 | 1,882 | 3,258 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PreviouslyStatedAmount` | 1,017 | 642 | 1,012 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsDimension` | `RestatedAmount` | 336 | 324 | 335 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `TotalEndowmentFunds` | 219 | 75 | 219 |
| `TotalAssetsLessCurrentLiabilities` | `ContinuingDiscontinuedOperationsDimension` | `ContinuingOperations` | 121 | 19 | 80 |
| `TotalAssetsLessCurrentLiabilities` | `GroupCompanyDimension` | `Consolidated` | 95 | 38 | 86 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodIncreaseDecrease` | 16 | 11 | 16 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `AccountingPolicyChangeIncreaseDecrease` | 9 | 5 | 9 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `CumulativeEffectDateInitialApplicationIncreaseDecrease` | 4 | 2 | 4 |
| `TotalAssetsLessCurrentLiabilities` | `RestatementsFirstTimeAdoptionDimension` | `PriorPeriodErrorIncreaseDecrease` | 4 | 2 | 4 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `EndowmentFundsExpendable` | 2 | 1 | 2 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `RestrictedIncomeFunds` | 2 | 1 | 2 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `UnrestrictedFundsGeneral` | 2 | 1 | 2 |
| `TotalAssetsLessCurrentLiabilities` | `CharityFundsDimension` | `UnrestrictedFundsDesignated` | 2 | 1 | 2 |
| `TotalAssetsLessCurrentLiabilities` | `ProductsServicesDimension` | `OtherProductsServices` | 1 | 1 | 1 |
| `TotalAssetsLessCurrentLiabilities` | `OriginalRevisedDataDimension` | `Revised` | 1 | 1 | 1 |
| `TotalAssetsLessCurrentLiabilities` | `ContinuingDiscontinuedOperationsDimension` | `SpecificDiscontinuedOperation4` | 1 | 1 | 1 |
| `TotalAssetsLessCurrentLiabilities` | `ContinuingDiscontinuedOperationsDimension` | `SpecificDiscontinuedOperation3` | 1 | 1 | 1 |

## Required human decisions

- Select the final WIDE member column map from the histogram; no map is inferred here.
- Decide whether `PropertyPlantEquipment` members should be promoted to WIDE.
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
