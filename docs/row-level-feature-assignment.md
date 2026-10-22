# Assigning point-in-time features to observation rows

The population builders remain available:

- `build_accounts_features(...)` builds one accounts table for a single reference month.
- `build_psc_features(...)` builds one PSC table for a single source snapshot.

For modelling data in which every row can have a different company and reference date, use the
assignment functions instead. They return a copy of the input pandas DataFrame with feature and
provenance columns appended. Input order, duplicate rows and duplicate DataFrame indices are
preserved.

## Accounts

```python
import pandas as pd

from ukcompany.accounts import assign_accounts_features

observations = pd.DataFrame(
    {
        "company_number": ["00000001", "SC123456"],
        "date": ["2024-01-15", "2026-06-30"],
        "target": [0, 1],
    }
)

enriched = assign_accounts_features(
    observations,
    "s3://research-data/accounts-wide.parquet",
    register_feature_snapshots={
        "2024-01-01": "s3://research-data/register/2024-01/features.parquet",
        "2026-06-01": "s3://research-data/register/2026-06/features.parquet",
    },
    memory_limit_gb=8,
    spill_dir="/opt/ml/tmp/duckdb",
)
```

The default `availability_policy="previous_complete_month"` gives each row its own accounts
cutoff: an observation on 15 January 2024 can use WIDE rows available by `202312`. This is the
conservative choice because WIDE availability is monthly, not daily. Use
`availability_policy="same_month"` only when a row date represents an end-of-month boundary.
`accounts_reference_yyyymm` records the cutoff used.

`register_feature_snapshots` is optional. If supplied, each row uses the latest register feature
snapshot dated on or before its observation date, and `accounts_category` is joined from that exact
snapshot. If it is omitted, `accounts_category` and
`accounts_register_snapshot_date_used` are null. The function never substitutes a present-day
register category for a historical observation.

The WIDE query is set-based: it ranks eligible accounts periods separately for every input row in
one DuckDB query. It does not call `build_accounts_features` once per month or once per company.

## PSC

First build and retain a company feature Parquet for every PSC snapshot that may be selected. Then
pass the dated catalog explicitly:

```python
from ukcompany.psc import assign_psc_features

enriched = assign_psc_features(
    observations,
    {
        "2026-05-29": "s3://research-data/psc/2026-05-29/psc_company_features.parquet",
        "2026-06-26": "s3://research-data/psc/2026-06-26/psc_company_features.parquet",
    },
    memory_limit_gb=8,
    spill_dir="/opt/ml/tmp/duckdb",
)
```

Each row selects the latest supplied snapshot dated on or before its reference date. Snapshot
selection happens before the company join. Consequently, if a company is absent from the selected
snapshot, its features remain null; the function does not search an older snapshot for that
company. `has_psc_snapshot`, `has_psc`, `psc_snapshot_date_used` and
`psc_snapshot_age_days` distinguish snapshot coverage from company presence.

Rows before the first supplied PSC snapshot have no selected snapshot and null PSC features. A
current PSC snapshot cannot safely reconstruct historical state merely because its records contain
old `notified_on` or `ceased_on` dates: corrections and deleted or overwritten state would still be
unknown.

## Column names, remote access and outputs

If the input columns are not named `company_number` and `date`, pass
`company_number_column=...` and `date_column=...`. Company values are compared after trimming and
uppercasing; dates must be parseable and non-null. Existing columns that would collide with an
appended feature are rejected rather than overwritten.

Both functions accept local paths or S3/HTTP inputs through the existing DuckDB backend. In an
offline SageMaker environment with S3 access through a VPC endpoint, install the `remote` and
`analysis` dependencies in the image and let the default backend select fsspec for `s3://` paths.
Pass `fsspec_options` only for nonstandard filesystem configuration. Spill remains local.

The returned pandas DataFrame can be written wherever the caller chooses. For network-isolated
SageMaker jobs, write it under the configured local model/job output directory and let SageMaker
upload that directory. For jobs with direct S3 access, pandas, PyArrow or another application-level
writer can save the final table to S3; the assignment functions deliberately do not prescribe an
output location.
