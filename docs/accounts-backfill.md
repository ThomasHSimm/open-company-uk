# Accounts fetch–extract–delete backfill

Use the bounded-disk backfill when the monthly ZIPs are not already staged locally:

```bash
ukcompany-accounts run --from 2019-01 --to 2025-12
```

The inclusive range is constructed month by month. A manifest-complete archive is skipped by name without requiring its deleted ZIP to exist. Other months follow this serial state transition:

```text
download to hidden .part
  → verify Content-Length when available
  → verify ZIP central directory
  → atomically rename
  → extract into SQLite
  → confirm manifest complete
  → stream that month to its own Parquet
  → delete only if downloaded by this process and retention is off
```

The existing `extract` command remains the disk-only entry point. Under the Stage 1 contract it now writes the same per-month outputs and uses the same scope-aware manifest.

## Coverage and exit status

`docs/accounts-coverage.md` is rewritten after every classified month, including immediately before an accounting failure is re-raised. A month is not complete for cleanup purposes until its configured scope is manifest-complete and its monthly Parquet has been written. The report lists:

- present and manifest-complete months;
- completed archives deleted or kept;
- previously completed months skipped without downloading;
- partial development samples;
- HTTP-404 absent months; and
- download, verification, extraction, or cleanup failures with their errors.

Absent and failed months are retried on a later invocation and cause a non-zero exit after the range finishes. Partial months produced by `--limit-per-zip` remain visibly incomplete but are an intentional development outcome.

The effective covered span is the earliest through latest manifest-complete requested month. It is not a claim of continuity: consult the explicit absent and failed lists for internal gaps. This report is the evidence needed before choosing the historical dataset start year.

## Configuration

Runtime settings live under `accounts` in `config/settings.yaml`:

- `downloads_dir` and `store_path`;
- `base_url`;
- `keep_zips`;
- `download_chunk_size`;
- `download_retries` and `download_backoff_seconds`;
- `download_timeout_seconds`; and
- `coverage_report`.

Stage 1 archive settings add `scope` (`all` or a concept list), `kinds` (`all` or `numeric-only`), `monthly_output_dir`, and the `long_input` glob used by downstream consumers.

The CLI can override the range, downloads directory, store, base URL, ZIP retention, output paths, and development sample limit. `--no-keep-zips` overrides a configured `keep_zips: true`.

`--disposable-store` extracts each month into a throwaway per-month working store instead of one monolithic database across the whole range (`extract.process_archive_disposable`); the persistent connection then only ever holds small manifest rows, so peak disk stays at roughly one ZIP plus one month's working set plus the slowly growing Parquet archive, never a multi-hundred-GB scratch database. This is the recommended mode for a full-history run. Trade-off: once a month's scratch store is discarded, that month cannot be re-exported at a different `scope`/`kinds` without re-extracting from the original ZIP, and the extraction report's observation-level stats are not populated (manifest-only) — use `ukcompany-accounts inventory` (reads the Parquets directly) for full-scale stats instead. Default remains the monolithic store for backward compatibility.

## Known boundaries

- Companies House splits monthly archives across two live locations: a rolling recent window at the root path (`download.companieshouse.gov.uk/Accounts_Monthly_Data-{Month}{Year}.zip`) and everything older under `/archive/`. `fetch_archive` tries `base_url` (root) first and falls back to `historic_base_url` (`/archive/`) on a 404, since the boundary between the two shifts monthly and should not be hardcoded.
- Live monthly-URL availability must be measured rather than assumed. A 404 on both candidate URLs is reported as absent and never silently narrows the requested range.
- Downloads restart from byte zero after interruption. HTTP range resume is out of scope for v1.
- Prefetch and parallel extraction are out of scope because they increase peak ZIP storage.
- Central-directory validation catches truncation and structural corruption without decompressing 1–2 GB archives. Companies House publishes no checksum for cryptographic verification.
- ZIP deletion does not limit SQLite/WAL growth or the working space needed for each monthly Parquet export in the default (non-disposable) mode; use `--disposable-store` to bound this.
- `ukcompany-accounts verify` (manifest observation count vs. archived Parquet row count) is the completeness check to run after an unclean shutdown — it never requires scanning the full store.
