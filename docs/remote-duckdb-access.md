# Optional DuckDB remote access through fsspec

The DuckDB-backed PSC and accounts readers have two explicit backends:

- `native` is the default and preserves the existing behaviour. Local files continue to work,
  and DuckDB may autoload its native `httpfs` extension for HTTP or S3 URIs.
- `fsspec` registers a Python filesystem on the same in-memory DuckDB connection that executes
  the SQL. DuckDB still parses NDJSON, CSV and Parquet; there is no PyArrow data intermediary.

Use `fsspec` when DuckDB imports but `httpfs` is unavailable in the execution environment.
Install the optional packages with:

```bash
pip install -e '.[remote]'
```

This adds `duckdb`, `fsspec`, `s3fs` and `aiohttp`. They are imported lazily, so the default
native/local paths do not require the remote extra.

## Configuration

Both `accounts:` and `psc:` accept these settings in `config/settings.yaml`:

```yaml
accounts:
  duckdb_backend: fsspec
  fsspec_options:
    s3:
      profile: research
      client_kwargs:
        endpoint_url: https://object.example.org
    http:
      headers:
        Authorization: "Bearer replace-me"

psc:
  duckdb_backend: fsspec
  fsspec_options: {}
```

Do not commit credentials. With no explicit S3 options, `s3fs`/botocore uses its normal
credential discovery chain (environment, profile and instance/container credentials). A custom
S3-compatible endpoint can be supplied through `client_kwargs.endpoint_url`. HTTP(S) retains TLS
verification. Its aiohttp session uses `trust_env=True`, so `HTTP_PROXY`, `HTTPS_PROXY` and
`NO_PROXY` are honoured; request headers can be supplied under `http.headers`.

HTTP and HTTPS share the `http` options key. Supported input schemes are `s3://`, `http://`,
`https://`, `file://` and ordinary local paths. Explicit Python path lists are supported by the
library functions. S3 globs are delegated to the registered filesystem. HTTP servers generally
cannot list wildcard URLs, so use one explicit URL or an explicit URL list for HTTP.

Spill directories, Parquet/CSV outputs, JSON reports, manifests and checksums remain local. A
remote URI in an output position is rejected instead of being passed through `Path` and mangled.

## Smoke tests

The default remains native:

```bash
ukcompany-accounts pivot --engine duckdb --duckdb-backend native \
  --long 'data/accounts/long/accounts-long-*.parquet' \
  --mode as_first_reported
```

An S3 input using fsspec:

```bash
ukcompany-accounts pivot --engine duckdb --duckdb-backend fsspec \
  --long 's3://my-bucket/accounts/accounts-long-*.parquet' \
  --mode as_first_reported
```

An HTTP PSC part (an HTTP snapshot with multiple parts should be passed as an explicit list through
`ukcompany.psc.loader.load_psc`):

```bash
ukcompany-psc load --duckdb-backend fsspec --no-data-governance \
  --parts 'https://example.org/psc-snapshot-2026-09-18_1of1.txt' \
  --snapshot-date 2026-09-18 --output-dir data/psc/remote-smoke
```

For already-built remote PSC Parquets:

```bash
ukcompany-psc features --duckdb-backend fsspec --snapshot-date 2026-09-18 \
  --records 's3://my-bucket/psc/psc_records.parquet' \
  --noc 's3://my-bucket/psc/psc_noc.parquet' \
  --output-dir data/psc/remote-features
```

In fsspec mode the connection is created with DuckDB's known-extension auto-install and autoload
settings disabled. Only already-installed/built-in JSON and Parquet capabilities are loaded;
`httpfs` is neither installed nor loaded. The code does not retry with another backend or download
the complete input after an error.

Parquet supports selective range reads when the server and filesystem do. NDJSON must be parsed
sequentially, and compressed archives may require a complete sequential read; fsspec cannot make
those formats selectively readable like Parquet. Actual transfer and performance also depend on
the server. The automated suite verifies an aiohttp/fsspec Parquet range read against a local
range-capable HTTP server. Live S3 credentials, private endpoints and internet behaviour are not
tested by that fixture.

## Scope kept local

The monthly snapshot loader, joins and validation/prospective-study paths deliberately remain
local-only. They discover local ZIP/CSV parts, verify manifests and SHA-256 hashes, or enforce
frozen-input identity before querying. Accepting a URI there would bypass rather than preserve
those controls. The PSC walkthrough is also local-only: it checks every consumed TXT against its
manifested ZIP before calling the loader, and its report-rendering subprocess reads only the local
outputs produced by that governed run. Hard-coded Phase-E comparison scripts, PSC site-asset
generation and the Kaggle staging guard remain local-corpus/pre-publication-directory checks.
