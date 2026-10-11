# Company-attribute comparison study plan

**Status:** implemented as approved; see the
[aggregate results](company-comparison-study-results.md). This is a contemporaneous descriptive
and classification study of registrar-recorded state. It is not a forecast, a causal study, a new
rule, a company ranking or a production risk score.

## 1. Evidence inspected

The design starts from the internal governed Handoff 10 join. Its base is one row per normalised
company number in the 2026-10-01 register snapshot, left-joined to PSC 2026-09-25 and accounts at
`T=202609`. The join was assembled on 2026-10-10; its source dates are not identical, and accounts
registration month is not the date on which the consolidated monthly ZIP became downloadable.
These timing limits make the data suitable for a contemporaneous association study, not a claim
that every attribute was available for a prediction at 2026-09-30.

Checked inputs and definitions:

- The governed join has 5,704,711 unique register rows and 63 columns. Its SHA-256 is
  `909414cb617ce3862954cb55dff1bde54983a7898cb7ec0c02f15026e098e031`; source paths, dates and
  hashes are recorded in the local
  `data/join/v1-internal-202609/governed/join_manifest.json` and the committed
  [Handoff 10 Stage 2 report](join-internal-202609-stage2.md).
- The inspected schema contains `reg_company_status` but no insolvency case type, insolvency link,
  `has_been_liquidated` or other case-level insolvency evidence. Register, PSC and accounts feature
  construction is defined in
  [`snapshot/features.py`](../src/ukcompany/snapshot/features.py),
  [`psc/features.py`](../src/ukcompany/psc/features.py) and
  [`accounts/features.py`](../src/ukcompany/accounts/features.py).
- Project rules treat administration, receivership, voluntary arrangement, insolvency proceedings
  and liquidation as insolvency statuses, but remove a liquidation from the adverse class when all
  known cases are members' voluntary liquidations. That distinction requires case types
  ([`rules.py`](../src/ukcompany/rules.py), [generated rule definitions](rules.md)).
- The completed historical study establishes which accounts attributes can be reconstructed before
  recorded insolvency among historical cases, but it has no contemporaneous comparison group. Its
  companies are not joined to this current register population
  ([case-only results](validation-case-lead-time-results.md)). No historical case is compared with a
  current survivor in this design.

“Checked” below means observed in these files, their manifests, their schemas or the bounded
aggregate described next. “Proposed” means an analysis decision that has not been executed.

## 2. Available outcome groups

### 2.1 Bounded aggregate

A lazy aggregate read only status, company type, register accounts category, age and the two source
coverage flags from the 199 MB governed Parquet. It emitted counts only to `/tmp`; no company
number or row-level output was retained. All 5,704,711 rows fell into one of 13 non-null status
labels, so there was no missing or unclassified status in this snapshot.

The primary status mapping is deliberately narrow:

- **Recorded adverse insolvency:** an explicit administration, receiver/receivership or voluntary
  arrangement status. The 11 observed display labels and counts are: `In Administration` (3,709),
  `Live but Receiver Manager on at least one charge` (2,156), `Voluntary Arrangement` (583),
  `In Administration/Administrative Receiver` (398), `RECEIVERSHIP` (182),
  `ADMINISTRATION ORDER` (121), `ADMINISTRATIVE RECEIVER` (104),
  `In Administration/Receiver Manager` (52),
  `RECEIVER MANAGER / ADMINISTRATIVE RECEIVER` (10),
  `VOLUNTARY ARRANGEMENT / RECEIVER MANAGER` (2), and
  `VOLUNTARY ARRANGEMENT / ADMINISTRATIVE RECEIVER` (1).
- **Ambiguous liquidation:** `Liquidation` (108,330). This display status does not distinguish
  adverse compulsory/creditors' liquidation from solvent members' voluntary liquidation, so it is
  excluded from both primary groups.
- **Without recorded adverse insolvency:** `Active` (5,166,057) and
  `Active - Proposal to Strike off` (423,006). This means only that the selected status field does
  not record one of the narrow adverse processes. It does not mean healthy, solvent, compliant or a
  verified negative.

| primary disposition | companies | has PSC | has accounts | has both |
|---|---:|---:|---:|---:|
| without recorded adverse insolvency | 5,589,063 | 5,452,171 (97.55%) | 3,938,739 (70.47%) | 3,937,786 (70.46%) |
| recorded adverse insolvency | 7,318 | 5,810 (79.39%) | 4,961 (67.79%) | 4,881 (66.70%) |
| ambiguous liquidation — excluded | 108,330 | 81,147 (74.91%) | 73,236 (67.60%) | 72,225 (66.67%) |
| **selected register total** | **5,704,711** | **5,539,128** | **4,016,936** | **4,014,892** |

The corresponding mutually exclusive coverage counts are:

| disposition | PSC and accounts | PSC only | accounts only | neither |
|---|---:|---:|---:|---:|
| without recorded adverse insolvency | 3,937,786 | 1,514,385 | 953 | 135,939 |
| recorded adverse insolvency | 4,881 | 929 | 80 | 1,428 |
| ambiguous liquidation — excluded | 72,225 | 8,922 | 1,011 | 26,172 |

After excluding ambiguous liquidation, the primary target population has 5,596,381 companies and
a recorded-adverse prevalence of 0.1308%. Source availability itself differs by group, especially
for PSC, and must not be hidden by complete-case analysis.

The adverse group is large enough for a bounded study but structurally concentrated: 7,075 of
7,318 (96.7%) are private limited companies. Its age-band counts are 74 at 0–23 months, 742 at
24–59 months, 1,777 at 60–119 months, 2,059 at 120–239 months and 2,666 at 240 months or more.
This supports broad adjustment and a private-limited-company sensitivity analysis, not detailed
claims for every rare company type.

### 2.2 Label interpretation and limitations

The narrow positive label is reliable as a description of an explicit adverse process status in
the selected register snapshot. It is not a complete insolvency outcome label: it omits unresolved
liquidations, companies whose status has not yet changed, and companies already dissolved or absent
from this register population. The comparison group can therefore contain latent or unrecorded
adverse cases and must always be called **companies without recorded adverse insolvency**, never
“healthy companies”, “solvent controls” or “confirmed negatives”.

No solvent-winding-up group can be identified from this join. In particular, none of the 108,330
`Liquidation` rows can be called a members' voluntary liquidation without the missing case-type
evidence.

The selected register is a current-register/current-status population. The aggregate contains no
`dissolved`, `converted-closed`, `closed` or `removed` status. Previously dissolved companies are
outside the target population, so results cannot describe all companies incorporated historically
or all insolvencies. This differs from the historical case-only study and is why its historical
cases are not reused as positives here.

To classify the 108,330 liquidation rows as adverse or solvent, the minimum additional input is a
versioned, point-in-time company-to-insolvency-case table at the reference date with case types,
including `members-voluntary-liquidation`, and a documented company-number linkage. A newly fetched
current API response would not reconstruct 2026-10-01 state. To identify adverse events not visible
in current status would additionally require an approved, dated outcome source with event dates and
coverage through the reference date. Neither input should be fetched for this design phase.

### 2.3 Predeclared cohort sensitivities

The primary cohort includes `Active - Proposal to Strike off` in the comparison group because it is
not recorded adverse insolvency. Report two sensitivities without redefining the primary label:

1. restrict the comparison group to `Active` only;
2. restrict both groups to private limited companies, where positive support is adequate.

Do not relabel all liquidation as adverse. A descriptive appendix may report the ambiguous group
separately, but it must not be included in supervised model fitting without the missing case-type
evidence.

## 3. Attributes and adjustment

### 3.1 Outcome fields versus candidate attributes

Use an explicit predictor whitelist. The following are outcome construction or identifiers and are
never model predictors:

- `company_number`, `reg_company_status` and the derived study-group label;
- any future insolvency status, status detail, insolvency case type/link, liquidation-history flag,
  label-source field or label timing field;
- `psc_corporate_reg_numbers`, because it is a high-cardinality identifier/linkage field rather
  than a company attribute for this comparison;
- raw calendar dates when the corresponding predeclared elapsed-time or overdue attribute exists.

At implementation, fail if a forbidden field enters a model matrix. The present schema contains no
case-level insolvency columns, but absence from this version is not a substitute for the assertion.

Proposed feature families are:

- **Structural:** broad company type, fixed age bands, SIC-2007 section multi-hot indicators and
  explicit unknown/multiple-section indicators.
- **Register attributes:** SIC count and dormant/non-trading/NEC markers; previous-name count;
  charge counts; register accounts category; accounts and confirmation-statement overdue flags;
  accounts-never-filed; and companies sharing the postcode. Status is excluded.
- **Accounts attributes:** period recency/availability, period count and gap; equity, current assets,
  short-term creditors, net current assets, cash, current ratio, employee band, anomaly diagnostic,
  period changes and accounts category. Preserve null as unavailable; do not convert it to zero or
  false.
- **PSC attributes:** PSC/cessation and entity-type counts, ownership/voting bands, control flags,
  nature counts, protected-record count, UK-format corporate count, unmapped-nature count, identity
  verification counts, active statement categories and information state. Preserve source absence
  separately from a present PSC row with null values.

The feature lists are fixed before outcome distributions are inspected. The study does not invent
threshold rules or select features because they separate these groups.

### 3.2 Structural adjustment and size

Primary adjustment uses company type, age and SIC section because all three can strongly determine
both filing structure and the observed attributes. Use fixed age bands `0–23`, `24–59`, `60–119`,
`120–239` and `240+` months. Pool rare company types into a predeclared “other” category using total
training frequency only, never outcome-specific frequency. Represent all recorded SIC sections,
rather than selecting a single section from a multi-SIC company.

Financial size is itself an attribute of interest. Therefore the primary analysis must not match
or adjust away employee band, assets or accounts category before describing their association.
Report a secondary size-conditioned sensitivity using broad register accounts category, and for
non-size attributes optionally employee band where observed. That sensitivity asks whether other
associations persist within similar reporting/size groups; it does not replace the unadjusted size
comparison. Never call accounts category a pure size measure: it also reflects filing regime and
coverage.

## 4. Descriptive analysis

Run aggregate descriptions before any model:

1. Reproduce the cohort flow and status mapping exactly, with the three dispositions summing to
   5,704,711.
2. Report `has_psc` and `has_accounts`, their four mutually exclusive combinations, and every
   feature's observed/null count by outcome group. Source absence and within-source null are separate
   states.
3. Report the same coverage by broad company type, age band and SIC section. Accounts coverage is
   additionally stratified by register accounts category. Apply the repository's small-count
   suppression to displayed tables.
4. For binary attributes, report both group proportions, percentage-point difference, prevalence
   ratio and odds ratio with 95% intervals. Denominators are observed values, not the full group
   unless the attribute is complete.
5. For categorical attributes, report distributions and a global association measure such as
   Cramer's V. For continuous attributes, report median/IQR, selected quantiles, a robust location
   difference and a rank-based effect size. Use signed-log views for highly skewed signed financial
   values, while retaining original-unit summaries.
6. Report crude and structurally adjusted estimates. Treat multiplicity explicitly: retain all
   predeclared attributes, show confidence intervals and false-discovery-rate-adjusted descriptive
   p-values, but do not use significance to create rules.

These results establish contemporaneous associations and distributional separation among companies
present in the selected register. They do not establish temporal precedence, causality or future
insolvency prediction.

## 5. Classification design

### 5.1 Evaluation populations and splits

Use the 5,596,381-company primary cohort for the main analysis. Assign companies to an 80% training
partition and 20% untouched test partition reproducibly from normalised company number and a fixed
seed, preserving the outcome allocation. Split before any comparison sampling or preprocessing.
Although there is one row per company, retain and assert company-level separation so later
extensions cannot leak a company across partitions.

Use all 7,318 adverse-status companies. For computationally bounded fitting, draw a reproducible
uniform random sample of comparison companies independently within each train/test partition,
targeting approximately 20 comparison companies per adverse company in that partition. Every
comparison company has the same strictly positive inclusion probability within its partition:
`min(1, target comparison count / eligible comparison count)`. Cases have inclusion probability
one. Record the exact eligible, target and sampled counts, seed, inclusion probabilities and inverse
probability weights for both partitions. Apply those weights during model fitting, training-only
validation and held-out evaluation. Twenty-to-one yields at most about 146,360 comparison rows; the
expected test partition retains about 1,464 adverse companies, giving roughly ±2.6 percentage
points for a test sensitivity near 50% before design effects.

The untouched test set must either retain the snapshot prevalence or use inverse-probability
weights back to the exact primary-cohort counts: 7,318 adverse and 5,589,063 comparison companies.
The displayed 0.1308% prevalence is rounded and must never be used for reconciliation. Unweighted
precision, PR curves, calibration or probabilities from a case-control sample are not population
quantities and must not be reported as such.

### 5.2 Models on consistent populations

Fit an L2-regularised logistic regression as the only planned classification model. Training-only
selection of regularisation strength by cross-validation is expressly permitted, with preprocessing
refitted inside each training/CV fold. Production-rule or threshold tuning remains prohibited. Do
not use the test partition for feature selection, transformations, hyperparameters, thresholds or
post-hoc changes to the analysis.

Compare these predeclared matrices on the same full-cohort split and sampled companies:

1. **Missingness only:** `has_psc`, `has_accounts` and candidate-feature observation indicators, no
   observed values.
2. **Structural baseline:** company type, age band and SIC sections.
3. **Structural + missingness:** structural attributes plus the complete missingness-only matrix.
4. **Register:** structural plus eligible register attributes.
5. **Accounts:** structural plus accounts attributes and accounts missingness indicators.
6. **PSC:** structural plus PSC attributes and PSC missingness indicators.
7. **Combined:** all eligible structural, register, accounts and PSC attributes plus missingness
   indicators.

Report incremental separation over the structural, missingness-only and structural + missingness
baselines. Compare the combined model directly with structural + missingness on identical held-out
companies and report paired uncertainty for that increment. Also repeat all seven matrices on the
fixed complete-source intersection (4,881 adverse and 3,937,786 comparison companies before
sampling). This secondary analysis compares content where both sources are present but is explicitly
selection-conditioned and cannot replace the full-cohort result.

### 5.3 Preprocessing and reporting

Fit every operation on training data only: category dictionaries and rare-category pooling,
imputation values, signed-log transforms, scaling and regularisation. Numeric missing values receive
a training median plus a missingness indicator. Categorical missing values receive an explicit
level; source absence remains distinguishable from a null attribute in a present source row.

Report weighted test ROC AUC, prevalence-corrected PR AUC, weighted log loss/Brier score and
calibration intercept/slope with bootstrap confidence intervals. If any thresholded precision,
recall or confusion matrix is shown, choose the threshold on training data, weight back to snapshot
prevalence and label it contemporaneous status classification. Do not emit company-level scores,
rankings or reusable decision thresholds.

Model coefficients are conditional associations, not causal effects. Compare model families only
on identical test companies and provide bootstrap intervals for metric differences. The expected
dominance of easy status-correlated availability or filing patterns is an empirical question; the
missingness-only baseline is specifically intended to reveal it.

## 6. Gates, outputs and decisions

Implementation must stop if any of these fails:

- input path/hash/date differs from the reviewed Handoff 10 manifest;
- company numbers are not unique, cohort counts do not reconcile, or a status is missing/unmapped;
- ambiguous liquidation enters either supervised class;
- an outcome-defining or identifier field enters a predictor matrix;
- train/test company overlap exists or preprocessing is fitted outside training data;
- observed-value and missingness denominators cannot be reproduced;
- weighted sampling totals do not reconcile to exactly 7,318 adverse and 5,589,063 comparison
  companies in the primary cohort.

Only aggregate tables, model coefficients/metrics and provenance may be committed. Keep row-level
samples, assignments and scores gitignored. Preserve the no-tuning, no-composite-score and
small-count-suppression requirements.

Approved implementation decisions:

1. use the narrow adverse-status mapping and exclude all `Liquidation` rows;
2. accept PSC's six-day-earlier reference state as sufficiently contemporaneous and document it;
3. include `Active - Proposal to Strike off` in the primary “without recorded adverse insolvency”
   group, with the active-only sensitivity;
4. run the full-cohort and complete-source-intersection analyses, the private-limited-company
   sensitivity, and the documented uniform approximately 20:1 comparison sampling design;
5. do not acquire additional data or classify the liquidation group in this study.

The narrow contemporaneous study is approved and feasible with existing local data. Broader
adverse-insolvency coverage, especially classification of liquidation, remains outside scope and
requires the additional point-in-time outcome evidence described above.
