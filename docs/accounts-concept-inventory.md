# Accounts concept inventory

This is the Stage 1 data dictionary generated from the extracted accounts data (SQLite store or archived monthly Parquets). It reports source facts as read and does not correct or curate stored values.

- Archives represented: 152
- Source manifests: `Accounts_Monthly_Data-January2014.zip`, `Accounts_Monthly_Data-February2014.zip`, `Accounts_Monthly_Data-March2014.zip`, `Accounts_Monthly_Data-April2014.zip`, `Accounts_Monthly_Data-May2014.zip`, `Accounts_Monthly_Data-June2014.zip`, `Accounts_Monthly_Data-July2014.zip`, `Accounts_Monthly_Data-August2014.zip`, `Accounts_Monthly_Data-September2014.zip`, `Accounts_Monthly_Data-October2014.zip`, `Accounts_Monthly_Data-November2014.zip`, `Accounts_Monthly_Data-December2014.zip`, `Accounts_Monthly_Data-January2015.zip`, `Accounts_Monthly_Data-February2015.zip`, `Accounts_Monthly_Data-March2015.zip`, `Accounts_Monthly_Data-April2015.zip`, `Accounts_Monthly_Data-May2015.zip`, `Accounts_Monthly_Data-June2015.zip`, `Accounts_Monthly_Data-July2015.zip`, `Accounts_Monthly_Data-August2015.zip`, `Accounts_Monthly_Data-September2015.zip`, `Accounts_Monthly_Data-October2015.zip`, `Accounts_Monthly_Data-November2015.zip`, `Accounts_Monthly_Data-December2015.zip`, `Accounts_Monthly_Data-January2016.zip`, `Accounts_Monthly_Data-February2016.zip`, `Accounts_Monthly_Data-March2016.zip`, `Accounts_Monthly_Data-April2016.zip`, `Accounts_Monthly_Data-May2016.zip`, `Accounts_Monthly_Data-June2016.zip`, `Accounts_Monthly_Data-July2016.zip`, `Accounts_Monthly_Data-August2016.zip`, `Accounts_Monthly_Data-September2016.zip`, `Accounts_Monthly_Data-October2016.zip`, `Accounts_Monthly_Data-November2016.zip`, `Accounts_Monthly_Data-December2016.zip`, `Accounts_Monthly_Data-January2017.zip`, `Accounts_Monthly_Data-February2017.zip`, `Accounts_Monthly_Data-March2017.zip`, `Accounts_Monthly_Data-April2017.zip`, `Accounts_Monthly_Data-May2017.zip`, `Accounts_Monthly_Data-June2017.zip`, `Accounts_Monthly_Data-July2017.zip`, `Accounts_Monthly_Data-August2017.zip`, `Accounts_Monthly_Data-September2017.zip`, `Accounts_Monthly_Data-October2017.zip`, `Accounts_Monthly_Data-November2017.zip`, `Accounts_Monthly_Data-December2017.zip`, `Accounts_Monthly_Data-January2018.zip`, `Accounts_Monthly_Data-February2018.zip`, `Accounts_Monthly_Data-March2018.zip`, `Accounts_Monthly_Data-April2018.zip`, `Accounts_Monthly_Data-May2018.zip`, `Accounts_Monthly_Data-June2018.zip`, `Accounts_Monthly_Data-July2018.zip`, `Accounts_Monthly_Data-August2018.zip`, `Accounts_Monthly_Data-September2018.zip`, `Accounts_Monthly_Data-October2018.zip`, `Accounts_Monthly_Data-November2018.zip`, `Accounts_Monthly_Data-December2018.zip`, `Accounts_Monthly_Data-January2019.zip`, `Accounts_Monthly_Data-February2019.zip`, `Accounts_Monthly_Data-March2019.zip`, `Accounts_Monthly_Data-April2019.zip`, `Accounts_Monthly_Data-May2019.zip`, `Accounts_Monthly_Data-June2019.zip`, `Accounts_Monthly_Data-July2019.zip`, `Accounts_Monthly_Data-August2019.zip`, `Accounts_Monthly_Data-September2019.zip`, `Accounts_Monthly_Data-October2019.zip`, `Accounts_Monthly_Data-November2019.zip`, `Accounts_Monthly_Data-December2019.zip`, `Accounts_Monthly_Data-January2020.zip`, `Accounts_Monthly_Data-February2020.zip`, `Accounts_Monthly_Data-March2020.zip`, `Accounts_Monthly_Data-April2020.zip`, `Accounts_Monthly_Data-May2020.zip`, `Accounts_Monthly_Data-June2020.zip`, `Accounts_Monthly_Data-July2020.zip`, `Accounts_Monthly_Data-August2020.zip`, `Accounts_Monthly_Data-September2020.zip`, `Accounts_Monthly_Data-October2020.zip`, `Accounts_Monthly_Data-November2020.zip`, `Accounts_Monthly_Data-December2020.zip`, `Accounts_Monthly_Data-January2021.zip`, `Accounts_Monthly_Data-February2021.zip`, `Accounts_Monthly_Data-March2021.zip`, `Accounts_Monthly_Data-April2021.zip`, `Accounts_Monthly_Data-May2021.zip`, `Accounts_Monthly_Data-June2021.zip`, `Accounts_Monthly_Data-July2021.zip`, `Accounts_Monthly_Data-August2021.zip`, `Accounts_Monthly_Data-September2021.zip`, `Accounts_Monthly_Data-October2021.zip`, `Accounts_Monthly_Data-November2021.zip`, `Accounts_Monthly_Data-December2021.zip`, `Accounts_Monthly_Data-January2022.zip`, `Accounts_Monthly_Data-February2022.zip`, `Accounts_Monthly_Data-March2022.zip`, `Accounts_Monthly_Data-April2022.zip`, `Accounts_Monthly_Data-May2022.zip`, `Accounts_Monthly_Data-June2022.zip`, `Accounts_Monthly_Data-July2022.zip`, `Accounts_Monthly_Data-August2022.zip`, `Accounts_Monthly_Data-September2022.zip`, `Accounts_Monthly_Data-October2022.zip`, `Accounts_Monthly_Data-November2022.zip`, `Accounts_Monthly_Data-December2022.zip`, `Accounts_Monthly_Data-January2023.zip`, `Accounts_Monthly_Data-February2023.zip`, `Accounts_Monthly_Data-March2023.zip`, `Accounts_Monthly_Data-April2023.zip`, `Accounts_Monthly_Data-May2023.zip`, `Accounts_Monthly_Data-June2023.zip`, `Accounts_Monthly_Data-July2023.zip`, `Accounts_Monthly_Data-August2023.zip`, `Accounts_Monthly_Data-September2023.zip`, `Accounts_Monthly_Data-October2023.zip`, `Accounts_Monthly_Data-November2023.zip`, `Accounts_Monthly_Data-December2023.zip`, `Accounts_Monthly_Data-January2024.zip`, `Accounts_Monthly_Data-February2024.zip`, `Accounts_Monthly_Data-March2024.zip`, `Accounts_Monthly_Data-April2024.zip`, `Accounts_Monthly_Data-May2024.zip`, `Accounts_Monthly_Data-June2024.zip`, `Accounts_Monthly_Data-July2024.zip`, `Accounts_Monthly_Data-August2024.zip`, `Accounts_Monthly_Data-September2024.zip`, `Accounts_Monthly_Data-October2024.zip`, `Accounts_Monthly_Data-November2024.zip`, `Accounts_Monthly_Data-December2024.zip`, `Accounts_Monthly_Data-January2025.zip`, `Accounts_Monthly_Data-February2025.zip`, `Accounts_Monthly_Data-March2025.zip`, `Accounts_Monthly_Data-April2025.zip`, `Accounts_Monthly_Data-May2025.zip`, `Accounts_Monthly_Data-June2025.zip`, `Accounts_Monthly_Data-July2025.zip`, `Accounts_Monthly_Data-August2025.zip`, `Accounts_Monthly_Data-September2025.zip`, `Accounts_Monthly_Data-October2025.zip`, `Accounts_Monthly_Data-November2025.zip`, `Accounts_Monthly_Data-December2025.zip`, `Accounts_Monthly_Data-January2026.zip`, `Accounts_Monthly_Data-February2026.zip`, `Accounts_Monthly_Data-March2026.zip`, `Accounts_Monthly_Data-April2026.zip`, `Accounts_Monthly_Data-May2026.zip`, `Accounts_Monthly_Data-June2026.zip`, `Accounts_Monthly_Data-July2026.zip`, `Accounts_Monthly_Data-August2026.zip`
- Concepts: 4,455
- Observations: 1,968,393,998

Only the nine core concepts are validated for fill-rate and reconciliation. All other concepts are captured but unvalidated; rare concepts should not be trusted without checking this inventory and the source filing.

**`companies` is approximate.** Computed with `approx_n_unique` (HyperLogLog, ~2% typical error) rather than an exact distinct count, which does not fit in memory across all 2,592 concepts (the full (concept, company) pair set measured 338M+ rows for this corpus).

## Numeric versus non-numeric split

The input to the `numeric-only` scope dial (config `accounts.kinds`), not a decision made here. Free-text disclosures are the main size driver of the all-fact archive relative to a numeric-only one.

- Numeric observations: 903,014,823 (45.9%)
- Non-numeric observations: 1,065,379,175 (54.1%)

## Employee-count GBP-unit anomaly

`AverageNumberEmployeesDuringPeriod` facts whose unit resolved to GBP instead of a plain count — headcount should never carry a currency. Small values are very likely genuine headcounts with a mis-tagged unit (kept, unit ignored); large values are very likely a different, mis-tagged monetary fact. The pivot does not filter employee facts by currency regardless of this split (see accounts-qa report limitations).

- GBP-tagged employee facts: 7,751,582
- Value range: -46.0 – 99499000.0 (median 1.0)
- Below 100,000 (plausible headcount): 7,715,955
- At or above 100,000 (likely mis-tagged): 281

## Read-correctness audit

- Non-numeric facts with non-null `numeric_value`: **0**
- Numeric facts with a missing or unresolved `unit`: **36,119**

### Non-numeric coercions by concept

None found.

### Numeric unit gaps by concept

| Concept | Rows |
|---|---:|
| `CalledUpShareCapital` | 5,251 |
| `Debtors` | 4,444 |
| `ProfitLossAccountReserve` | 3,754 |
| `CreditorsDueWithinOneYear` | 3,710 |
| `CashBankInHand` | 3,339 |
| `TangibleFixedAssets` | 2,533 |
| `ShareCapitalAllottedCalledUpPaid` | 2,161 |
| `ParValueShare` | 2,002 |
| `TangibleFixedAssetsCostOrValuation` | 1,191 |
| `TangibleFixedAssetsDepreciationChargedInPeriod` | 1,012 |
| `TangibleFixedAssetsDepreciation` | 885 |
| `CreditorsDueAfterOneYear` | 845 |
| `StocksInventory` | 829 |
| `TangibleFixedAssetsAdditions` | 650 |
| `RevaluationReserve` | 496 |
| `IntangibleFixedAssets` | 446 |
| `InvestmentsFixedAssets` | 381 |
| `BankBorrowingsOverdrafts` | 259 |
| `IntangibleFixedAssetsAmortisationChargedInPeriod` | 217 |
| `BankOverdrafts` | 205 |
| `IntangibleFixedAssetsCostOrValuation` | 205 |
| `Long-termBorrowingsBookValue` | 188 |
| `IntangibleFixedAssetsAggregateAmortisationImpairment` | 176 |
| `CapitalRedemptionReserve` | 136 |
| `BankBorrowings` | 130 |
| `TangibleFixedAssetsDisposals` | 102 |
| `ProvisionsForLiabilitiesCharges` | 96 |
| `OtherReserves` | 89 |
| `SharePremiumAccount` | 89 |
| `ObligationsUnderFinanceLeaseHirePurchaseContractsWithinOneYear` | 62 |
| `IntangibleFixedAssetsAdditions` | 56 |
| `TangibleFixedAssetsDepreciationDecreaseIncreaseOnDisposals` | 47 |
| `TangibleFixedAssetsIncreaseDecreaseFromRevaluations` | 39 |
| `CurrentAssetInvestments` | 26 |
| `ShareholderFunds` | 20 |
| `TotalAssetsLessCurrentLiabilities` | 20 |
| `NetCurrentAssetsLiabilities` | 7 |
| `CurrentAssets` | 6 |
| `IntangibleFixedAssetsDisposals` | 6 |
| `IntangibleFixedAssetsAmortisationDecreaseIncreaseOnDisposals` | 3 |
| `TotalRecognisedGainLossForPeriod` | 3 |
| `ProfitLossOnOrdinaryActivitiesAfterTax` | 2 |
| `OtherCreditorsDueWithinOneYear` | 1 |

## Anomaly flags

These flags are review cues, not corrections.

### Mixed numeric/non-numeric kind (1)

`NumberOwnSharesPurchased`

### Multiple incompatible unit families (71)

| Concept | Units |
|---|---|
| `AverageNumberEmployeesDuringPeriod` | `EUR`, `EUR/shares`, `GBP`, `ONE`, `USD`, `employee`, `employeeNumber`, `employees`, `numberOfEmployee`, `person`, `pure`, `shares` |
| `ParValueShare` | `AED/shares`, `AFA`, `AFN`, `ARS`, `AUD`, `BGN`, `BRL`, `CAD`, `CHF`, `CNY`, `CZK`, `DKK`, `EGP`, `EUR`, `EUR/shares`, `GBP`, `GBP/shares`, `GIP`, `GMD`, `HKD`, `HRK`, `HUF`, `ILS`, `INR`, `IRR`, `ISK`, `JPY`, `KES`, `KRW`, `KWD`, `MAD`, `MGA`, `MRO`, `NGN`, `NOK`, `NZD`, `PKR`, `PLN`, `QAR`, `RUB`, `SAR`, `SEK`, `THB`, `TRY`, `TTD`, `UAH`, `USD`, `USD/shares`, `UYU`, `XCD`, `XDR`, `XOF`, `ZAR`, `pure`, `shares`, `shares/GBP` |
| `DepreciationRateUsedForPropertyPlantEquipment` | `GBP`, `USD`, `pure` |
| `AdministrationSupportAverageNumberEmployees` | `GBP`, `employee`, `pure` |
| `ApplicableTaxRate` | `GBP`, `Rate`, `USD`, `pure` |
| `DividendPerShareInterim` | `GBP`, `GBP/shares`, `USD`, `pure` |
| `UsefulLifePropertyPlantEquipmentYears` | `GBP`, `pure` |
| `AmortisationRateUsedForIntangibleAssets` | `GBP`, `pure` |
| `ProductionAverageNumberEmployees` | `GBP`, `numberOfEmployee`, `pure` |
| `NumberDirectorsAccruingBenefitsUnderMoneyPurchaseScheme` | `GBP`, `employee`, `pure` |
| `OwnershipInterestInSubsidiaryPercent` | `GBP`, `pure` |
| `PercentageSubsidiaryHeld` | `GBP`, `pure` |
| `DividendPerShareFinal` | `GBP`, `GBP/shares`, `USD`, `pure` |
| `OtherDepartmentsAverageNumberEmployees` | `GBP`, `employee`, `pure` |
| `UsefulLifeIntangibleAssetsYears` | `GBP`, `pure` |
| `NumberEquityInstrumentsOutstandingShare-basedPaymentArrangement` | `GBP`, `pure`, `shares` |
| `WeightedAverageExercisePriceEquityInstrumentsOutstandingShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `USD/shares`, `pure`, `shares` |
| `EmployeesTotal` | `GBP`, `pure` |
| `OwnershipInterestInAssociatePercent` | `GBP`, `pure` |
| `NumberEquityInstrumentsExercisableShare-basedPaymentArrangement` | `GBP`, `pure` |
| `WeightedAverageExercisePriceEquityInstrumentsExercisableShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `USD/shares`, `pure`, `shares` |
| `NumberEquityInstrumentsGrantedShare-basedPaymentArrangement` | `GBP`, `USD`, `pure`, `shares` |
| `WeightedAverageExercisePriceEquityInstrumentsGrantedShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `USD/shares`, `pure`, `shares` |
| `WeightedAverageExercisePriceEquityInstrumentsForfeitedShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `USD/shares`, `pure`, `shares` |
| `NumberEquityInstrumentsForfeitedShare-basedPaymentArrangement` | `GBP`, `pure`, `shares` |
| `MarketingAverageNumberEmployees` | `numberOfEmployee`, `pure` |
| `DiscountRateUsedDefinedBenefitPlan` | `GBP`, `Rate`, `pure` |
| `WeightedAverageExercisePriceEquityInstrumentsExercisedShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `USD/shares`, `pure`, `shares` |
| `NumberDirectorsAccruingBenefitsUnderDefinedBenefitScheme` | `GBP`, `employee`, `pure` |
| `NumberEquityInstrumentsExercisedShare-basedPaymentArrangement` | `GBP`, `USD`, `pure`, `shares` |
| `AssumedRateIncreasePensionsInPaymentDeferredPensions` | `Rate`, `pure` |
| `DividendPerShareProposedButNotPaid` | `pure`, `shares` |
| `AssumedRateIncreasePensionableSalaries` | `Rate`, `pure` |
| `WeightedAverageExercisePriceEquityInstrumentsExpiredShare-basedPaymentArrangement` | `GBP`, `GBP/shares`, `USD`, `pure`, `shares` |
| `NumberEmployeesDate` | `GBP`, `pure` |
| `NumberEquityInstrumentsExpiredShare-basedPaymentArrangement` | `GBP`, `pure` |
| `DividendPerShare` | `EUR`, `GBP`, `GBP/shares` |
| `DepreciationRateUsedForPropertyPlantEquipmentIncludingRight-of-use` | `GBP`, `pure` |
| `NumberDirectorsAccruingRetirementBenefits` | `GBP`, `pure` |
| `AverageNumberDirectors` | `GBP`, `pure` |
| `AssumedRateInflation-RPI` | `Rate`, `pure` |
| `NumberDirectorsWhoReceivedOrWereEntitledToReceiveSharesUnderLongTermIncentiveSchemes` | `employee`, `pure` |
| `EmissionsDirectTotal` | `pure`, `t`, `tCO2e` |
| `AssumedRateInflation-CPI` | `GBP`, `Rate`, `pure` |
| `EnergyConsumptionUsedToCalculateEmissions` | `KWH`, `pure` |
| `BasicEarningsLossPerShare` | `GBP`, `GBP/shares`, `USD/shares`, `pure`, `shares` |
| `DilutedEarningsLossPerShare` | `GBP`, `GBP/shares`, `USD/shares`, `pure`, `shares` |
| `EmissionsIndirectTotal` | `pure`, `tCO2e` |
| `EmissionsDirectStationaryCombustion` | `pure`, `tCO2e` |
| `UsefulLifePropertyPlantEquipmentIncludingRight-of-useYears` | `Y`, `pure` |
| `EmissionsIndirectElectricity` | `pure`, `t`, `tCO2e` |
| `EmissionsDirectMobileCombustionTransport` | `pure`, `tCO2e` |
| `EmissionsGrossTotal` | `pure`, `t`, `tCO2e` |
| `RedemptionValueRedeemablePreferenceShares` | `GBP`, `GBP/shares`, `pure`, `shares` |
| `EnergyConsumptionElectricity` | `KWH`, `pure` |
| `EnergyConsumptionCombustionGas` | `KWH`, `pure` |
| `EnergyConsumptionCombustionTransportFuel` | `KWH`, `miles`, `pure` |
| `EmissionsOtherIndirectTotal` | `pure`, `t` |
| `TaxRateIncreaseDecreaseFromEffectForeignTaxRates` | `GBP`, `pure` |
| `WeightedAverageSharePriceDateExerciseOrDuringPeriodShare-basedPaymentArrangement` | `GBP`, `pure` |
| `DividendPerShareFirstInterim` | `GBP`, `GBP/shares`, `pure` |
| `NumberEquityInstrumentsTransferredInFromOutToGroupEntitiesShare-basedPaymentArrangement` | `GBP`, `pure` |
| `AverageLeaseTermInYearsPropertyPlantEquipmentLeasedUnderFinanceLeases` | `GBP`, `pure` |
| `TaxRateDecreaseFromTaxLossesForWhichNoDeferredTaxAssetWasRecognised` | `GBP`, `pure` |
| `TaxRateIncreaseDecreaseFromEffectExpensesNotDeductibleInDeterminingTaxableProfitTaxLoss` | `GBP`, `pure` |
| `DividendPerShareSecondInterim` | `GBP`, `GBP/shares`, `pure` |
| `WeightedAverageExercisePriceEquityInstrumentsTransferredInFromOutToGroupEntitiesShare-basedPaymentArrangement` | `GBP`, `pure`, `shares` |
| `OtherTaxRateIncreaseDecreaseTaxRateReconciliation` | `GBP`, `pure` |
| `CapitalisationRateForCapitalisedBorrowingCostsGeneralBorrowingsPool` | `GBP`, `pure` |
| `TaxRateIncreaseDecreaseFromAdjustmentTaxForPriorPeriods` | `GBP`, `pure` |
| `NumberYearsOverWhichArrangementVests` | `GBP`, `pure` |

### Mixed instant/duration context (3)

`NumberSharesAllotted`, `RawMaterialsConsumables`, `CashCashEquivalentsCashFlowValue`

### Name-versus-kind mismatch (41)

| Concept | Reason |
|---|---|
| `StatementThatThereWereNoGainsLossesInPeriodOtherThanThoseInProfitLossAccount` | numeric-like name has non-numeric facts |
| `OutstandingPre-paidContributionsToDefinedContributionPlanReportingDate` | text-like name has numeric facts |
| `DividendsDeclaredAfterReportingDate` | text-like name has numeric facts |
| `NumberEmployeesDate` | text-like name has numeric facts |
| `DateValuationTangibleFixedAssets` | numeric-like name has non-numeric facts |
| `AggregateDividendsDueBalanceSheetDate` | text-like name has numeric facts |
| `EquityInterestsAcquirerUsedInAcquisitionFairValueAcquisitionDate` | text-like name has numeric facts |
| `BasisValuationTangibleFixedAssets` | numeric-like name has non-numeric facts |
| `AdministrationSupportNumberEmployeesDate` | text-like name has numeric facts |
| `EffectiveDateRevaluationIntangibleAssets` | numeric-like name has non-numeric facts |
| `OutstandingPre-paidContributionsToDefinedContributionSchemeBalanceSheetDate` | text-like name has numeric facts |
| `AggregateMarketValueListedInvestmentsDate` | text-like name has numeric facts |
| `Non-controllingInterestInAcquiredEntityRecognisedAcquisitionDate` | text-like name has numeric facts |
| `StatementOnNon-disclosureInformationOnContingentLiabilities` | numeric-like name has non-numeric facts |
| `InvestmentCompanyPolicyOnAllocatingFinanceCostsBetweenRevenueCapital` | numeric-like name has non-numeric facts |
| `NetContingentLiabilitiesAssetsIndemnificationAssetsRecognisedAcquisitionDate` | text-like name has numeric facts |
| `EntityRelyingOnExemptionUnderCompaniesActInNotPublishingItsOwnProfitLossAccount` | numeric-like name has non-numeric facts |
| `OtherDepartmentsNumberEmployeesDate` | text-like name has numeric facts |
| `OutstandingPre-paidContributionsToDefinedBenefitPlanReportingDate` | text-like name has numeric facts |
| `GeneralDescriptionFinancialAssetsPastDueButNotImpairedIncludingCollateralHeldFairValue` | numeric-like name has non-numeric facts |
| `ProductionNumberEmployeesDate` | text-like name has numeric facts |
| `GeneralDescriptionImpairedFinancialAssetsIncludingCollateralHeldFairValue` | numeric-like name has non-numeric facts |
| `LocalNumber` | numeric-like name has non-numeric facts |
| `StatementOnOpenMarketValueNon-specialisedPropertiesCarriedOnBasisExistingUseValue` | numeric-like name has non-numeric facts |
| `SellingNumberEmployeesDate` | text-like name has numeric facts |
| `StatementOnNon-disclosureInformationOnContingentAssets` | numeric-like name has non-numeric facts |
| `OtherTangibleOrIntangibleAssetsTransferredFairValueAcquisitionDate` | text-like name has numeric facts |
| `BalancesHeldAsAgentReportingDate` | text-like name has numeric facts |
| `ConditionsToObtainRolloverReliefOnGainOnSaleAssetWhichExpectedToBeRolledOverIntoReplacementAssets` | numeric-like name has non-numeric facts |
| `ExplanationReasonsForDeferredIncome` | numeric-like name has non-numeric facts |
| `GeneralDescriptionFinancialAssetsTransferredWhichDoNotQualifyForDerecognitionIncludingExposuresRelationshipWithAssociatedLiabilities` | numeric-like name has non-numeric facts |
| `LiabilitiesIncurredFairValueAcquisitionDate` | text-like name has numeric facts |
| `MarketingNumberEmployeesDate` | text-like name has numeric facts |
| `SalesMarketingDistributionNumberEmployeesDate` | text-like name has numeric facts |
| `GeneralDescriptionImpairedFinancialAssetsTogetherWithCollateralHeldFairValue` | numeric-like name has non-numeric facts |
| `OutstandingPre-paidContributionsToDefinedBenefitSchemeBalanceSheetDate` | text-like name has numeric facts |
| `ReasonsForAdoptingMethodValuationWhichNotMarketValue` | numeric-like name has non-numeric facts |
| `BasisAllocationBetweenActivitiesDefinedContributionPensionLiabilityExpense` | numeric-like name has non-numeric facts |
| `GeneralDescriptionValuationFinancialAssetsLiabilities` | numeric-like name has non-numeric facts |
| `OtherTangibleOrIntangibleAssetsReceivedFairValueDisposalDate` | text-like name has numeric facts |
| `Share-basedPaymentLiabilitiesTransferredFromAcquiredEntityFairValueAcquisitionDate` | text-like name has numeric facts |

## CSV data dictionary

`accounts-concept-inventory.csv` contains one row per concept, sorted by observation count. `example_values` is a compact JSON array of up to three distinct source-text examples; examples are whitespace-normalised and truncated to 120 characters only for display.
