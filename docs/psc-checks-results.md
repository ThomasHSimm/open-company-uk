# PSC checks — companies-per-person usability (Task C, focused)

*Branch `feature/psc-loader`. Aggregates only — no names, no DOBs, no person keys, no individual
rows appear in this file or any committed output. Source data: the gitignored full-snapshot load
(`data/psc/2026-09-18-stage1/psc_records.parquet`, 2026-09-18) joined for company type to the
`2026-09-01` Basic Company Data one-file register.*

The one question: **is "companies per person" usable at all**, given there is no stable person
identifier? Keys are fuzzy:

- **baseline key** = lower(forename) + lower(surname) + DOB year + DOB month (the recon's key);
- **strict key** = baseline + lower(middle name) — higher precision, but only computable for the
  ~53% of individuals with a middle name recorded.

## Usability criteria — pre-registered (written before computing)

**C1 — baseline-key detectable-split rate.** The baseline→strict split rate (among strict-eligible
records, the share of baseline keys that map to >1 strict key) measures only **detectable** splits:
a split is either two distinct people who share forename+surname+DOB, or one person recorded with
inconsistent middle names — indistinguishable here. It is an upper bound on *detectable* splits and
**under-counts true collisions**: it cannot see collisions among the ~47% of records with no middle
name (outside the strict key), nor collisions where both people share a middle name. Reading fixed
in advance (applied to the detectable-split rate, not claimed as a total-collision bound): **<2%** →
baseline key not materially split; **2–10%** → usable with caveat; **>10%** → baseline
companies-per-person is materially inflated by conflation.

**C2 — name-frequency confound.** companies-per-person is only interpretable inside name-frequency
bands (band = how many distinct baseline keys share a forename+surname). Reading fixed in advance:
if the ≥2- and ≥11-company rates are low in the **rarest** band and rise monotonically with name
commonness, the high-count tail is predominantly a **common-name collision artifact** → not a
usable person-level identity measure without name-frequency control. If the rarest band itself
shows a genuine multi-company tail, that tail is real multi-directorship (usable within the band).

**C3 — coverage.** The strict key covers only the ~53% of individuals with a recorded middle name,
a **non-random** subset (middle-name recording correlates with record vintage and registrar
practice). Fixed in advance: strict-key figures generalise only to that subpopulation — a
higher-precision / lower-recall, biased-coverage instrument, usable as a precision bound, never as
a population rate.

**Decision rule (pre-registered).** companies-per-person may ship as a documented **attribute**
(carrying its name-frequency band and an explicit match-confidence caveat), never as a rule and
never as a clean identity, **iff** the C1 bound is ≤10% **and** C2 shows an interpretable rare-name
tail. Otherwise it is reported as data-quality context only. No individual-level output either way.

## Method

Individuals only (`category = 'individual'`). Keys built in-query from the raw name/DOB columns of
the private load; only the aggregates below are emitted. "Companies per person" = distinct
`company_number` per key (ever, i.e. active + ceased). Name-commonness bands are by the number of
distinct baseline keys sharing a (forename, surname). Company type for the tail is joined from the
register's `CompanyCategory`.

## Results

Full-snapshot individuals: 13,887,210 records → **8,570,142 distinct baseline keys** and
**4,595,852 distinct strict keys** (a key spans multiple records when a person appears on multiple
companies — or when distinct people collide on one key). Counts below are distinct **keys**.

### (1) Baseline→strict split rate (detectable splits only)

Among the **7,365,820** strict-eligible records (**4,487,009** distinct baseline keys that carry at
least one middle-name record):

| measure | value |
|---|--:|
| baseline keys mapping to >1 strict key | 92,840 of 4,487,009 = **2.07%** |
| strict-eligible records under a split baseline key | 361,475 of 7,365,820 = **4.91%** |

**≤2.07% of baseline keys show a detectable split** (a baseline key that resolves into >1 strict
key). This is **not** a bound on all collisions: it only sees splits within the strict-eligible
subset, so it misses (a) collisions where both people have no middle name recorded (~47% of records,
outside the strict key) and (b) collisions where both share a middle name. The **record-weighted
4.91%** is the more relevant figure for companies-per-person, because the keys that split are
disproportionately the large (many-record) ones. Per C1 (2–10% band): **usable with caveat**.

### (2) companies-per-person by name-frequency band

Name band = number of distinct baseline keys sharing a (forename, surname); "companies per person"
= distinct companies **ever** (active + ceased). No name reached the 1001+ band.

**Baseline key**

| name band | keys | median | p90 | p99 | max | % ≥2 co | % ≥11 co |
|---|--:|--:|--:|--:|--:|--:|--:|
| 1 (unique) | 4,440,327 | 1 | 2 | 7 | 2,858 | 24.98% | 0.30% |
| 2–10 | 2,382,819 | 1 | 3 | 8 | 7,664 | 28.39% | 0.53% |
| 11–100 | 1,442,391 | 1 | 3 | 8 | 4,811 | 32.62% | 0.57% |
| 101–1000 | 304,605 | 1 | 4 | 12 | 1,168 | 46.72% | 1.34% |

**Strict key** (middle-name subset, banded by the same forename+surname commonness)

| name band | keys | median | p90 | p99 | max | % ≥2 co | % ≥11 co |
|---|--:|--:|--:|--:|--:|--:|--:|
| 1 (unique) | 2,048,154 | 1 | 3 | 7 | 2,853 | 26.15% | 0.28% |
| 2–10 | 1,362,213 | 1 | 3 | 8 | 1,871 | 29.08% | 0.47% |
| 11–100 | 920,360 | 1 | 3 | 8 | 1,580 | 30.64% | 0.48% |
| 101–1000 | 265,125 | 1 | 3 | 8 | 396 | 32.07% | 0.53% |

Reading: the **rarest band already shows a genuine tail** (max 2,858; 0.30% on ≥11 companies) — real
multi-directorship, not a common-name artifact (C2's "usable within band" case). But the ≥2/≥11
rates **do rise with name commonness** (≥11 goes 0.30→1.34% across baseline bands), and the strict
key **flattens** that rise (0.28→0.53%) and cuts the common-name-band maximum from 1,168 to 396
(11–100 band: 4,811→1,580). So part of the baseline tail in common-name bands is collision that the
middle name resolves — companies-per-person must carry its name-frequency band; a raw cross-name
count conflates distinct people.

### (3) High-count tail (≥11 companies)

| | unique | 2–10 | 11–100 | 101–1000 | total |
|---|--:|--:|--:|--:|--:|
| baseline tail keys | 13,347 | 12,693 | 8,227 | 4,076 | 38,343 |
| strict tail keys | 5,769 | 6,453 | 4,436 | 1,410 | 18,068 |

~35% of the baseline tail is unique-name (genuine); the rest is in multi-name bands (more
collision-prone). The strict key roughly **halves** the tail (38,343→18,068) — partly coverage,
partly collisions removed by the middle name.

**Company type** of the **659,653** companies linked to a baseline tail key (joined to the
2026-09-01 register; aggregates only):

| company type | companies | share |
|---|--:|--:|
| (unmatched in live register — dissolved/removed) | 337,058 | 51.1% |
| Private Limited Company | 304,770 | 46.2% |
| Private, limited by guarantee, no share capital | 8,122 | 1.2% |
| Limited Liability Partnership | 5,719 | 0.9% |
| Community Interest Company | 959 | 0.1% |
| Limited Partnership / PLC / Unlimited / other | <0.5% each | — |

The tail is **dominated by dissolved shells** (51% unmatched): "ever" companies-per-person
accumulates historical dissolved companies, so an **active-only** variant would be materially
smaller and is the more defensible feature.

## Verdict against the criteria

- **C1 — pass.** Detectable-split rate 2.07% of baseline keys / **4.91% of records** (record-weighted
  is the relevant figure — the large keys are the ones that split). Within the pre-registered 2–10%
  "usable with caveat" band. This counts only splits visible in the strict-eligible subset, so it is
  **not** a bound on the true collision rate (it misses no-middle-name and shared-middle-name
  collisions).
- **C2 — pass, with required controls.** The rarest-name band shows a genuine multi-company tail, so
  companies-per-person is not merely a common-name artifact; but the confound is real and only
  moderate, and is controllable by banding on name frequency and cross-checking with the strict key.
- **C3 — as pre-registered.** Strict coverage is 4.60M of 8.57M baseline keys (~53%), a non-random
  subset; the strict key is a precision bound on the middle-name subpopulation, never a population
  rate.

**Decision (pre-registered rule: attribute iff C1 ≤10% and C2 interpretable — both hold).**
companies-per-person is **usable as a documented attribute**, not as a rule and not as a clean
identity, provided it carries: (i) its **name-frequency band**; (ii) a **match-confidence caveat**
(2.07% of baseline keys show a detectable split, 4.91% record-weighted — detectable splits only, not
a bound on true collisions; the strict key gives higher precision at ~53% recall); and
(iii) **active-only vs ever** (51% of tail companies are dissolved — prefer active-only).
No individual-level output is produced or committed.

