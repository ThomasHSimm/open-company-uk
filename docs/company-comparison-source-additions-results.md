# Exploratory company-comparison source additions

**Status:** completed internal exploratory analysis. The original held-out results were inspected
before this follow-up was specified, so these comparisons and paired intervals are not a new
confirmatory test. They describe classification of adverse status already recorded in the selected
register snapshot; they do not measure future insolvency prediction.

## Question and fixed design

This follow-up asks whether accounts or PSC attributes add contemporaneous classification
information beyond the structural + register model, and whether any apparent gain is explained by
source availability alone. It uses the unchanged narrow outcome definition, exclusions, company-
number split, comparison sample sizes, inclusion probabilities, inverse-probability weights,
feature transformations, regularisation grid and training-only cross-validation from the completed
[company-comparison study](company-comparison-study-results.md).

Seven L2-logistic models were fitted to identical companies within each population:

1. register;
2. register + accounts availability indicators;
3. register + accounts attributes and missingness;
4. register + PSC availability indicators;
5. register + PSC attributes and missingness;
6. register + all-source availability indicators; and
7. all three sources.

The primary population contains 7,318 recorded-adverse and 5,589,063 comparison companies before
sampling. The secondary complete-source population is conditioned on both PSC and accounts being
present and contains 4,881 recorded-adverse and 3,937,786 comparison companies. The selected
register is dated 2026-10-01, PSC is dated 2026-09-25, and accounts use registration month
`T=202609`; registration month is not the date when the consolidated monthly ZIP became available.

## Sampling resolution

The original run retained aggregate sample counts and weights but not sampled company identities.
Its seeded DuckDB reservoir was not identity-reproducible across processes when insertion order was
not preserved. The first follow-up attempt therefore stopped before writing results when the
register model did not reproduce.

Before any follow-up result was seen, the analysis froze a deterministic company-number hash order
within each unchanged train/test split. The fixed-size comparison samples, positive inclusion
probabilities and weights remain those in the original design. Aggregate hashes of the newly frozen
sample identities are recorded in the committed JSON. Because the sampled identities differ, the
absolute metrics below must not be presented as same-sample changes from the original study.

## Held-out metrics

Metrics are weighted to the exact eligible population counts. Lower log loss and Brier score are
better; higher ROC AUC and average precision are better. All models selected `C=0.1` using
training-only cross-validation.

### Primary population

| model | ROC AUC | average precision | log loss | Brier score |
|---|---:|---:|---:|---:|
| register | 0.96890 | 0.26018 | 0.005268 | 0.001100 |
| register + accounts availability | 0.96861 | 0.26492 | 0.005252 | 0.001096 |
| register + accounts | 0.97165 | 0.37153 | 0.004762 | 0.000993 |
| register + PSC availability | 0.97067 | 0.27394 | 0.005176 | 0.001092 |
| register + PSC | 0.96999 | 0.29052 | 0.005082 | 0.001063 |
| register + all-source availability | 0.97053 | 0.27859 | 0.005151 | 0.001087 |
| all three | 0.97306 | 0.39185 | 0.004642 | 0.000970 |

### Complete-source population

| model | ROC AUC | average precision | log loss | Brier score |
|---|---:|---:|---:|---:|
| register | 0.96134 | 0.30403 | 0.005283 | 0.001019 |
| register + accounts availability | 0.96094 | 0.31577 | 0.005257 | 0.001011 |
| register + accounts | 0.96485 | 0.34797 | 0.004922 | 0.000974 |
| register + PSC availability | 0.96125 | 0.31662 | 0.005269 | 0.001013 |
| register + PSC | 0.96128 | 0.31448 | 0.005235 | 0.001009 |
| register + all-source availability | 0.96083 | 0.31712 | 0.005251 | 0.001009 |
| all three | 0.96538 | 0.33862 | 0.004916 | 0.000970 |

## Paired increments

The tables report candidate minus reference for ROC AUC and average precision. For log loss and
Brier score, positive values mean the candidate reduced error. Intervals are paired bootstrap 95%
intervals on identical held-out companies.

### Primary population

| comparison | ROC AUC increment (95% CI) | AP increment (95% CI) | log-loss reduction (95% CI) | Brier reduction (95% CI) |
|---|---:|---:|---:|---:|
| register + accounts vs register | 0.00285 (0.00039, 0.00527) | 0.10785 (0.06849, 0.14421) | 0.000506 (0.000375, 0.000623) | 0.000106 (0.000068, 0.000139) |
| register + accounts vs accounts availability | 0.00297 (0.00038, 0.00538) | 0.10567 (0.06846, 0.15333) | 0.000492 (0.000372, 0.000606) | 0.000104 (0.000068, 0.000139) |
| register + PSC vs register | 0.00108 (-0.00051, 0.00249) | 0.03087 (-0.00346, 0.07855) | 0.000185 (0.000086, 0.000284) | 0.000035 (-0.000008, 0.000075) |
| register + PSC vs PSC availability | -0.00066 (-0.00191, 0.00054) | 0.01988 (-0.00728, 0.05121) | 0.000100 (0.000022, 0.000182) | 0.000030 (-0.000002, 0.000058) |
| all three vs register | 0.00419 (0.00163, 0.00657) | 0.12772 (0.07514, 0.17477) | 0.000625 (0.000475, 0.000757) | 0.000128 (0.000077, 0.000172) |
| all three vs all-source availability | 0.00266 (0.00017, 0.00462) | 0.10993 (0.06539, 0.16132) | 0.000510 (0.000372, 0.000635) | 0.000117 (0.000075, 0.000161) |
| all three vs register + accounts | 0.00139 (0.00063, 0.00228) | 0.02189 (-0.00818, 0.04915) | 0.000123 (0.000041, 0.000187) | 0.000024 (-0.000006, 0.000048) |
| all three vs register + PSC | 0.00303 (0.00064, 0.00549) | 0.09678 (0.06978, 0.12802) | 0.000440 (0.000335, 0.000537) | 0.000094 (0.000067, 0.000119) |

Accounts availability alone did not clearly improve on register: its ROC AUC, average-precision,
log-loss and Brier intervals all included zero. PSC availability increased ROC AUC and reduced log
loss, while its average-precision and Brier intervals included zero. All-source availability versus
register increased ROC AUC and reduced log loss, but its other two intervals included zero. Full
paired results are in the committed JSON.

### Complete-source population

| comparison | ROC AUC increment (95% CI) | AP increment (95% CI) | log-loss reduction (95% CI) | Brier reduction (95% CI) |
|---|---:|---:|---:|---:|
| register + accounts vs register | 0.00362 (-0.00037, 0.00693) | 0.04584 (-0.03190, 0.11437) | 0.000362 (0.000143, 0.000538) | 0.000045 (-0.000047, 0.000112) |
| register + accounts vs accounts availability | 0.00392 (0.00039, 0.00726) | 0.03410 (-0.03441, 0.10123) | 0.000332 (0.000133, 0.000512) | 0.000038 (-0.000040, 0.000100) |
| register + PSC vs register | -0.00004 (-0.00133, 0.00141) | 0.00816 (-0.02511, 0.03321) | 0.000045 (-0.000022, 0.000100) | 0.000009 (-0.000011, 0.000025) |
| register + PSC vs PSC availability | 0.00002 (-0.00101, 0.00121) | -0.00102 (-0.02716, 0.02623) | 0.000033 (-0.000026, 0.000085) | 0.000005 (-0.000015, 0.000023) |
| all three vs register | 0.00402 (0.00044, 0.00753) | 0.03819 (-0.05591, 0.12332) | 0.000358 (0.000103, 0.000562) | 0.000046 (-0.000043, 0.000120) |
| all three vs all-source availability | 0.00452 (0.00086, 0.00783) | 0.03076 (-0.04967, 0.10932) | 0.000337 (0.000099, 0.000530) | 0.000040 (-0.000055, 0.000109) |
| all three vs register + accounts | 0.00050 (-0.00051, 0.00146) | -0.00392 (-0.02885, 0.02275) | 0.000008 (-0.000087, 0.000073) | 0.000005 (-0.000017, 0.000023) |
| all three vs register + PSC | 0.00404 (0.00022, 0.00760) | 0.03056 (-0.03418, 0.10379) | 0.000314 (0.000090, 0.000503) | 0.000037 (-0.000043, 0.000100) |

## Findings

- **Accounts earns the clearest incremental place in this exploratory comparison.** In the primary
  population, register + accounts improved all four metrics over register and over accounts
  availability, with every paired interval above zero. In the complete-source population, its ROC
  AUC and log-loss gains over availability remained above zero; the wider average-precision and
  Brier intervals crossed zero.
- **PSC content adds little beyond register.** Its primary ROC AUC, average-precision and Brier
  increments over register crossed zero, although log loss improved. Relative to PSC availability,
  only the small primary log-loss reduction excluded zero. All four complete-source intervals
  crossed zero.
- **Most of the all-three gain is associated with accounts.** Adding accounts to register + PSC
  improved primary ROC AUC, average precision, log loss and Brier score. Adding PSC to register +
  accounts gave smaller primary ROC AUC and log-loss gains, while average-precision and Brier
  intervals crossed zero; no all-three increment over register + accounts was resolved in the
  complete-source population.
- **Availability is itself informative but does not explain the accounts result.** PSC/all-source
  availability produced some primary separation, consistent with differential source coverage.
  Accounts values still added substantially over an accounts-availability control.

These findings do not license automatic source removal or a production feature choice. The test
partition had already been inspected, the complete-source analysis is selection-conditioned, and
attributes can reflect consequences of an adverse process already under way.

## Validation and provenance

The corrected run completed in 316.3 seconds and peaked at 2,441,621,504 bytes (2.27 GiB RSS). All
126 cross-validation fits passed the fail-fast warning gate; all 14 final fits recorded zero
convergence warnings. Validation checked 22 paired contrasts, four deterministic sample-identity
hashes, input provenance, the parent aggregate, cohort/split closure, sampling records, positive
probabilities, weights and finite metrics.

Synthetic validation covered outcome exclusions, deterministic sampling, inclusion weights,
company-separated splits, training-only preprocessing, forbidden predictors, source-addition model
construction and aggregate-only output. The full suite passed 285 tests with one deselected; Ruff
reported no issues. The committed JSON reproduced exactly from the validated private aggregate.

The governed join SHA-256 is
`909414cb617ce3862954cb55dff1bde54983a7898cb7ec0c02f15026e098e031`. The frozen exploratory
configuration SHA-256 is
`496bd0a87810c1503bb1a45333db6446ad1e95bda57fcec8e76efd78b37aaaff`; the promoted private
aggregate SHA-256 is
`78bb2707308dfba4bd965b9b186b2708623558de8b8fae2f3faab5d9e70f3956`. The committed
[`company-comparison-source-additions-results.json`](company-comparison-source-additions-results.json)
contains aggregate model and paired-bootstrap results only. No company identifiers, assignments,
scores, rankings, thresholds or production rules are committed.
