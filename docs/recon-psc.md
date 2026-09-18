# PSC bulk snapshot — recon brief

*Agent brief. Work on a branch; do not push or open a PR. Deliverable is a script, its
generated output, and this file updated with the measured results. Every number quoted in
project docs about the PSC product must come from this recon, run over ALL parts of the
snapshot, not from a single part.*

## Purpose

Establish what the Companies House PSC bulk snapshot actually contains, at what quality, and
with what time structure, before writing the extractor spec. Mirrors `docs/recon-accounts.md`.

Three questions the spec depends on and which a single part cannot answer:

1. **History.** Are ceased PSC records retained (so point-in-time control structure can be
   reconstructed), and over what date range?
2. **Statements.** Do PSC *statement* records (no-PSC-identified, PSC-unidentified,
   super-secure etc.) exist in the product, and where?
3. **Partitioning.** How are the 32 parts partitioned? A one-part probe showed a
   `notified_on` year distribution that alternates implausibly (see "Prior evidence"), which
   means parts are not random samples and any per-part rate is unusable.

## Input

- `psc-snapshot-YYYY-MM-DD_{k}of{N}.txt`, newline-delimited JSON, one record per line.
  Record shape: `{"company_number": str, "data": {...}}`. Snapshot date is in the filename;
  record it in the output as `snapshot_date`.
- Read as a stream; do not load a part into memory. Parts are ~415 MB / 500k lines each.
- Do NOT write any per-record output containing `name`, `name_elements`, `address` (other
  than derived fields listed below), or `date_of_birth`. Recon outputs are aggregates only.

## Output

`docs/recon-psc-results.json` (machine-readable, one object) and a generated
`docs/recon-psc-results.md` table rendered from it. The script lives at
`scripts/recon_psc.py`, takes a glob of parts, and is deterministic. Emit `n_parts`,
`n_records`, `n_bad_lines`, and the snapshot date at the top of the output.

## Measurements

All counts both overall and **per part** (so the partitioning question can be answered).

### Structure
- Top-level keys and `data` keys: presence count of every key seen.
- `kind` distribution.
- Records with `description` and/or `ceased` (boolean) but no `notified_on` — these are the
  super-secure / statement-like records. List their `kind` and `description` values.
- Whether any record has a `statement` field or a `kind` containing `statement`. If none in
  any part, state that the product excludes statement records and note the API endpoint
  (`/company/{n}/persons-with-significant-control-statements`) as the only source.

### Time structure
- `notified_on` present rate; year distribution; min/max.
- `ceased_on` present rate; year distribution; min/max.
- Cross-tab `notified_on` year × ceased (bool).
- Records with `ceased_on` < `notified_on` (should be zero; report if not).
- `notified_on` before 2016-04-06 (pre-regime dates — report count; these are likely
  backdated or data-entry, not real PSC events).

### Per-company
- Distinct companies; PSCs per company distribution (active only, and all).
- Companies whose only records are ceased.
- Companies with ≥1 corporate PSC; with ≥1 individual PSC; mixed.

### Individuals (`kind` starts with `individual`)
- `date_of_birth` presence (year, month).
- Year-of-birth distribution in 5-year bands; count of implied age <16 or >110 at
  `notified_on` (data-quality flag).
- `nationality` presence; distinct raw values; top 30 after `.strip().title()`.
  (Measured for data-quality documentation only — nationality is excluded from the product,
  see `psc.qmd`.)
- `country_of_residence` presence; top 30; share UK (England/Scotland/Wales/Northern
  Ireland/United Kingdom + spelling variants — record the normalisation map used).
- `address.country` presence; top 30; share UK by the same map.
- `address.postal_code` presence; share matching a UK postcode regex; share matching after
  whitespace/case normalisation.
- Share whose service address postcode equals the company's registered-office postcode
  (join to the general snapshot `RegAddress.PostCode`; report join rate too).
- `identity_verification_details` presence; `appointment_verification_start_on` year
  distribution.
- `is_sanctioned` presence and value counts.
- Person-key connectivity: key = (`forename` lower, `surname` lower, DOB year, DOB month).
  Report distribution of records-per-key and distinct-companies-per-key, **overall across all
  parts** (this is the number that matters; per-part connectivity understates it). Do not
  persist the key table beyond the run.

### Corporate PSCs (`kind` starts with `corporate` or `legal-person`)
- `identification` sub-keys presence.
- `registration_number`: presence; share matching `^[A-Z0-9]{8}$` after upper/strip; share
  that resolve to a company number present in the general snapshot (join rate).
- `country_registered` top 30 and UK share (same normalisation map).
- `legal_form` top 20.

### Natures of control
- Full vocabulary with counts. Group by suffix family: plain / `-as-firm` / `-as-trust` /
  `-limited-liability-partnership` / `-registered-overseas-entity` / other. Report how many
  distinct base rights exist once suffixes are stripped.

### Partitioning diagnostic
- Per part: company-number prefix distribution, `notified_on` year distribution, `kind`
  distribution. State the partition rule if one is evident (by hash? by company number
  range? by record id?). If not evident, say so.

## Acceptance
- Script runs over all parts in one invocation and finishes; runtime reported.
- Every number in `docs/recon-psc-results.md` traces to a field in the JSON.
- The three questions in "Purpose" each have a one-paragraph answer in the "Results"
  section below, with the supporting numbers.
- No personal data in any output file. Reviewer greps outputs for `forename`, `surname`,
  `address_line`, `date_of_birth` as a check.

## Prior evidence (single part, 2of32, snapshot 2026-09-11 — PROVISIONAL, do not cite)

500,000 records, 400,709 companies, 0 bad lines. Kinds: individual 92.2%, corporate 7.0%,
legal-person 0.1%, beneficial-owner variants (ROE) 0.7%, super-secure 32 records.
`ceased_on` present 16.8%, years 2016–2026. `notified_on` present 99.99%, years alternating
2016: 165k / 2017: 55k / 2018: 9.8k / 2019: 38k / 2020: 8.8k / 2021: 99k / 2022: 4.4k /
2023: 118k / 2024: 2 — not a real filing pattern. No statement records. `is_sanctioned`
present 3,258, True 4. `identity_verification_details` on 41% of individuals. UK-format
postcode 97%. Nationality 885 distinct raw values. Corporate `registration_number` 8-char
in 26,132 of 33,064 present. Person-key: 3.7% of keys on ≥2 records within the part.

## Results

**Run.** Snapshot **2026-09-18**, all **32 of 32** parts, **15,952,486 records, 0 bad
lines**, runtime 404 s single-threaded. The 2026-09-11 snapshot named in "Prior evidence"
was no longer published when this recon ran — Companies House serves only the current day's
PSC snapshot — so all 32 parts of 2026-09-18 were downloaded fresh; the script refuses to
mix snapshot dates in one run. Join base: BasicCompanyData 2026-08-01 (5,695,465 live
companies; note the ~7-week skew against the PSC snapshot). Full numbers:
`docs/recon-psc-results.json` / `docs/recon-psc-results.md`; every figure below traces to a
JSON field.

**1. History — yes, ceased records are retained, usable from 2016-04-06.** 2,655,316
records (16.6%) carry `ceased_on`; 2,655,219 of them (99.996%) fall in 2016–2026, the
regime's lifetime, and every `notified_on` year since 2016 retains a ceased cohort (2016:
814,461 ceased vs 3,242,562 not). 62,986 companies exist in the product only as ceased
records. The product spans **10,917,257 distinct companies — nearly double the live
register** (5,695,465), so it retains PSC history for companies no longer on the live
snapshot (the 54.2% company join rate for postcode-bearing individuals is consistent with
this, not a defect). Point-in-time control reconstruction is therefore feasible from
2016-04-06 onward, subject to a cleaning rule for: 14,554 records with
`ceased_on` < `notified_on` (not zero as hoped), 23,916 pre-regime `notified_on` dates
(min 1083-01-01), and 97 `ceased_on` outliers outside 2016–2026 (including 2924, 9998,
9999).

**2. Statements — yes, the product contains them, segregated at the tail.** 922,564
records (5.8%) have `kind = persons-with-significant-control-statement`, all of them in
parts 31 (470,187) and 32 (452,377). Part 32 contains **no** individual or corporate PSC
records at all — only statements, 108 `exemptions` records, and a single
`totals#persons-of-significant-control-snapshot` trailer record. The prior one-part probe
saw "no statement records" because parts 1–30 genuinely contain none. The API statements
endpoint is NOT the only source; the brief's fallback note does not apply. Super-secure
records (384 PSC + 161 beneficial-owner) are the only statement-like records under the
brief's definition (description/ceased with no `notified_on`); together with exemptions
and the totals trailer they account for exactly the 654 records lacking `notified_on`.

**3. Partitioning — positional slices of a non-random internal ordering; per-part rates
are unusable.** Parts are NOT partitioned by company number: every part's company-number
range spans essentially the whole register (mins ~`000001xx`, maxes in `SO`/`SZ`/`ZC`
prefixes) and no part is internally sorted, so the ranges overlap completely. Nor are they
random samples: statements are segregated into parts 31–32; parts 25–30 are dominated by
recent `notified_on` years (25–26 by 2024, 27–28 by 2025 at up to 97%, 29–30 by 2026); and
parts 1–24 mix vintages with 2016 heaviest. This is consistent with a fixed-size positional
split of an internal extract held in rough record-creation order with a statements segment
appended — which also explains the implausibly alternating year distribution in the prior
single-part probe. Extractor rule: treat part boundaries as meaningless, stream all parts,
never quote a per-part rate.

**Headline quality numbers (overall).** Kinds: individual PSC 87.1%, corporate 6.7%,
statement 5.8%, legal-person 0.1%, ROE beneficial-owner variants ~0.3%, super-secure 545,
exemptions 108. Individuals (13,921,890): DOB year and month 100.0% present; implied age at
notification <16: 17,729 and >110: 55; nationality 100.0% present with 4,666 distinct raw
values; country of residence 99.7% present, 91.6% UK; `address.country` 89.2% present,
97.1% UK; service postcode 99.3% present, 98.1% UK-format (raw and normalised); of the
7,480,567 joined to a live-snapshot company with a registered-office postcode, **78.1%
have service address postcode = registered-office postcode**;
`identity_verification_details` on 50.6% (start years 2025: 240,962; 2026: 3,668,702);
`is_sanctioned` present on 34,444, True on 17. Person-key connectivity **overall**:
8,586,821 distinct keys; **28.8% on ≥2 records and 28.0% on ≥2 distinct companies** —
roughly 7.6× the single-part 3.7% figure, confirming that per-part connectivity badly
understates linkage. Corporate (1,107,378): `identification` 100.0%;
`registration_number` on 91.0%, of which 81.7% are 8-char `[A-Z0-9]` and 77.9% resolve to
a live-snapshot company; `country_registered` 90.9% UK. Natures of control: 35,169,887
assertions over 15,029,053 records; 55 distinct base rights after stripping the four
suffix families (`-as-firm` 988,162, `-as-trust` 704,737,
`-limited-liability-partnership` 342,451, `-registered-overseas-entity` 123,964, plain
33,010,573).

**Privacy check.** `docs/recon-psc-results.md` greps clean for `forename`, `surname`,
`address_line`, `date_of_birth`. In `docs/recon-psc-results.json` the only hits are the
key-NAME presence counters the brief requires (`date_of_birth` and `name_elements` appear
once per PSC-bearing part in `data_keys`, with counts, never values — part 32 contributes
none as it holds no PSC records) and one methodology string in `normalisation.person_key`
naming the fields the key is built from. No name, address-line, or birth-date value
appears in any output.
