# Companies House accounts extractor

The accounts extractor is separate from the Companies House API pipeline. It reads monthly accounts ZIP members directly in memory, writes an unreconciled LONG Parquet table, and can later create a map-driven WIDE table with cell-level provenance.

## Bounded-disk historical run

The month-driven `run` command downloads, extracts, and conditionally deletes one archive before moving to the next:

```bash
ukcompany-accounts run --from 2019-01 --to 2025-12
```

It does not discover whatever happens to be present in the downloads directory. Every requested calendar month is classified as complete, absent, failed, or an intentional partial sample in `docs/accounts-coverage.md`. An absent or failed month makes the command exit non-zero after the remaining months have been attempted.

Downloads stream to `.Accounts_Monthly_Data-….zip.part`. The final name appears only after any supplied `Content-Length` matches and the ZIP central directory opens successfully. Stale `.part` files are removed on restart. Transient requests retry with exponential backoff; HTTP 404 is classified as absent without retry.

Automatic deletion happens only when the ZIP was downloaded during the current process, the extraction was unlimited, the manifest records the archive complete, and ZIP retention was not requested. Consequently, these modes always retain archives:

```bash
ukcompany-accounts run --from 2022-01 --to 2022-02 --limit-per-zip 1000
ukcompany-accounts run --from 2019-01 --to 2019-12 --keep-zips
```

A manually staged ZIP is never automatically deleted. An extraction failure or accounting non-closure also leaves the ZIP in place; accounting non-closure aborts the entire run.

This bounds ZIP storage to approximately one monthly archive during the default serial workflow. It does not bound the accumulating SQLite store or WAL, and final Parquet export needs additional temporary space. Companies House supplies no per-file checksum, so verification is limited to HTTP length and ZIP-structure checks. HTTP range resume and parallel prefetch are deliberately deferred.

## Extract LONG

```bash
ukcompany-accounts extract ~/Downloads/Accounts_Monthly_Data-January2023.zip
```

With no archive arguments, matching archives are discovered under the configured downloads directory. Progress is committed to a SQLite manifest per archive. Completed unchanged archives are skipped; a partial archive is safely processed again because observations use an idempotent identity constraint.

`--limit-per-zip N` selects an evenly distributed development sample and deliberately leaves its manifest entries marked partial.

## Generate QA before choosing WIDE columns

```bash
ukcompany-accounts qa --long data/accounts/accounts-long.parquet
```

This writes the member-frequency histogram and total-versus-component reconciliation. Neither output corrects source values. Select the final member map only after reviewing that evidence.

## Pivot WIDE

The pivot uses the reviewed [`config/accounts-wide-columns.json`](../config/accounts-wide-columns.json) by default. It contains all nine genuine totals and the approved Share Capital and Retained Earnings Equity members. An alternative reviewed map can be supplied with `--column-map`.

For predictive work, use:

```bash
ukcompany-accounts pivot \
  --long data/accounts/accounts-long.parquet \
  --mode as_first_reported
```

`as_first_reported` selects the earliest archive month among current-period observations. `latest` selects the latest archive month and therefore incorporates later comparative restatements. Archive month—not `made_up_to_date`—is the available point-in-time boundary.

The WIDE row carries `n_concepts_present`, `n_source_filings`, and `row_available_yyyymm`. A separate provenance Parquet has one row per selected WIDE cell with its own source archive month, member filename, and made-up-to date.

Missing values remain null. Monetary facts whose resolved unit is not GBP are retained and flagged in LONG but excluded from WIDE; no currency conversion occurs.

## Creditors totals

Creditors are dimensionally dominant. Genuine non-dimensional Creditors totals occurred in only about 4% of company-periods in the two-archive validation sample. The earlier panel report's approximately 52% was a conflated legacy metric that promoted some agreeing dimensional-only groups.

A null WIDE `Creditors` total therefore does **not** mean that the filing omitted creditor information. Creditors member columns remain gated on larger-sample reconciliation characterisation, so v1 intentionally carries no broad Creditors signal beyond the rare genuine total.

## Limitations and publication gates

- Pre-2019 archives remain unvalidated. Reconnaissance around 2010, 2013, and 2016 is required before selecting an effective start year.
- The extractor skips and counts plain XML filings.
- Non-zero scale is supported and synthetically tested, but the real recon samples contained only missing or zero scale.
- Employee-count coverage changes from about 24% in 2019 to 33% in 2020 and 85% in 2021. This is a reporting-regime break, not company signal.
- Equity missingness varies by more than ten percentage points across months and is non-random.
- `as_first_reported` is the required publication mode for predictive datasets. `latest` has look-ahead leakage.
- A random regex-versus-lxml parser-agreement audit is required before starting a full-history extraction.
- The v1 WIDE map is approved. PropertyPlantEquipment members are deferred pending class normalisation, Creditors members remain gated on larger-sample reconciliation characterisation, and the effective start year and Kaggle/OGL wording still require human approval.
