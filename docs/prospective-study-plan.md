# Prospective validation study: plan and pre-registration

*Design document. Nothing here has been executed beyond freezing the baseline and
the sample. The only future work is the two API outcome fetches and the
pre-registered analysis described in §5 and §6.*

## 0. Why this design

The only honest test of a prediction signal is to fix it **before** the outcomes
exist and check it against what actually happens. The maintainer does not want to
collect monthly bulk snapshots indefinitely, and does not need to: the Companies
House API keeps a company's insolvency history retrievable even after dissolution
(§4.4), so the outcome can be read with **one API fetch per horizon** rather than
from a monthly snapshot series. This document freezes a baseline now and
pre-registers everything that will be computed later, so the analysis cannot be
tuned to the result.

## 1. The frozen baseline (done)

The baseline is the October 2026 **governed** point-in-time join, reference month
**T = 2026-09**.

| Artefact | Path | sha256 |
|---|---|---|
| Joined feature table | `data/join/v1-internal-202609/governed/joined_company_features.parquet` | `909414cb617ce3862954cb55dff1bde54983a7898cb7ec0c02f15026e098e031` |
| Governed join manifest | `data/join/v1-internal-202609/governed/join_manifest.json` | `d93c82f3aa57d95e5d168728bcda619a5400ffb9f2c3b0a8656296d7f5174ef1` |
| Root join manifest | `data/join/v1-internal-202609/join_manifest.json` | `6a3b44bcc8454f2a4edb1aca95fb437ad9a19ea8bb7f0e74f53e5dd75f9476a5` |

The join pairs the **2026-10-01 register** snapshot, the **2026-09-25 PSC**
snapshot, and accounts available in registration month **≤ 2026-09**. It carries
**5,704,711** companies (the live register; dissolved companies are not in the
`BasicCompanyData` product) across 63 feature columns. Both source snapshots are
irreplaceable — see `docs/data-retention.md`.

### 1.1 The frozen study sample (done — v2, risk-stratified)

Fetching the whole register at two horizons is infeasible, so a sample is frozen.
It was produced by `scripts/freeze_prospective_sample.py` (deterministic: fixed
seed `20260912`, reproducible from the join hash above):

| Artefact | Path | sha256 |
|---|---|---|
| Sample (company numbers + weights) | `data/prospective/study-sample.csv` | `9d6926b62dff526748f39b1fd71dac92ab5a24e3e8a4311def4019918fd74cf7` |
| Sample sidecar (strata, seed, weights, rates) | `data/prospective/study-sample.strata.json` | `93985b408af50dce826639812d7728702830587c5279e0e26395630d9f1b522b` |

Both files are **private and gitignored** (`data/`); only the hashes are
committed. (This supersedes a v1 status-only sample — see `docs/AUDIT.md` for the
retired hash and the reason.)

**The target is *incident* adverse insolvency** — a company *entering* a
non-solvent liquidation / administration / receivership / voluntary arrangement
within a horizon, having not already been in one at baseline. So the budget is
concentrated where incident events can actually occur. Strata A and B are
**already in an insolvency state at baseline**: they cannot produce incident
events and are kept only as **small descriptive samples** — A to describe how
in-process companies progress (resolution to dissolution / MVL / CVL), B as the
ground-truth set for the members'- vs creditors'-voluntary-liquidation case-type
classifier (§4.3). They are **excluded from the incident numerator and
denominator**. The remaining budget goes to the at-risk population,
sub-stratified by baseline compliance markers whose adverse-transition rate was
**measured on the Aug-2026 → Oct-2026 governed register snapshots** (two-month
rate × 6):

| Cell | Baseline definition | Population | Sampled | Weight | Measured rate/yr | Role |
|---|---|---:|---:|---:|---:|---|
| A live insolvency process | administration / receivership / VA (all spellings) | 7,318 | 2,000 | 3.66 | — | descriptive (progression) |
| B liquidation | liquidation (solvency unknown until fetched) | 108,330 | 2,000 | 54.16 | — | descriptive (classifier validation) |
| C strike-off proposal | active – proposal to strike off | 423,006 | 20,000 | 21.15 | 1.13 % | incident + dissolution outcome |
| D1 accounts overdue | active, `accounts.overdue` | 93,785 | 38,000 | 2.47 | **5.40 %** | incident (dominant source) |
| D2 CS overdue | active, not D1, `confirmation_statement.overdue` | 245,631 | 10,000 | 24.56 | 0.83 % | incident |
| D3 charges | active, not D1/D2, charges outstanding | 595,358 | 10,000 | 59.54 | 0.75 % | incident |
| D4 base | active, no marker | 4,231,283 | 33,000 | 128.22 | 0.35 % | incident (population anchor) |

Total **115,000** companies. The cells are **disjoint** (precedence D1 → D2 → D3
→ D4), so inclusion probabilities are exact and `sampling_weight =
population / sampled` recovers the true population prevalence for average
precision at the base rate (§6). The allocation maximises expected incident
positives (§5) while keeping the base cell D4 large enough (33k) to anchor the
population-weighted metrics and keeping D2/D3 estimable.

Markers `accounts.overdue` and `confirmation_statement.overdue` are also partly
*consequences* of an adverse process (§6); selecting on them is legitimate —
inclusion probability depends only on observed baseline features, so weighted
estimates stay unbiased — and the leakage concern is handled in the analysis by
the with/without-compliance contrast, not in the sampling.

**The frozen rule.** Once the first outcome fetch (§3) is run, nothing about the
baseline join or the sample may change — not the sample, not the strata, not the
feature definitions. Until then the sample may be re-frozen with different sizes
by re-running the script (the hashes above must then be updated here and in
`docs/AUDIT.md`); after outcomes begin arriving the hashes are final.

## 2. Horizons

Anchor date **T0 = 2026-10-01** (the baseline register date — the latest observed
state of every sampled company).

| Horizon | Window end | Fetch on/after | Role |
|---|---|---|---|
| +6 months | 2027-04-01 | 2027-04-05 | secondary (optional — see §3.3) |
| +12 months | 2027-10-01 | 2027-10-05 | **primary endpoint** |

A few days' delay after each window end lets the register and insolvency filings
settle. There is no monthly snapshot sequence to maintain; each horizon is a
single API pass.

## 3. The outcome, from one API fetch per horizon

### 3.1 What to fetch

For every sampled company fetch only:

1. the company **profile** (`/company/{number}`), and
2. **`/company/{number}/insolvency`** where the profile's `links.insolvency` is
   present.

No officers or PSC endpoints. `ukcompany run` (via `fetch_companies`) also fetches
officers, PSC and PSC-statements, which would multiply the request budget four- to
five-fold, so the study uses a dedicated **profile-and-insolvency-only** path,
`ukcompany prospective-fetch` (`fetch.fetch_profile_insolvency`). It is built and
unit-tested (`tests/test_prospective_fetch.py`): the tests assert that officers
and PSC endpoints are **never** called and that `/insolvency` is called only when
the profile carries `links.insolvency`. It writes into a horizon-specific cache
directory (so it cannot overwrite the baseline or other runs), resumes for free on
interruption, and reports per-endpoint request counts for budget accounting.

**Invalid-number caveat (found in the dry run).** 232 of the 115,000 sampled
numbers (~0.20 %) are registered-society / royal-charter / other non-standard
forms (`IP…C`, `R…`, `SP…`, `SL…`) that the pipeline's strict validator rejects
because they are not 8-digit or 2-letter+6-digit. They are legitimate, fetchable
register entries, so `ukcompany prospective-fetch` **explicitly allows exactly
these registered-society / royal-charter prefixes** (`is_registered_society_number`)
and fetches them — rather than a blanket `--allow-invalid` that would also swallow
genuinely malformed numbers. Any *other* invalid number still hard-fails the run,
so no non-random slice is dropped silently. (Widening the main pipeline's strict
validator to accept these prefixes is a separate, out-of-scope change; the
allowance is scoped to this command.)

### 3.2 Counting an adverse outcome

From the horizon `/insolvency` resource, read each case's **type** and **dates**.
A company is an **adverse-insolvency positive** for a horizon when it has at least
one case whose type is *not* a solvent winding-up and whose relevant date falls
in the window **(T0, T0 + h]**. Counting by case date (not merely by current
status) excludes cases that were already open at baseline, so strata A and B
(prevalent at baseline) are scored as prevalent, not as incident positives, and
serve instead to validate the case-type classifier (§4.3).

### 3.3 Is the 6-month fetch worth it?

Measured on the maintainer's own Aug-2026 → Oct-2026 register snapshots, the
`active → liquidation/administration/VA` transition runs at **0.0809 % per two
months ≈ 0.485 %/year** — closely matching the national liquidation rate (§5).
Insolvency events accrue roughly linearly but are **under-recorded early**
(petition-to-order and filing lag), so a 6-month fetch yields only ~40–50 % of
the 12-month incident positives and understates the slow processes. By contrast
strike-off proposals resolve fast (29 % of strike-off-proposal companies had left
the register within two months), so the 6-month horizon captures most of the
strike-off outcome.

**Recommendation:** make **12 months the primary and required** fetch. The
6-month fetch on the full sample is not worth its cost for incident insolvency;
if run at all, restrict it to the fast-moving cells **C (strike-off) + D1
(accounts overdue)** (~58k companies, about half the budget) — strike-off
resolution and the highest-rate incident cell are where a 6-month look adds the
most — and skip the slow base cells. The analysis below is specified on the
12-month fetch.

### 3.4 Dissolution without insolvency, and unfetchable companies

- A company that leaves the register by **voluntary strike-off / dissolution with
  no insolvency case** is a **separate outcome**, not an adverse-insolvency
  positive and **not censored**: it is still observable (profile status
  `dissolved` with a dissolution date). Strike-off is frequently non-distress
  (dormant/retired companies), so conflating it with insolvency would inflate the
  positive rate. It is recorded as its own outcome class and analysed separately.
- **Censoring** applies only when a company genuinely cannot be observed. Within a
  12-month horizon this should be near-zero: dissolved companies stay retrievable
  for ~20 years (§4.4). A **transient** fetch failure is retried (the cache
  resumes); a company that is **persistently unresolvable** (e.g. 404 with no
  dissolution record) is marked censored and its count reported — censored
  companies are excluded from the numerator and denominator, not scored as
  negatives.

## 4. Citations and verifications (accessed 2026-10-12)

### 4.3 Liquidation is no longer ambiguous — case types verified

The Companies House `insolvency_case_type` enumeration
(`companieshouse/api-enumerations`, `constants.yml`,
<https://raw.githubusercontent.com/companieshouse/api-enumerations/master/constants.yml>,
accessed 2026-10-12) distinguishes the liquidation routes explicitly:

| Key | Description | Treatment |
|---|---|---|
| `members-voluntary-liquidation` | Members voluntary liquidation | **solvent** — not adverse |
| `creditors-voluntary-liquidation` | Creditors voluntary liquidation | adverse |
| `compulsory-liquidation` | Compulsory liquidation | adverse |
| `in-administration` | In administration | adverse |
| `administrative-receiver` | Administrative receiver appointed | adverse |
| `receiver-manager` | Receiver/Manager appointed | adverse |
| `corporate-voluntary-arrangement` | Corporate voluntary arrangement (CVA) | adverse |

Because the `/insolvency` case type separates members' voluntary liquidation
(solvent) from creditors' voluntary and compulsory liquidation, **liquidation at
the outcome fetch is unambiguous** — unlike the register's bare `liquidation`
status. This matches the code constant `SOLVENT_CASE_TYPES =
{"members-voluntary-liquidation"}` in `derive.py`.

### 4.4 How long dissolved companies stay retrievable

Company formation and dissolution records remain on the public register — and
therefore retrievable through the API, which serves the register — for **20 years
after strike-off**, after which a selection is transferred to The National
Archives and the remainder destroyed. As of a review **announced May 2026**,
Companies House has **paused** destruction and transfer pending reconsideration of
the retention period, so records are currently being held at least that long.
Sources (accessed 2026-10-12):
<https://www.gov.uk/government/news/companies-house-is-reviewing-the-retention-period-for-dissolved-company-records>;
<https://www.1stformations.co.uk/blog/dissolved-companies-register/>;
<https://www.lexisnexis.co.uk/legal/guidance/what-does-companies-house-do-with-the-records-of-dissolved-companies>.
A 12-month horizon is far inside this window, so dissolution does not threaten
retrievability.

## 5. Expected number of positive cases per horizon

Two independent estimates of the annual adverse-insolvency incidence among
active-at-baseline companies agree:

- **Insolvency Service National Statistics, 2024 (England & Wales):** 23,872
  company insolvencies (18,840 CVL, 3,230 compulsory liquidation, 1,597
  administrations, 202 CVAs, 3 receiverships); liquidation rate **52.4 per 10,000
  on the effective register = 1 in 191 ≈ 0.524 %/year**
  (<https://www.gov.uk/government/statistics/company-insolvencies-december-2024/commentary-company-insolvency-statistics-december-2024>,
  accessed 2026-10-12).
- **The maintainer's own data** (Aug-2026 → Oct-2026 governed register snapshots):
  `active → liquidation/administration/VA` at **0.485 %/year** annualised.

Applying the **per-cell measured rates** (the `annual_adverse_rate` recorded in
the sidecar) to each cell's sampled count gives the expected **raw** incident
adverse-insolvency positives at 12 months (A and B are prevalent at baseline and
excluded from the incident numerator):

| Cell | Sampled | Rate/yr | 12-month incident positives | 6-month (≈45 %) |
|---|---:|---:|---:|---:|
| D1 accounts overdue | 38,000 | 5.40 % | **≈ 2,053** | ≈ 920 |
| C strike-off proposal | 20,000 | 1.13 % | ≈ 226 | ≈ 100 |
| D4 base | 33,000 | 0.35 % | ≈ 114 | ≈ 50 |
| D2 CS overdue | 10,000 | 0.83 % | ≈ 83 | ≈ 37 |
| D3 charges | 10,000 | 0.75 % | ≈ 75 | ≈ 34 |
| **Total adverse-insolvency positives** | 111,000 | | **≈ 2,550** | **≈ 1,150** |
| Dissolution-without-insolvency outcome (mostly from C) | | | tens of thousands | ~20k+ |

The risk-stratified allocation lifts the expected 12-month incident count to
**≈ 2,550** — roughly **9× the ~300** a status-only / uniform sample of the same
size would yield — because 38,000 of the budget sits in the 5.4 %/yr
accounts-overdue cell, which alone contributes ~2,050 positives. Weighting (§6)
restores the true population prevalence for the headline metric, so the enrichment
buys power without biasing the estimate. The base cell D4 (33,000) keeps the
dominant clean-active population segment estimable. The separate
dissolution-without-insolvency outcome remains abundant. Caveat: the per-cell rates
are measured over one two-month window and annualised linearly; the 12-month figure
assumes that rate holds and does not model seasonality or the petition-to-order lag,
so treat ≈ 2,550 as a design estimate, not a forecast.

**Limitation — the signal is concentrated in overdue-accounts companies.** About
**80 %** of the expected positives (≈ 2,053 of ≈ 2,550) come from the single D1
accounts-overdue cell. The on-time-filer cells contribute only ≈ **270** combined
(D2–D4), and the companies with *no* overdue marker at all (D3 + D4) only ≈ **190**.
Two consequences follow, and both are pre-registered as caveats rather than fixed
by changing the design:

- **Subgroup results for on-time filers are underpowered and strictly
  exploratory.** Any AP / recall figure computed on the D3+D4 (clean, on-time)
  subset rests on ~190 positives and will have wide confidence intervals; it must
  be reported as exploratory, not as a headline result.
- This is also where it bites hardest analytically: the headline metric is the
  **leakage-free** (without-compliance) model (§6), yet most positives sit in the
  very cell selected *on* a compliance field. So the population-weighted leakage-free
  AP is driven by a subgroup in which the leakage-free features are, by
  construction, weakest. The weighting keeps the estimate unbiased, but its
  precision for on-time filers is limited — the study can say whether a leakage-free
  signal exists in the overdue population far more confidently than in the on-time
  population. If stronger on-time power is wanted, the lever is to move budget from
  D1 into D3/D4 at the next (pre-outcome) re-freeze.

## 6. Pre-registered analysis

**Unit:** one company. **Weights:** the frozen `sampling_weight`, so every
estimate is at the true population base rate.

**Primary outcome:** adverse insolvency within 12 months (§3.2), among companies
not already in an insolvency process at baseline (strata C and D). **Secondary
outcomes:** the same at 6 months (if fetched); dissolution-without-insolvency at
12 months as a distinct label.

**Models (both weighted):**
1. **L2-penalised logistic regression** — the interpretable primary model.
2. **Gradient-boosted trees** (histogram-based) — the flexible comparator.

Hyperparameters are fixed by weighted cross-validation **within the baseline
only** (no outcome data), and recorded before the outcome fetch.

**Metrics** (bootstrap CIs resampling companies, weighted):
- **Average Precision at the true prevalence**, using the sampling weights — the
  headline metric, because the oversampled in-sample base rate is not the
  population rate.
- ROC-AUC; calibration (reliability curve + weighted Brier score); recall at
  fixed alert budgets (top 0.5 %, 1 %, 2 % by population weight).

**Feature blocks:**
1. **Register core** — status, type, age, SIC sections, charges, dormancy flags.
2. **Register compliance** — accounts overdue, confirmation-statement overdue,
   accounts never filed, next-due gaps.
3. **PSC** — record/ceased counts, natures of control, identification state.
4. **Accounts financial** — equity, net current assets, cash, current ratio,
   negative-equity flag, deltas.

**Register compliance analysed with and without (block 2).** Accounts-overdue and
confirmation-statement-overdue are partly **consequences** of an adverse process
already under way (a company heading into insolvency stops filing), so including
them risks outcome leakage. The **primary model excludes block 2**; a secondary
model includes it, and the AP gap between them is reported as the
leakage-prone optimistic ceiling, not as predictive performance. Note the sample
is deliberately enriched on block-2 fields (cells D1/D2); because the inclusion
probability depends only on those observed baseline fields, the weighted
with/without-block-2 estimates remain unbiased for the population, but most
positives sit in the overdue cell, so the leakage-free (without-block-2) model is
being asked to recover them from other features — a deliberately demanding test.

## 7. The exact future work

The fetch path (`ukcompany prospective-fetch`) is built. Everything below is the
study's only remaining work; the two commands are exactly what the maintainer
runs, with the dates.

```bash
# --- +12 months: PRIMARY. Run on or after 2027-10-05. ---
# Profile + /insolvency only, into a horizon-specific cache so it cannot
# overwrite the baseline or other runs. The 232 registered-society / royal-charter
# numbers are allowed automatically; any other invalid number hard-fails (§3.1).
ukcompany prospective-fetch \
  --input data/prospective/study-sample.csv \
  --cache-dir data/prospective/raw-2027-10

# --- +6 months: OPTIONAL, cells C + D1 only. Run on or after 2027-04-05. ---
#   Pre-filter the sample to cells C_strike_off_proposal and D1_accounts_overdue
#   (the `cell` column), write study-sample-CD1.csv, then:
ukcompany prospective-fetch \
  --input data/prospective/study-sample-CD1.csv \
  --cache-dir data/prospective/raw-2027-04

# --- Analysis (after the 12-month fetch) ---
#   Extract per-company outcomes (adverse-insolvency / dissolution / censored)
#   from the horizon cache by case type and date (§3.2), join to the frozen
#   baseline features and weights, and fit the §6 models. This outcome-extraction
#   + scoring step is the analysis deliverable; it reports aggregates only
#   (no company numbers), consistent with the repo's publication policy.
```

**Expected API time per horizon.** The fetch is one profile per company
(114,768 valid) plus one `/insolvency` call only where the profile links to it.
The insolvency-link share across the sample is dominated by cells A and B
(~4,000, nearly all linked) plus a low single-digit percent of C/D, so
≈ **6,000–8,000** insolvency calls → ≈ **121,000–123,000 requests** total.

A 100-company dry run (2026-10-12) fetched 100 profiles + 27 insolvency = **127
requests in 2.9 s (43 req/s)** — but that is the *unthrottled* burst while the
token bucket is full, and the 27 % insolvency rate is inflated (the lowest
company numbers are old and insolvency-heavy). The binding constraint is the
client's conservative rate limit of **500 requests / 300 s (1.67 req/s
sustained)**, so a full horizon ≈ 122,000 / 6,000 per hour ≈ **~20 hours**. The
optional C+D1 6-month fetch (~58k companies) is roughly half that. These are long
unattended runs; the cache resumes on interruption.
