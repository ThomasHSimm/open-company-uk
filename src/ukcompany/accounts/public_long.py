"""The public LONG dataset: personal data removed, built as a filter over per-month Parquets.

See `docs/accounts-public-long-concepts.md` for the review and maintainer approval (2026-09-24)
behind `NUMERIC_DENYLIST` and `NON_NUMERIC_ALLOWLIST`. This module is the single source of
truth for both lists — reused by the builder here and by the staging guard
(`scripts/kaggle_staging_guard.py`) so the two can never silently drift apart. Never
re-extracts from source archives; only filters the existing `data/accounts/long/` Parquets.
"""

from __future__ import annotations

from pathlib import Path

from .ooc import DEFAULT_MEMORY_LIMIT_GB, DEFAULT_SPILL_DIR, _connect, _sql_literal

# Numeric facts: keep everything EXCEPT these person-related concepts (director, officer,
# key-management, related-party, remuneration, trustee). A single-director or single-trustee
# company turns a "company" figure into a fact about an identifiable individual, even with no
# name attached — see docs/accounts-public-long-concepts.md for the three explicitly-flagged
# borderline cases (NumberDirectors, AverageNumberDirectors, DirectorsGenderNotDisclosed) that
# were kept in this list by the maintainer's approved default.
NUMERIC_DENYLIST = frozenset(
    {
        "AccruedPensionEntitlementUnderDefinedBenefitSchemeDirectors",
        "AccruedPensionLumpSumPeriodEndDirectors",
        "AccruedPensionPeriodEndDirectors",
        "AdvancesCreditsDirectors",
        "AdvancesCreditsMadeInPeriodDirectors",
        "AdvancesCreditsRepaidInPeriodDirectors",
        "AmountDueFromToRelatedParty",
        "AmountPaidLiabilityIncurredInFulfillingGuaranteesDirectors",
        "AmountPaidLiabilityIncurredInFulfillingSpecificGuaranteeDirectors",
        "AmountReceivedOrReceivableUnderLong-termIncentiveSchemesDirectors",
        "AmountRemuneration",
        "AmountSpecificAdvanceOrCreditDirectors",
        "AmountSpecificAdvanceOrCreditMadeInPeriodDirectors",
        "AmountSpecificAdvanceOrCreditRepaidInPeriodDirectors",
        "AmountWrittenOffInPeriodInRespectDebtDueFromRelatedParty",
        "AmountsOwedByDirectors",
        "AmountsOwedByOtherRelatedPartiesOtherThanDirectors",
        "AmountsOwedToDirectors",
        "AmountsOwedToOtherRelatedPartiesOtherThanDirectors",
        "AverageNumberDirectors",
        "BenefitsInKindDirectors",
        "BenefitsReceivedOrReceivablePerformanceInMultipleReportingPeriodsDirectors",
        "BenefitsReceivedOrReceivablePerformanceInReportingPeriodDirectors",
        "BenefitsUnderLong-termIncentiveSchemesDirectors",
        "BonusesDirectors",
        "BonusesExcludingDirectors",
        "CashPaymentsOnDirectorsFees",
        "CompanyContributionsToDefinedBenefitPlansDirectors",
        "CompanyContributionsToDefinedBenefitSchemesDirectors",
        "CompanyContributionsToMoneyPurchasePlansDirectors",
        "CompanyContributionsToMoneyPurchaseSchemesDirectors",
        "CompensationForLossOfficeDirectors",
        "ContributionsToRemunerationTrust",
        "DirectorPensionsDefinedContributionSchemesAdministrativeExpenses",
        "DirectorRemuneration",
        "DirectorRemunerationBenefitsExcludingPaymentsToThirdParties",
        "DirectorRemunerationBenefitsIncludingPaymentsToThirdParties",
        "DirectorsFeesAdministrativeExpenses",
        "DirectorsGenderNotDisclosed",
        "DirectorsRemunerationAdministrativeExpenses",
        "DirectorsRemunerationCostSales",
        "DirectorsSalariesAdministrativeExpenses",
        "DirectorsSalariesCostSales",
        "DirectorsSalariesDistributionCosts",
        "DirectorsTotal",
        "DividendRecommendedByDirectors",
        "EmployersNationalInsuranceDirectorsAdministrativeExpenses",
        "EmployersNationalInsuranceDirectorsCostSales",
        "ExcessRetirementBenefitsOverOriginalEntitlementDirectors",
        "ExpenseAllowancesDirectors",
        "FeesDirectors",
        "GainLossOnExerciseShareOptionsDirectors",
        "KeyManagementPersonnelCompensationOtherLong-termBenefits",
        "KeyManagementPersonnelCompensationPost-employmentBenefits",
        "KeyManagementPersonnelCompensationShare-basedPayment",
        "KeyManagementPersonnelCompensationShort-termEmployeeBenefits",
        "KeyManagementPersonnelCompensationTerminationBenefits",
        "KeyManagementPersonnelCompensationTotal",
        "LoansFromDirectors",
        "LoansFromDirectorsAfterOneYear",
        "LoansFromDirectorsWithinOneYear",
        "LoansFromOtherRelatedPartiesOtherThanDirectors",
        "LoansToDirectors",
        "LoansToOtherRelatedPartiesOtherThanDirectors",
        "MaximumLiabilityUnderGuaranteesDirectors",
        "MaximumLiabilityUnderSpecificGuaranteeDirectors",
        "NetAssetsReceivedOrReceivableUnderLong-termIncentiveSchemesDirectors",
        "NumberDirectors",
        "NumberDirectorsAccruingBenefitsUnderDefinedBenefitScheme",
        "NumberDirectorsAccruingBenefitsUnderMoneyPurchaseScheme",
        "NumberDirectorsAccruingRetirementBenefits",
        "NumberDirectorsWhoExercisedShareOptions",
        "NumberDirectorsWhoReceivedOrWereEntitledToReceiveSharesUnderLongTermIncentiveSchemes",
        "NumberSharesInEntityOrItsUndertakingsDirectors",
        "NumberTrusteesReimbursedOrWhoHadExpensesPaidByCharityToThirdParties",
        "OtherStaffCostsDirectors",
        "OtherStaffCostsExcludingDirectors",
        "PaymentsToThirdPartiesForDirectorServices",
        "PensionCommitmentsRelatedToPensionsPayableToPastDirectors",
        "PensionsCostsDefinedBenefitSchemesExcludingDirectors",
        "PensionsCostsDefinedContributionSchemesExcludingDirectors",
        "ProvisionForDoubtfulDebtDueFromRelatedParty",
        "RecruitmentRemunerationServiceCosts",
        "SalariesDirectors",
        "SalariesFeesDirectors",
        "Share-basedPaymentsDirectors",
        "SocialSecurityCostsDirectors",
        "SocialSecurityCostsExcludingDirectors",
        "StaffCostsDirectors",
        "StaffCostsExcludingDirectors",
        "TaxableBenefitsDirectors",
        "TotalPension-relatedBenefitsDirectors",
        "TrusteesExpenses",
        "TrusteesRemunerationBenefits",
        "WagesSalariesExcludingDirectors",
    }
)

# Non-numeric facts: drop everything EXCEPT these structured, known-safe concepts (fails
# safe — a denylist can't be trusted to catch every risky field among 1,235 non-numeric
# concepts, many of which are free text that can contain names).
NON_NUMERIC_ALLOWLIST = frozenset(
    {
        "EndDateForPeriodCoveredByReport",
        "StartDateForPeriodCoveredByReport",
        "BalanceSheetDate",
        "DateAuthorisationFinancialStatementsForIssue",
        "DateApprovalAccounts",
        "UKCompaniesHouseRegisteredNumber",
        "NameProductionSoftware",
        "VersionProductionSoftware",
        "EntityDormantTruefalse",
        "EntityDormant",
        "EntityTradingStatus",
        "EntityTrading",
        "AccountingStandardsApplied",
        "AccountsStatusAuditedOrUnaudited",
        "LegalFormEntity",
        "AccountsTypeFullOrAbbreviated",
        "AccountsType",
    }
)


def build_public_long_duckdb(
    parts: str | Path,
    output_dir: str | Path,
    years: range,
    *,
    memory_limit_gb: int = DEFAULT_MEMORY_LIMIT_GB,
    spill_dir: str = DEFAULT_SPILL_DIR,
) -> dict[int, int]:
    """Write one filtered Parquet per year to `output_dir`, via `COPY ... TO ...` (never
    materialised in Python memory). Filters over the existing per-month Parquets only — never
    re-extracts. Returns `{year: rows_written}` (0 for a year with no matching source months,
    e.g. before the archive's start or after its end; no file is written for those years).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    numeric_list_sql = ", ".join(_sql_literal(c) for c in sorted(NUMERIC_DENYLIST))
    allow_list_sql = ", ".join(_sql_literal(c) for c in sorted(NON_NUMERIC_ALLOWLIST))
    parts_sql = _sql_literal(str(parts))
    written = {}
    for year in years:
        output_path = output_dir / f"accounts-long-public-{year}.parquet"
        query = f"""
            SELECT *
            FROM read_parquet({parts_sql})
            WHERE source_year = {int(year)}
              AND concept != 'EntityCurrentLegalOrRegisteredName'
              AND (
                (fact_kind = 'numeric' AND concept NOT IN ({numeric_list_sql}))
                OR (fact_kind = 'non-numeric' AND concept IN ({allow_list_sql}))
              )
        """
        connection = _connect(memory_limit_gb, spill_dir)
        try:
            count = connection.sql(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
            if count:
                connection.execute(
                    f"COPY ({query}) TO {_sql_literal(str(output_path))} "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            written[year] = int(count)
        finally:
            connection.close()
    return written
