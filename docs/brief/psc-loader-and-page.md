# Brief: PSC loader, data checks, and `psc.qmd` site page

*For a code agent working in `ThomasHSimm/open-company-uk`. Work on a new branch `feature/psc-loader`.
Never push and never open a PR. Where this brief says **FLAG**, stop and report the numbers; don't
choose.*

Read first: `docs/psc-data-guide.md` (supplied alongside this brief; add it to `docs/`),
`docs/recon-psc.md`, `docs/recon-psc-results.md`, `scripts/recon_psc.py`,
`src/ukcompany/snapshot/` (the existing BasicCompanyData downloader and loader, used here as the
pattern).

## Current state

- **PSC code in the package: none.** `scripts/recon_psc.py` streams the parts and writes aggregate
  counts only, with no per-record output. `src/ukcompany/snapshot/` handles BasicCompanyData only:
  `download.py` matches `BasicCompanyData-…zip` and nothing else.
- **Raw PSC parts** exist locally for 2026-09-18, 32 parts. They are newline-delimited JSON, one
  record per line, shaped `{"company_number": …, "data": {…}}`. Note that `company_number` is
  **outside** `data`.

## Global rules

- Use ruff with line length 100, and pytest. Put runtime settings in `settings.yaml` only.
- Run every full-scale job under `systemd-run --user --scope -p MemoryMax=<N>G`. There are no
  exceptions.
- Use DuckDB for full-scale work and write results with `COPY … TO '…parquet'`. Never pull
  full-size frames into Python.
- **Count every line into exactly one category and assert that the counts reconcile.** Treat an
  exact 0% or 100% as a warning to investigate.
- The loader keeps personal data by default only when the user asks for it. See the
  `data_governance` switch in Task B. Whatever the setting, nothing personal goes into `docs/`,
  the site, tests or logs. Output tables live under `data/` (gitignored). Test fixtures are
  synthetic.

## Task A: PSC downloader and archive

1. Add PSC support to `snapshot/download.py`, or a sibling module:
   - landing page: `https://download.companieshouse.gov.uk/en_pscdata.html`
   - part filename pattern: `psc-snapshot-YYYY-MM-DD_{k}of{N}.zip`
   - require a complete N-of-N set for a single date
2. **Keep the zips as the archive.** Do not delete them after extraction. Write a manifest with
   each part's sha256, size and the snapshot date, reusing `manifest.py`.
3. Report the total zipped size of one full day. That figure decides the archiving design (full
   daily copies vs periodic copy plus diffs). **FLAG**, don't decide.
4. Add a CLI entry point that can be run from cron. Scheduling is T's job.

## Task B: Loader to Parquet (private)

Goal: turn the raw parts into tables that can be queried, **without losing anything**.

**Parsing approach.** Don't rely on DuckDB schema inference over the whole file. Rare keys such as
super-secure fields or identity-verification sub-keys can be dropped or mistyped by sampling.
Instead, read each line as JSON text (e.g. `read_ndjson_objects`) and pull each field out
explicitly by JSON path. Keep the full `data` object as a JSON `raw` column, so fields we haven't
extracted yet are still available.

**Outputs, all written under `data/psc/<snapshot_date>/`:**

| Table | Grain | Contents |
|---|---|---|
| `psc_records.parquet` | one row per line | see below |
| `psc_noc.parquet` | one row per (record, nature of control) | `record_id`, `right_raw`, `base_right`, `suffix_family` (`plain`, `as-firm`, `as-trust`, `limited-liability-partnership`, `registered-overseas-entity`), `band` where one exists |
| `psc_totals.json` | the single totals line | Companies House's own counts |
| `load_report.json` | run level | category counts, reconciliation, flag counts, runtime |

**`psc_records` columns:**

- **Identity of the row:**
  - `snapshot_date`, `part`, `line_no`
  - `company_number`: taken from the top level; also parse the company number from `links.self`
    and count any mismatches
  - `psc_id`: the last segment of `links.self`
  - `record_id` = `company_number` + `psc_id`
- **What kind of record it is:**
  - `kind`
  - `category`, one of: individual, corporate, legal_person, statement, super_secure, exemption,
    bo_individual, bo_corporate, bo_legal, totals, unknown
- **Names:** `name`, `forename`, `middle_name`, `surname`, `title`. Confirm the middle-name key's
  actual spelling in the data. **FLAG** if it is not `middle_name`.
- **Birth, residence and address:**
  - `dob_year`, `dob_month`
  - `nationality`: extracted for data-quality work only; it is not a feature
  - `country_of_residence`
  - service address fields, plus `postcode_norm` (uppercase, no spaces)
- **Corporate identification:** `reg_number_raw`, `reg_number_norm`, `country_registered`,
  `legal_form`, `legal_authority`, `place_registered`
- **Statements and flags:** `statement`, `is_sanctioned`
- **Identity verification:** its own columns. First dump the distinct key paths inside the block,
  then extract all of them.
- **Dates:** keep `notified_on_raw` and `ceased_on_raw` as strings. Add `notified_on` and
  `ceased_on` as `TRY_CAST` to DATE.
- **Date flags:** `f_ceased_before_notified`, `f_pre_regime` (notified before 2016-04-06),
  `f_ceased_out_of_range`, `f_age_under_16_at_notified`
- `raw` (JSON)

**`data_governance` switch.** Add it as a loader argument and CLI flag (`--data-governance` /
`--no-data-governance`), settable in `settings.yaml`. **Default: `True`.** People running the
public code get the safer output unless they choose otherwise. T runs with `False`.

- **`False`:** keep every field as described above. This is the full private table.
- **`True`:** before writing anything to disk:
  - drop `nationality`
  - replace `dob_year` and `dob_month` with `birth_band_5y`
  - drop the name fields and the address lines, keeping only `postcode_district`, the outward
    code such as `SA1`
  - **drop `raw`, or rewrite it with the same fields removed.** `raw` holds the whole original
    record, so leaving it in would undo everything above. Add a test that proves no dropped field
    survives anywhere in the output.
- **Person keys in `True` mode.** Compute them *before* dropping names, so that
  companies-per-person features still work. Store them as a keyed hash (HMAC) using a secret held
  per installation, in `.env` and never committed. A plain hash of name plus birth month can be
  reversed by hashing a list of common names.
- Record the mode in `load_report.json` and in the Parquet metadata, so no table is ever mistaken
  for the other kind.

**Don't fix dates.** Flag them, and **FLAG** the counts. The rules for handling each case are T's
decision.

**Accounting invariant.** Assert that the category counts sum to the number of lines read, and that
`unknown` is 0 (or list every unknown kind). Reconcile against the recon, which found 15,952,486
lines and the kind counts in `recon-psc-results.md`, and against `psc_totals.json`. Report every
difference. Do not explain differences away.

**Tests** (synthetic fixtures, one per kind):
- an individual with and without `ceased_on`
- a corporate owner
- a statement
- a super-secure record
- an exemption
- the totals line
- a malformed line
- an impossible date

## Task C: Answer the open checks

Write `scripts/psc_checks.py`. It outputs `docs/psc-checks-results.md` and `.json`, containing
**aggregates only**, and answers:

1. The middle-name key and its fill rate for individuals, active only and overall.
2. Does any `psc_id` appear under more than one company? Give the count.
3. The full key structure of the identity-verification block. Is any field a candidate
   cross-company identifier? Report key names and fill rates only.
4. The totals line vs our counts.
5. Share of person keys linked to 2+ companies: **active only** vs **ever**. Compute it with the
   recon key and with a key that adds the middle name.
6. For keys on 11+ companies: how common is the name (count of distinct keys sharing forename and
   surname)? Report the distribution only.
7. Corporate owners that don't link to a live company, broken down into:
   - good-format reg number, no match
   - bad format that matches after normalisation
   - non-UK `country_registered`
   - missing
8. Zipped size of a full day (from Task A).

Use a BasicCompanyData snapshot as close as possible to the PSC date for joins, and report the
gap in days.

## Task D: Site page `docs/site/psc.qmd`

**Structure.** Base the text on `docs/psc-data-guide.md`, including §5 on data governance
verbatim. Replace each **[check]** marker with the Task C result, or leave it and say why. Add the
page to `_quarto.yml` next to `accounts.qmd`.

**No personal data or raw files at render time.** A script,
`scripts/psc_site_aggregates.py`, writes small aggregate files to `docs/site/data/psc/` and
figures to `docs/site/figures/psc/`. The `.qmd` embeds these. This keeps the site renderable
without the 2 GB snapshot, and consistent with `accounts.qmd`, which executes no code.

**Small-count suppression:** any published cell with a count below 10 is shown as "<10".

**Nationality is never plotted or tabulated.**

**Figures.** Plain, labelled with units, and each captioned with the snapshot date:

1. Records by kind, as a bar chart on a log scale, so the small kinds show up.
2. History: records by year control started, split into still-active vs ended. This shows why the
   file is roughly twice the live register.
3. Active PSCs per company: distribution from 0 to 10+, plus the count of companies with only a
   statement.
4. Natures of control: share bands (25–50 / 50–75 / 75–100) for shares and for votes, and the mix
   of suffix families.
5. Active statement codes, with counts, using the literal codes.
6. Corporate owners: a funnel from "has reg number" to "valid format" to "matches live company",
   plus the unmatched breakdown from Task C.
7. Identity-verification uptake by start month, 2025–2026.
8. Field coverage heatmap: fill rate per field (rows) by category (columns).
9. Data-quality table: impossible dates, pre-regime starts, under-16s, super-secure,
   links/company mismatches.
10. **Area heatmap:** active PSC records by registered-office location.
    - Join postcodes to latitude and longitude using the ONS Postcode Directory (open government
      licence; check the attribution wording, and check the Northern Ireland terms). Then draw a
      hexbin density on a log colour scale.
    - This needs no boundary file and no `geopandas`.
    - Formation-agent addresses will show as extreme hotspots. That is real, and the caption
      should say so.
    - Report the share of postcodes that couldn't be placed.
    - Drop the world map; it isn't needed.

**Coverage metrics box at the top of the page:**

- snapshot date
- lines
- companies, all and with active control
- share of live register companies with at least one active PSC or statement (using the matched
  register snapshot)
- percentage of individuals with identity verification

## Stop and report (FLAG) if

- the invariant fails, or the totals line disagrees by more than 0
- the middle-name key is not as expected
- any `psc_id` is shared across companies (this changes the matching design)
- a figure would need a cell below 10 that can't be merged

## Deliverables

- Branch `feature/psc-loader` with:
  - Tasks A–D
  - passing ruff and pytest
  - `load_report.json` summarised in the final message
  - `docs/psc-checks-results.md`
  - `docs/site/psc.qmd` plus its figures
- Final message: the reconciliation table, every FLAG with its numbers, and anything skipped.
