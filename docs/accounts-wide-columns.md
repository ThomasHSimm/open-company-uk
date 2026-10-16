# Reviewed accounts WIDE columns

The runnable v1 map is [`config/accounts-wide-columns.json`](../config/accounts-wide-columns.json). It was selected from the member histogram and reconciliation evidence in `accounts-qa.md`.

## Published columns

The shipped WIDE column set (both `as_first_reported` and `latest`), matching the
runnable map in `config/accounts-wide-columns.json`:

- Genuine non-dimensional totals for all nine locked concepts. `Creditors` is retained despite being about 96% null because a reported genuine total must not be replaced by dimensional components.
- `EquityClassesDimension/ShareCapital` as `equity_share_capital`.
- `EquityClassesDimension/RetainedEarningsAccumulatedLosses` as `equity_retained_earnings`.
- `MaturitiesOrExpirationPeriodsDimension/WithinOneYear` as `creditors_within_one_year`.
- `MaturitiesOrExpirationPeriodsDimension/AfterOneYear` as `creditors_after_one_year`.

The two Creditors maturity members were **gated in v1 and are now published in v2**
(see "Promoted in v2" below). The two Equity members have the strongest component
coverage: 1,356 observations across 706 companies for Share Capital and 1,301 across
680 companies for Retained Earnings. Equity reconciliation is 95.8% with a median
absolute difference of £0.

## Promoted in v2

- The two Creditors **maturity** members (`creditors_within_one_year`,
  `creditors_after_one_year`, under `MaturitiesOrExpirationPeriodsDimension`) are
  now published. On the development sample their reconciliation agreement was only
  33.3% over 63 comparisons (£9,833 median absolute difference), so treat them as a
  **maturity split of a reported total, not an audited figure** — the sparse
  `Creditors` total remains the conservative choice where exactness matters.

## Deliberate exclusions

- Every `RestatementsFirstTimeAdoptionDimension` member is excluded. This is a restatement axis, not an economic component axis.
- Other Equity members have less than 4% sample coverage and remain available only in LONG.
- PP&E members remain excluded (the PP&E *total* `PropertyPlantEquipment` is published; the members are not). Raw names overlap economically, such as `MotorVehicles`, `Vehicles`, and `MotorCars`; promotion requires a reviewed class-normalisation map.
- The Creditors **financial-instrument** current/non-current members are **not**
  published and must never be unioned with the maturity columns above. The two axes
  describe different scopes:

- Maturity: `WithinOneYear` (1,392 observations) and `AfterOneYear` (660) under `MaturitiesOrExpirationPeriodsDimension`. This is the recommended primary axis.
- Financial-instrument scope: `CurrentFinancialInstruments` (1,086) and `Non-currentFinancialInstruments` (453) under `FinancialInstrumentCurrentNon-currentDimension`.

The published maturity columns are `creditors_within_one_year` and `creditors_after_one_year`. Any future financial-instrument columns must use distinct names such as `creditors_fi_current` and `creditors_fi_noncurrent`; they must not be coalesced with the maturity columns.

## Remaining publication gates

- The Creditors maturity members have been promoted (v2); continue to characterise
  their reconciliation on larger samples, and gate any *financial-instrument*
  Creditors members on the same evidence before promoting those.
- Run reconnaissance around 2010, 2013, and 2016 before selecting the dataset start year.
- Run the random regex-versus-lxml parser audit before full-history extraction.
- Obtain human approval for the Kaggle/OGL v3.0 framing.
