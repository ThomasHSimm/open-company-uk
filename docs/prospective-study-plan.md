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

### 1.1 The frozen study sample (done)

Fetching the whole register at two horizons is infeasible, so a sample is frozen.
It was produced by `scripts/freeze_prospective_sample.py` (deterministic: fixed
seed `20260912`, reproducible from the join hash above):

| Artefact | Path | sha256 |
|---|---|---|
| Sample (company numbers + weights) | `data/prospective/study-sample.csv` | `68e92c3a9642fc9833d7bdd2fc28e28fc7891e9867ebe29f976e98b8a75880c8` |
| Sample sidecar (strata, seed, weights) | `data/prospective/study-sample.strata.json` | `fe531f1fb2db3f1d5956e2faa80c2a6a1a645eb73b133aeba27f8530fbaf72af` |

Both files are **private and gitignored** (`data/`); only the hashes are
committed. The sample is **100,318** companies in four baseline-status strata:

| Stratum | Baseline register status | Population | Sampled | Weight (pop/sampled) |
|---|---|---:|---:|---:|
| A live insolvency process | administration / receivership / voluntary arrangement (all spellings) | 7,318 | 7,318 (all) | 1.00 |
| B liquidation | liquidation (solvency unknown until fetched) | 108,330 | 15,000 | 7.22 |
| C strike-off proposal | active – proposal to strike off | 423,006 | 30,000 | 14.10 |
| D active | active | 5,166,057 | 48,000 | 107.63 |

The take-all A stratum keeps the rare live-process companies from being lost to
sampling noise; B is the ground-truth set for the members'-vs-creditors'
classifier (§4.3); C is the fast-moving strike-off population; D is the bulk
at-risk population. Each company's `sampling_weight` lets a weighted analysis
reproduce the true population prevalence (§6).

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

No officers or PSC endpoints. **Note:** `ukcompany run` (via
`fetch_companies`) also fetches officers, PSC and PSC-statements, which would
multiply the request budget four- to five-fold. The horizon runs must therefore
use a **profile-and-insolvency-only** fetch. That path does not exist yet; adding
it (a `--only profile,insolvency` option on `run`, or a small
`ukcompany prospective-fetch`) is a one-off, pre-registered addition to make
**before** the first horizon run. It changes only the fetch surface, never the
baseline.

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
if run at all, restrict it to strata **A + C** (the fast-moving ~37k companies,
roughly half the budget) to observe strike-off resolution timing. The analysis
below is specified on the 12-month fetch.

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

Using ≈ **0.5 %/year** incident adverse insolvency, the expected **raw** positive
counts in the sample (positives arise almost entirely from strata C and D; A and B
are prevalent at baseline and excluded from the incident numerator):

| Source | Sampled | 12-month incident positives | 6-month |
|---|---:|---:|---:|
| D active (0.485 %/yr) | 48,000 | ≈ 230 | ≈ 100–115 |
| C strike-off proposal (elevated insolvency conversion on top of mostly non-insolvency dissolution) | 30,000 | ≈ 50–150 | ≈ 30–80 |
| **Total adverse-insolvency positives** | | **≈ 280–380** | **≈ 130–195** |
| Dissolution-without-insolvency outcome (mostly from C) | | tens of thousands | ~20k+ |

So the **binding constraint on power is the adverse-insolvency positive count
(~300 at 12 months)**; the separate dissolution outcome is abundant. If stronger
incident-insolvency power is wanted, the cheapest lever is to move budget into
stratum D (each +10,000 active companies ≈ +48 positives/year) before the freeze
is final; the current split deliberately also buys classifier-validation coverage
of the prevalent strata A/B and full coverage of the dissolution outcome.

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
leakage-prone optimistic ceiling, not as predictive performance.

## 7. The exact future work

Everything below is the study's only remaining work. Build the profile-and-
insolvency-only fetch (§3.1) first.

```bash
# --- +12 months: PRIMARY. Run on or after 2027-10-05. ---
# Profile + /insolvency only, into a horizon-specific cache so it cannot
# overwrite the baseline or other runs:
ukcompany prospective-fetch \
  --input data/prospective/study-sample.csv \
  --cache-dir data/prospective/raw-2027-10
# (equivalently, once implemented: ukcompany run --only profile,insolvency
#  --input data/prospective/study-sample.csv --settings config/prospective-2027-10.yaml)

# --- +6 months: OPTIONAL, strata A+C only. Run on or after 2027-04-05. ---
#   Pre-filter the sample to strata A and C, then:
ukcompany prospective-fetch \
  --input data/prospective/study-sample-AC.csv \
  --cache-dir data/prospective/raw-2027-04

# --- Analysis (after the 12-month fetch) ---
#   Extract per-company outcomes (adverse-insolvency / dissolution / censored)
#   from the horizon cache by case type and date (§3.2), join to the frozen
#   baseline features and weights, and fit the §6 models. This outcome-extraction
#   + scoring step is the analysis deliverable; it reports aggregates only
#   (no company numbers), consistent with the repo's publication policy.
```

**Expected API time per horizon** (profile for all 100,318 + `/insolvency` for
the ~24,000 companies with an insolvency link ≈ **124,000 requests**): at the
project-conservative 500 requests / 300 s ≈ **~21 hours**; at the published 600 /
300 s ≈ **~17 hours**. The 12-month fetch alone is the primary cost; the optional
A+C 6-month fetch is roughly half of one horizon. These are long unattended runs —
the cache resumes on interruption.
