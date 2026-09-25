# Public LONG dataset: numeric denylist and non-numeric allowlist (Task 5b)

**Human review gate — the maintainer approves both lists below before anything is staged to
`kaggle-long/`.** Built from `docs/accounts-concept-inventory.csv` (4,455 concepts, full
152-archive corpus). Nothing here has been applied to any file yet.

## Design

- **Numeric facts**: denylist. Keep everything except person-related concepts — a headcount
  of one (a single-director company, a single trustee) turns a "company" figure into a
  figure about an identifiable individual, even with no name attached.
- **Non-numeric facts**: allowlist, not a denylist. With 1,235 non-numeric concepts and free
  text everywhere (director names, addresses, signing officers, principal activity, policy
  narratives can all contain names), an allowlist fails safe — a denylist only works if every
  risky concept is correctly identified, and a single miss among 1,235 leaks. Only fields
  *known* to be safe are kept; everything else is dropped, including several fields that are
  probably harmless (see the appendix) but weren't on the task's named list.
- **Company name**: `EntityCurrentLegalOrRegisteredName` is dropped outright (explicit task
  instruction) — the company number already identifies the company, and small-company names
  are frequently a person's own name.

## Numeric denylist (95 concepts, 8,697,598 observations — 0.44% of all numeric observations)

Built by matching concept names against `director|officer|keymanagement|related.?party|
remuneration|trustee` (the task's named patterns, plus `trustee` added by hand: charity
trustees carry the same single-individual identifiability risk as directors, and
`TrusteesExpenses`/`NumberTrusteesReimbursedOrWhoHadExpensesPaidByCharityToThirdParties`
matched no other pattern). No other manual additions found beyond this on a targeted second
pass for `partner|proprietor|beneficial|connected.?person|highest.?paid`.

Top 20 by observation count (full 95-row list in
`docs/accounts-concept-inventory.csv`, filterable by this pattern):

| Concept | Observations |
|---|---:|
| `AdvancesCreditsDirectors` | 2,384,497 |
| `AdvancesCreditsMadeInPeriodDirectors` | 1,371,160 |
| `AmountsOwedToDirectors` | 1,106,552 |
| `AdvancesCreditsRepaidInPeriodDirectors` | 1,091,333 |
| `LoansFromDirectors` | 1,079,322 |
| `DirectorRemuneration` | 341,210 |
| `AmountSpecificAdvanceOrCreditDirectors` | 251,629 |
| `AmountsOwedByDirectors` | 228,497 |
| `AmountSpecificAdvanceOrCreditMadeInPeriodDirectors` | 172,436 |
| `AmountSpecificAdvanceOrCreditRepaidInPeriodDirectors` | 147,727 |
| `CompanyContributionsToMoneyPurchasePlansDirectors` | 98,479 |
| `AmountDueFromToRelatedParty` | 79,482 |
| `DirectorRemunerationBenefitsExcludingPaymentsToThirdParties` | 68,070 |
| `AmountsOwedToOtherRelatedPartiesOtherThanDirectors` | 63,826 |
| `DirectorRemunerationBenefitsIncludingPaymentsToThirdParties` | 62,285 |
| `NumberDirectorsAccruingBenefitsUnderMoneyPurchaseScheme` | 45,889 |
| `KeyManagementPersonnelCompensationTotal` | 17,110 |
| `CompanyContributionsToDefinedBenefitPlansDirectors` | 14,904 |
| `AmountsOwedByOtherRelatedPartiesOtherThanDirectors` | 12,323 |
| `LoansFromDirectorsAfterOneYear` | 12,056 |

The remaining 75 concepts range from 12,056 down to 1 observation each (mostly rare
concepts — `Share-basedPaymentsDirectors`, `TaxableBenefitsDirectors`, and similar, at 1-8
observations).

**Three borderline cases, flagged rather than silently decided:**

- `NumberDirectors` (12 obs) and `AverageNumberDirectors` (425 obs) are plain headcounts, not
  amounts — "this company has 2 directors" doesn't by itself reveal anything about an
  individual's pay or loans. **Included in the denylist by default** (conservative), but
  reasonable to move to the published set if the maintainer judges a bare headcount
  non-identifying.
- `DirectorsGenderNotDisclosed` (11 obs) is also count-shaped, but ties a demographic
  attribute to directors specifically; kept in the denylist.
- `NumberDirectorsAccruingBenefitsUnderMoneyPurchaseScheme` (45,889 obs) and its
  defined-benefit-scheme sibling (1,903 obs) are counts, but for a single-director company a
  count of "1" reveals that specific director has a specific benefit type — kept in the
  denylist.

## Non-numeric allowlist (12 concepts, 297,568,003 observations)

| Category | Concept | Observations |
|---|---|---:|
| Period dates | `EndDateForPeriodCoveredByReport` | 39,791,432 |
| Period dates | `StartDateForPeriodCoveredByReport` | 35,884,863 |
| Balance-sheet date | `BalanceSheetDate` | 38,476,070 |
| Authorisation date | `DateAuthorisationFinancialStatementsForIssue` | 28,222,157 |
| Authorisation date | `DateApprovalAccounts` | 7,166,971 |
| Registered number | `UKCompaniesHouseRegisteredNumber` | 35,418,151 |
| Filing software | `NameProductionSoftware` | 24,948,647 |
| Filing software | `VersionProductionSoftware` | 17,686,512 |
| Dormant flag | `EntityDormantTruefalse` | 28,226,781 |
| Dormant flag | `EntityDormant` | 7,191,928 |
| Trading status | `EntityTradingStatus` | 28,208,920 |
| Trading status | `EntityTrading` | 7,191,920 |
| Accounting standards | `AccountingStandardsApplied` | 27,843,582 |
| Audited/unaudited | `AccountsStatusAuditedOrUnaudited` | 27,842,022 |
| Legal form | `LegalFormEntity` | 24,867,730 |
| Accounts type | `AccountsTypeFullOrAbbreviated` | 18,018,647 |
| Accounts type | `AccountsType` | 9,837,059 |

(17 rows — two categories have both a `Truefalse`-suffixed and a plain variant in the
corpus, e.g. filer-software or taxonomy-version differences across years; both kept since
neither is redundant across the full span.)

**Everything else non-numeric is dropped** — including all of: names (`NameEntityOfficer`,
`DirectorSigningFinancialStatements`, `NameDirectorSigningAccounts`, `NameEntityAccountants`,
`NameAuthor`, `NameThirdPartyAgent`, `EntityCurrentLegalOrRegisteredName`), addresses
(`AddressLine1/2/3`, `PostalCodeZip`, `PrincipalLocation-CityOrTown`, `CountyRegion`),
`DescriptionPrincipalActivities`, every `*Policy` narrative concept (accounting policy
free text), every `Statement*`/`*Truefalse` compliance-boilerplate concept not in the table
above, and every other free-text description concept.

**Appendix — plausibly safe, excluded by default (not on the task's named list):**

| Concept | Observations | Why it might be safe |
|---|---:|---|
| `ScopeAccounts` | 8,010,652 | Categorical ("group"/"individual" scope), similar in kind to accounts type |
| `CountryFormationOrIncorporation` | 16,736,067 | Company-level jurisdiction fact, not personal |
| `PrincipalCurrencyUsedInBusinessReport` | 9,236,059 | A currency code, structured |
| `ReportPeriod` | 6,082,715 | Likely a period label/descriptor, possibly redundant with the date fields above |

These were excluded by the fail-safe default (only add what's explicitly named), not because
a specific risk was found. Flagging for an explicit maintainer decision rather than silently
adding or permanently excluding them.
