# Reviewed accounts WIDE columns

The runnable v1 map is [`config/accounts-wide-columns.json`](../config/accounts-wide-columns.json). It was selected from the member histogram and reconciliation evidence in `accounts-qa.md`.

## Approved v1 columns

- Genuine non-dimensional totals for all nine locked concepts. `Creditors` is retained despite being about 96% null because a reported genuine total must not be replaced by dimensional components.
- `EquityClassesDimension/ShareCapital` as `equity_share_capital`.
- `EquityClassesDimension/RetainedEarningsAccumulatedLosses` as `equity_retained_earnings`.

The two Equity members have the strongest component coverage in the sample: 1,356 observations across 706 companies for Share Capital and 1,301 across 680 companies for Retained Earnings. Equity reconciliation is 95.8% with a median absolute difference of £0.

## Deliberate exclusions

- Every `RestatementsFirstTimeAdoptionDimension` member is excluded. This is a restatement axis, not an economic component axis.
- Other Equity members have less than 4% sample coverage and remain available only in LONG.
- PP&E members are deferred to v2. Raw names overlap economically, such as `MotorVehicles`, `Vehicles`, and `MotorCars`; promotion requires a reviewed class-normalisation map.
- Creditors members are gated. Their reconciliation agreement is 33.3% over 63 sample comparisons with a £9,833 median absolute difference. A larger sample must distinguish incomplete axes, sign flips, scale errors, and scope mismatches before promotion.

If Creditors members are later approved, maturity and financial-instrument current/non-current axes must remain separate. They describe different scopes and must never be unioned into the same WIDE column:

- Maturity: `WithinOneYear` (1,392 observations) and `AfterOneYear` (660) under `MaturitiesOrExpirationPeriodsDimension`. This is the recommended primary axis.
- Financial-instrument scope: `CurrentFinancialInstruments` (1,086) and `Non-currentFinancialInstruments` (453) under `FinancialInstrumentCurrentNon-currentDimension`.

The candidate maturity columns are `creditors_within_one_year` and `creditors_after_one_year`. Optional financial-instrument columns must use distinct names such as `creditors_fi_current` and `creditors_fi_noncurrent`; they must not be coalesced with the maturity columns.

## Remaining publication gates

- Characterise Creditors reconciliation on a larger sample before promoting its members.
- Run reconnaissance around 2010, 2013, and 2016 before selecting the dataset start year.
- Run the random regex-versus-lxml parser audit before full-history extraction.
- Obtain human approval for the Kaggle/OGL v3.0 framing.
