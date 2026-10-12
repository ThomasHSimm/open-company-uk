# Data retention: what is irreplaceable, what is not

This note records which locally held snapshots can never be re-acquired and which
can, and recommends what to keep and back up when the project stops active
collection. It is a companion to `ukcompany status`, which prints the live
inventory from disk.

Run the inventory at any time:

```bash
ukcompany status
```

## Why some snapshots cannot be re-downloaded

Companies House publishes each bulk product as a **current snapshot only**. There
is no historical archive of the register (`BasicCompanyData`) product, and the
persons-with-significant-control (PSC) snapshot is a file regenerated each day
with no archive of previous days. The moment a register month or a PSC day is not
downloaded, that state is lost permanently — the API gives current state, not the
population as it stood on a past date. The monthly bulk **accounts** archives are
the exception: Companies House keeps the trailing run of monthly accounts archives
available, so those months can be downloaded again.

## Inventory held locally (as of 2026-10-12)

### Register (`BasicCompanyData`) — IRREPLACEABLE

| Month | Snapshot date | Parts | Rows | Downloaded |
|---|---|---|---|---|
| 2026-08 | 2026-08-01 | 7 | 5,695,466 | 2026-08-06 |
| 2026-10 | 2026-10-01 | 7 | 5,704,712 | 2026-10-05 |

No September register snapshot was taken. Each month that is not on disk here is
gone; neither month can be re-downloaded.

### PSC daily snapshot — IRREPLACEABLE

| Snapshot | Parts | Downloaded | Notes |
|---|---|---|---|
| 2026-09-18 | — | — | stage1 + governed/private derived parquet; no own manifest |
| 2026-09-25 | 32 | 2026-09-25 | manifested raw snapshot; used in the governed join |

Because the PSC file is daily, the first-of-a-month snapshot can only be captured
on that day. The earliest PSC snapshot held is **2026-09-18**; there is no
first-of-September or first-of-October PSC snapshot, and none can now be obtained.

### Accounts (monthly bulk iXBRL archives) — RE-DOWNLOADABLE

- Extracted long-table months on disk: **153**, spanning **2014-01 through
  2026-09** (across `data/accounts/long`, `data/accounts/v2/long`, and
  `data/accounts/v2-internal-202609/long`).
- Raw monthly ZIPs on disk: **1** (`Accounts_Monthly_Data-September2026.zip`).
  The pipeline deletes raw ZIPs after extraction by default (`accounts.keep_zips:
  false`); it bounds raw-ZIP storage to roughly one archive at a time.

The raw archives are re-downloadable from Companies House, so the accounts source
is recoverable. What is *not* cheap to recreate is the extracted/derived product:
the 153 monthly long tables and the WIDE/provenance tables represent substantial
parse-and-reconcile compute (days of processing), not a quick re-download.

## Recommendation when the project stops

Priority order for a backup, highest first:

1. **Register raw snapshots and manifests** (`data/snapshot/2026-08`,
   `data/snapshot/2026-10`; ~6.6 GB). Irreplaceable; small. Back up the raw ZIPs
   **and** `manifest.json` so provenance and hashes travel with the data.
2. **PSC raw snapshot and manifest** (`data/psc/2026-09-25`, plus the derived
   `2026-09-18` directories; ~13 GB). Irreplaceable. The raw `.txt` parts matter
   most; keep the manifest with them.
3. **The frozen governed join and its manifest**
   (`data/join/v1-internal-202609/`; ~0.4 GB). This is the prospective-study
   baseline (see `docs/prospective-study-plan.md`); its integrity depends on the
   two irreplaceable snapshots above, so back it up alongside them. Its hash is
   recorded in the study plan.
4. **The WIDE accounts product.** The published Kaggle v2 dataset already serves
   as an off-site backup of the WIDE table; keeping a local copy of
   `data/accounts/v2/accounts-wide-*.parquet` is a convenience, not a necessity.

Safe to drop to reclaim space: the raw accounts ZIP(s) (re-downloadable); the
extracted `extracted/` register CSVs (re-derivable from the raw ZIPs); DuckDB
spill directories and `.accounts-scratch`. The 80 GB accounts tree is the largest
consumer but the least at risk, because its source is republished upstream.

**One line to remember:** if a fire alarm went off, the register and PSC raw
snapshots are the only things that could never be recreated — everything else is
either re-downloadable from Companies House or re-derivable from those snapshots.
