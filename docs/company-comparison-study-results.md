# Company-attribute comparison study results

**Status:** completed internal contemporaneous study. These results classify a registrar-recorded
status in the selected 2026-09/10 source state. They do **not** predict future insolvency, establish
causality, define a production rule, rank companies or create a risk score. Attributes may be
consequences of an adverse process already under way.

The reviewed design is in the [study plan](company-comparison-study-plan.md). The complete committed
aggregate, with positive cells below 10 suppressed, is
[`company-comparison-study-results.json`](company-comparison-study-results.json).

## Inputs and outcome

The governed Handoff 10 join contains one row for each of 5,704,711 companies in the 2026-10-01
register, with PSC from 2026-09-25 and accounts at `T=202609`. PSC is six days earlier than the
register and is accepted as contemporaneous for this study. Accounts registration month is not the
monthly ZIP publication or download date. The join was assembled on 2026-10-10.

| item | checked value |
|---|---|
| joined Parquet | `data/join/v1-internal-202609/governed/joined_company_features.parquet` |
| join SHA-256 | `909414cb617ce3862954cb55dff1bde54983a7898cb7ec0c02f15026e098e031` |
| join manifest SHA-256 | `d93c82f3aa57d95e5d168728bcda619a5400ffb9f2c3b0a8656296d7f5174ef1` |
| frozen corrected spec SHA-256 | `6fd23b82cb221cab64caa80a094593f667713d90332cae2384cb6c449f20d70c` |
| promoted private aggregate SHA-256 | `bcd1ab2d6bd1cf37abc6d9e064cad62411dc68d2ab2b2fc9a8ff309c6fbfacb9` |
| analysis code commit | `a3b67db3baea102ff1806f69db2a05f977c71e09` |

The narrow positive group is the 7,318 companies whose status explicitly records administration,
receivership or a voluntary arrangement. The comparison group is 5,589,063 `Active` or
`Active - Proposal to Strike off` companies **without recorded adverse insolvency**. It is not a
verified solvent or healthy group. All 108,330 `Liquidation` rows are excluded because this input
cannot separate adverse liquidation from a solvent members' voluntary liquidation. The supervised
population is therefore 5,596,381 companies, with an exact recorded-adverse prevalence of
7,318 / 5,596,381 = 0.130763%.

Previously dissolved companies are absent from the selected register and outside this target
population. The historical case-only cohort is not reused as a comparison against current
survivors.

## Coverage and sampling

Source-row flags describe source presence, independently of null attributes within a present row.

| group | companies | has PSC | has accounts | has both |
|---|---:|---:|---:|---:|
| recorded adverse | 7,318 | 5,810 (79.39%) | 4,961 (67.79%) | 4,881 (66.70%) |
| without recorded adverse | 5,589,063 | 5,452,171 (97.55%) | 3,938,739 (70.47%) | 3,937,786 (70.46%) |

The PSC coverage difference is itself substantial and is why the missingness-only baselines are
reported. Accounts values remain feature-specific: for example, negative equity is observed for
4,039 adverse and 3,397,176 comparison companies, while short-term creditors are observed for only
1,468 and 1,580,094 respectively. Missing values are unavailable, never treated as a non-firing
attribute.

The fixed company-number split placed 5,862 adverse and 4,469,557 comparison companies in training,
and 1,456 adverse and 1,119,506 comparison companies in held-out testing. All adverse companies
were retained. Comparison companies were sampled uniformly within each partition at approximately
20:1 and inverse-probability weighted to the exact eligible totals.

| analysis population | eligible adverse | eligible comparison | sampled comparison |
|---|---:|---:|---:|
| primary | 7,318 | 5,589,063 | 146,360 |
| complete PSC and accounts | 4,881 | 3,937,786 | 97,620 |
| Active-only comparison sensitivity | 7,318 | 5,166,057 | 146,360 |
| private-limited sensitivity | 7,075 | 5,163,442 | 141,500 |

Every eligible comparison company had positive inclusion probability. Primary comparison
probabilities were 0.026231 in training and 0.026011 in testing, corresponding to weights 38.123
and 38.445. The validated weighted totals reconcile to every eligible population exactly within
floating-point tolerance.

## Attribute findings

### Binary attributes

The largest unadjusted differences are register compliance states. These are associations with an
already-recorded adverse status and may be consequences of that process.

| attribute | adverse signal / observed | comparison signal / observed | difference | odds ratio (95% CI) |
|---|---:|---:|---:|---:|
| accounts overdue | 5,963 / 7,318 (81.48%) | 338,459 / 5,589,063 (6.06%) | +75.43 pp | 68.25 (64.33–72.40) |
| confirmation statement overdue | 5,587 / 7,318 (76.35%) | 609,009 / 5,589,063 (10.90%) | +65.45 pp | 26.39 (25.00–27.85) |
| negative equity | 1,372 / 4,039 (33.97%) | 598,762 / 3,397,176 (17.63%) | +16.34 pp | 2.40 (2.25–2.57) |
| net current liabilities | 2,114 / 4,595 (46.01%) | 993,060 / 3,296,619 (30.12%) | +15.88 pp | 1.98 (1.87–2.09) |
| PSC appointment rights | 2,954 / 5,810 (50.84%) | 3,372,780 / 5,452,171 (61.86%) | −11.02 pp | 0.64 (0.61–0.67) |
| accounts never filed | 368 / 7,318 (5.03%) | 49,473 / 5,589,063 (0.89%) | +4.14 pp | 5.94 (5.34–6.59) |

All six displayed comparisons remain below a 5% Benjamini-Hochberg false-discovery-rate threshold.
Given the population size, statistical significance is not a measure of practical importance;
effect sizes, uncertainty and observed denominators are primary.

### Counts and financial attributes

Rank-biserial effects below use the weighted sampled comparison distribution; medians and observed
counts come from the full aggregate.

| attribute | adverse observed; median | comparison observed; median | rank-biserial effect |
|---|---:|---:|---:|
| registered charges | 7,318; 3 | 5,589,063; 0 | +0.781 |
| months since latest available accounts period end | 4,961; 30 | 3,938,739; 14 | +0.733 |
| outstanding charges | 7,318; 2 | 5,589,063; 0 | +0.720 |
| creditors within one year | 1,468; £445,453 | 1,580,094; £13,119 | +0.691 |
| current assets | 4,411; £714,483 | 3,065,269; £24,121 | +0.604 |
| companies sharing postcode | 7,318; 199 | 5,589,063; 15 | +0.348 |
| corporate PSC count | 5,810; 0 | 5,452,171; 0 | +0.284 |
| ceased PSC count | 5,810; 0 | 5,452,171; 0 | +0.267 |

Financial size is intentionally not adjusted away before these descriptions because it is an
attribute under study. The structural models adjust for broad company type, age band and SIC
section. The private-limited and complete-source results below provide predeclared sensitivity
checks rather than selecting the most favourable cohort.

Register accounts category had the largest categorical association (Cramer's V 0.146). `TOTAL
EXEMPTION FULL` represented 39.00% of the adverse group versus 23.29% of the comparison group;
`MICRO ENTITY` represented 12.68% versus 32.88%. Accounts employee band, accounts filing category
and PSC information state had smaller associations (V 0.047, 0.046 and 0.043). Categorical cells
below 10 are pooled or suppressed in the committed JSON.

## Held-out classification

All metrics are inverse-probability weighted to the eligible held-out population. “AP” is weighted
average precision at the exact source prevalence, not an unweighted case-control precision. Every
transformation and imputation step was fit within training/CV folds. Logistic regularisation was
selected only by training-fold weighted log loss.

| primary model | ROC AUC | weighted AP | log loss | Brier score |
|---|---:|---:|---:|---:|
| missingness only | 0.7395 | 0.0087 | 0.009268 | 0.001294 |
| structural | 0.7924 | 0.0069 | 0.009107 | 0.001294 |
| structural + missingness | 0.8622 | 0.0881 | 0.007990 | 0.001232 |
| register | 0.9708 | 0.3226 | 0.005118 | 0.001057 |
| accounts | 0.9266 | 0.0467 | 0.007421 | 0.001282 |
| PSC | 0.8824 | 0.0804 | 0.007850 | 0.001238 |
| combined | 0.9719 | 0.4387 | 0.004555 | 0.000936 |

Against structural + missingness on the identical held-out companies, the combined model improved
ROC AUC by 0.1091 (paired bootstrap 95% CI 0.1011–0.1180), weighted AP by 0.3516
(0.2843–0.4225), log loss by 0.003435 (0.003201–0.003655) and Brier score by 0.000297
(0.000243–0.000342). Register attributes account for most ROC separation: the combined and
register point estimates differ by only 0.0011 ROC AUC, although the predeclared paired uncertainty
comparison was combined versus structural + missingness, not combined versus register.

### Sensitivities

| population | structural + missingness AUC / AP | combined AUC / AP | paired AUC increment (95% CI) |
|---|---:|---:|---:|
| primary | 0.8622 / 0.0881 | 0.9719 / 0.4387 | 0.1091 (0.1011–0.1180) |
| complete PSC and accounts | 0.7887 / 0.0056 | 0.9639 / 0.4329 | 0.1750 (0.1637–0.1871) |
| Active-only comparison | 0.8610 / 0.0915 | 0.9822 / 0.5195 | 0.1209 (0.1133–0.1276) |
| private limited | 0.8573 / 0.0724 | 0.9722 / 0.3049 | 0.1154 (0.1067–0.1243) |

The planned sensitivities all retain separation; they do not repair label incompleteness or make
the task prospective. Complete-source analysis is conditioned on source availability. The
Active-only analysis removes proposal-to-strike-off companies from the comparison group, and the
private-limited analysis reflects the positive group's concentration in that company type.

## Numerical correction and validation

The first full run at commit `303dd60` used `saga`, took 10,407.5 seconds (2h53m) and peaked at
6,274,330,624 bytes (5.84 GiB). All 28 final fits emitted convergence warnings; its CV warnings had
been suppressed, so CV convergence could not be certified. That output is retained locally as
`company-comparison-aggregate.diagnostic-nonconverged.json`, explicitly marked diagnostic and not
used for any finding above.

Commit `a3b67db` changed only numerical execution: the solver became `newton-cholesky` at tolerance
`1e-6`, any CV or final convergence warning became fatal, bootstrap calibration work unrelated to
the paired metrics was removed, and progress logging was added. Cohort definitions, features,
regularisation grid, sampling seeds, held-out split and metrics did not change. This is a numerical
correction, not performance tuning.

The detached corrected job was `corrected-newton-cholesky-20261011`, PID 247524, from
2026-10-11 12:42:47 to 12:48:30 BST. It took 342.2 seconds and peaked at 6,232,199,168 bytes
(5.80 GiB). Promotion checks established:

- all 252 CV fits passed the fail-fast convergence gate and all 28 final fits recorded zero
  convergence warnings;
- input hashes/dates were reverified, all four cohorts closed, all inclusion probabilities were
  positive, and weighted totals reconciled;
- the frozen cohort, features, sampling records and held-out split counts were identical to the
  diagnostic design;
- all held-out and paired metrics were complete, finite and within their valid ranges;
- focused synthetic tests cover labels and liquidation exclusion, weights, deterministic
  company-separated splits, training-only preprocessing, forbidden predictors, aggregate-only
  output, report validation and small-count suppression.
- the complete synthetic suite passed: 283 tests passed, one was deselected, and Ruff reported no
  issues.

## Limitations

- This classifies a status already recorded on 2026-10-01. Overdue filings, stale accounts and
  charge states can be consequences of administration or receivership rather than antecedent risk.
- The comparison group is “without recorded adverse insolvency”, not confirmed negative. Latent,
  delayed or unrecorded adverse processes may be present.
- Excluding ambiguous liquidation substantially narrows the outcome. Point-in-time insolvency case
  types are still required to separate solvent and adverse liquidation.
- The register base excludes previously dissolved companies. Results do not generalise to all
  historical companies or insolvencies.
- Accounts and PSC missingness differs by outcome and company structure. Weighting repairs the
  comparison sample, not source non-observation or selection into the register.
- PSC predates the register by six days. Accounts are aligned by registration month, not exact ZIP
  publication time or exact public availability timestamp.
- No threshold, company score, ranking, production rule or prospective claim is produced. A future
  insolvency evaluation still requires dated baseline enrolment and later outcome follow-up.

## Exploratory source-addition follow-up

After inspecting this study's held-out results, a separately labelled exploratory analysis compared
register + accounts, register + PSC and all three against register-only and source-availability
controls. Accounts supplied the clearest incremental classification information; PSC content added
little beyond register and availability. Because the test partition was already inspected, this is
not confirmatory source-selection evidence. See
[`company-comparison-source-additions-results.md`](company-comparison-source-additions-results.md).
