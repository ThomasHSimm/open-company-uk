"""CLI for the basic-company snapshot pipeline (Handoff 08).

    ukcompany-snapshot refresh --month 2026-08   # download, verify, prune, load, row-count check
    ukcompany-snapshot features --month 2026-08  # per-company feature table (governed tier)

`refresh` mirrors the PSC `refresh`: download, verify checksums against the manifest, prune to
the retention policy (first snapshot of each month + latest), load, and check the row count
against the manifest. It fails loudly on a checksum or row-count mismatch and is idempotent.
The reference date for every age/overdue feature is the snapshot date (month-01), never today.

Config in config/settings.yaml under `snapshot:`.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import yaml

from ukcompany.cli import load_dotenv

from .archive import prune_archive, verify_manifest
from .download import download_snapshot
from .loader import SnapshotLoader
from .manifest import create_manifest, load_manifest, manifest_summary

DEFAULTS = {
    "downloads_dir": "data/snapshot",
    "manifest_path": "data/snapshot/{month}/manifest.json",
    "parts_glob": "data/snapshot/{month}/BasicCompanyData-{month}-01-part*_*.zip",
    "output_dir": "data/snapshot/{month}/{mode}",
    "data_governance": True,
    "duckdb_memory_gb": 8,
}


def load_snapshot_settings(path: str | Path) -> dict[str, object]:
    values = dict(DEFAULTS)
    settings_path = Path(path)
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        values.update(raw.get("snapshot", {}))
    return values


def setting_path(value: object) -> Path:
    return Path(str(value)).expanduser()


def cmd_refresh(args: argparse.Namespace) -> int:
    settings = load_snapshot_settings(args.settings)
    downloads_dir = setting_path(args.downloads_dir or settings["downloads_dir"])
    started = time.monotonic()

    if args.skip_download:
        if not args.month:
            raise SystemExit("--month is required with --skip-download")
        month = args.month
        print(f"[refresh] skipping download; using existing archive for {month}")
    else:
        snapshot = download_snapshot(downloads_dir, args.month)
        month = snapshot.month
        manifest_path = setting_path(str(settings["manifest_path"]).format(month=month))
        create_manifest(month, snapshot.paths, snapshot.parts, manifest_path)
        print(f"[refresh] downloaded {len(snapshot.paths)} part(s) for {month}")

    archive_dir = downloads_dir / month
    manifest_path = setting_path(str(settings["manifest_path"]).format(month=month))
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found at {manifest_path}; cannot verify checksums")

    problems = verify_manifest(manifest_path, archive_dir)
    if problems:
        raise SystemExit(f"[refresh] checksum verification FAILED: {problems}")
    print(f"[refresh] checksums verified against {manifest_path}")

    pruned = prune_archive(downloads_dir, dry_run=args.prune_dry_run)
    verb = "would remove" if args.prune_dry_run else "removed"
    print(f"[refresh] retention: keep {pruned['keep']}; {verb} {pruned['removed']}")

    # Load and reconcile the row count against the manifest (same lazy method the manifest
    # used), failing loudly on a mismatch.
    manifest = load_manifest(manifest_path)
    import polars as pl

    loaded_rows = SnapshotLoader(archive_dir).scan().select(pl.len()).collect().item()
    manifest_rows = manifest.get("total_rows")
    if manifest_rows is not None and loaded_rows != manifest_rows:
        raise SystemExit(
            f"[refresh] row-count check FAILED: loaded {loaded_rows:,} != manifest "
            f"{manifest_rows:,}"
        )
    elapsed = time.monotonic() - started
    print(manifest_summary(manifest))
    print(f"[refresh] rows loaded and reconciled: {loaded_rows:,}")
    print(f"[refresh] snapshot date (reference): {month}-01")
    print(f"[refresh] wall time: {elapsed:.1f}s")
    return 0


def cmd_features(args: argparse.Namespace) -> int:
    from .features import build_snapshot_features

    load_dotenv()  # harmless; keeps parity with other CLIs
    settings = load_snapshot_settings(args.settings)
    downloads_dir = setting_path(args.downloads_dir or settings["downloads_dir"])
    month = args.month
    parts_glob = str(
        args.parts or setting_path(str(settings["parts_glob"]).format(month=month))
    )
    data_governance = True if args.data_governance is None else args.data_governance
    mode = "governed" if data_governance else "ungoverned"
    output_dir = setting_path(
        args.output_dir
        or str(settings["output_dir"]).format(month=month, mode=f"features-{mode}")
    )
    _ = downloads_dir  # parts_glob already resolved from settings/month
    report = build_snapshot_features(
        parts_glob, output_dir, f"{month}-01",
        data_governance=data_governance,
        memory_limit_gb=args.duckdb_memory_gb or int(settings["duckdb_memory_gb"]),
    )
    print(f"tier: {report['tier']}  companies: {report['n_companies']:,}")
    print(f"snapshot date (reference): {report['snapshot_date']}")
    print(f"malformed rows (quarantined): {report['n_malformed_rows']}  "
          f"blank/other rows (allowed): {report['n_blank_or_other_rows']}")
    print(f"outputs: {report['outputs']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="config/settings.yaml")
    commands = parser.add_subparsers(dest="command", required=True)

    refresh = commands.add_parser(
        "refresh", help="download, verify, prune, load, row-count check (Task 1)"
    )
    refresh.add_argument("--month", help="YYYY-MM; required with --skip-download")
    refresh.add_argument("--downloads-dir")
    refresh.add_argument("--skip-download", action="store_true",
                         help="reuse an already-downloaded + manifested archive")
    refresh.add_argument("--prune-dry-run", action="store_true",
                         help="report the retention plan without deleting any month directories")
    refresh.set_defaults(func=cmd_refresh)

    features = commands.add_parser(
        "features", help="build the per-company snapshot feature table (Task 2)"
    )
    features.add_argument("--month", required=True, help="YYYY-MM")
    features.add_argument("--downloads-dir")
    features.add_argument("--parts", help="glob of snapshot part zips (default from settings)")
    features.add_argument("--output-dir")
    features.add_argument(
        "--data-governance", action=argparse.BooleanOptionalAction, default=None,
        help="governed tier (default True) drops exact-address concentration",
    )
    features.add_argument("--duckdb-memory-gb", type=int, default=None)
    features.set_defaults(func=cmd_features)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
