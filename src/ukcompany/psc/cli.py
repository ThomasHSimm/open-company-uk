"""CLI for the PSC snapshot pipeline: fetch (Task A), load (Task B), refresh (Handoff 07).

    ukcompany-psc fetch                 # download today's published PSC snapshot, keep zips
    ukcompany-psc load --parts '...'    # load NDJSON parts into Parquet tables
    ukcompany-psc refresh               # the whole repeatable pipeline, end to end

`refresh` is the repeatable one-shot: it downloads, verifies checksums against the manifest,
prunes the archive to the D1 retention policy (first-of-month + latest), extracts the zips,
loads, and runs the written-file + totals-line reconciliation checks. It FAILS LOUDLY if a
checksum or the totals line does not reconcile, and is idempotent (re-running skips an
already-correct download/extract and overwrites the Parquet outputs in place).

Config (paths, defaults) in config/settings.yaml under `psc:`. The `--data-governance` /
`--no-data-governance` default comes from settings too (brief: default True). Scheduling
this from cron is out of scope here — see the brief's Task A point 4.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import yaml

from ukcompany.cli import load_dotenv

from .archive import archive_sizes, extract_parts, prune_archive, verify_manifest
from .download import download_snapshot
from .loader import load_psc
from .manifest import create_manifest, manifest_summary

DEFAULTS = {
    "downloads_dir": "~/Downloads/psc",
    "manifest_path": "data/psc/{date}/manifest.json",
    "parts_glob": "data/psc/{date}/psc-snapshot-{date}_*of*.txt",
    "output_dir": "data/psc/{date}/{mode}",
    "data_governance": True,
    "duckdb_memory_gb": 8,
}


def load_psc_settings(path: str | Path) -> dict[str, object]:
    values = dict(DEFAULTS)
    settings_path = Path(path)
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        values.update(raw.get("psc", {}))
    return values


def setting_path(value: object) -> Path:
    return Path(str(value)).expanduser()


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = load_psc_settings(args.settings)
    downloads_dir = setting_path(args.downloads_dir or settings["downloads_dir"])
    snapshot = download_snapshot(downloads_dir, args.date)
    manifest_path = setting_path(
        str(settings["manifest_path"]).format(date=snapshot.date)
    )
    manifest = create_manifest(snapshot.date, snapshot.paths, snapshot.parts, manifest_path)
    print(manifest_summary(manifest))
    print(f"Manifest: {manifest_path}")
    print(f"Kept {len(snapshot.paths)} zip(s) in {downloads_dir / snapshot.date}")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    load_dotenv()
    settings = load_psc_settings(args.settings)
    data_governance = (
        bool(settings["data_governance"]) if args.data_governance is None else args.data_governance
    )
    person_key_secret = os.environ.get("PSC_PERSON_KEY_SECRET")
    if data_governance and not person_key_secret:
        raise SystemExit(
            "PSC_PERSON_KEY_SECRET is not set (add it to .env) — required whenever "
            "--data-governance is on, since person_key cannot be computed without it"
        )
    mode = "governed" if data_governance else "private"
    output_dir = setting_path(
        args.output_dir
        or str(settings["output_dir"]).format(date=args.snapshot_date, mode=mode)
    )
    report = load_psc(
        args.parts,
        output_dir,
        args.snapshot_date,
        data_governance=data_governance,
        person_key_secret=person_key_secret,
        memory_limit_gb=args.duckdb_memory_gb or int(settings["duckdb_memory_gb"]),
    )
    print(f"snapshot date: {report['snapshot_date']}")
    print(f"data_governance: {report['data_governance']}")
    print(f"lines: {report['n_lines']:,}  bad lines: {report['n_bad_lines']:,}")
    print(f"categories sum to lines: {report['categories_sum_to_lines']}")
    print(f"category counts: {report['category_counts']}")
    print(f"outputs: {report['outputs']}")
    return 0 if report["categories_sum_to_lines"] else 1


def cmd_refresh(args: argparse.Namespace) -> int:
    """The repeatable end-to-end pipeline: download -> verify -> prune (D1) -> extract ->
    load -> written-file + totals reconciliation. Fails loudly on a checksum or totals
    mismatch; idempotent."""
    load_dotenv()
    settings = load_psc_settings(args.settings)
    downloads_dir = setting_path(args.downloads_dir or settings["downloads_dir"])
    data_governance = (
        bool(settings["data_governance"]) if args.data_governance is None else args.data_governance
    )
    person_key_secret = os.environ.get("PSC_PERSON_KEY_SECRET")
    if data_governance and not person_key_secret:
        raise SystemExit(
            "PSC_PERSON_KEY_SECRET is not set (add it to .env) — required whenever "
            "--data-governance is on, since person_key cannot be computed without it"
        )
    started = time.monotonic()

    # 1. Download (or reuse an already-downloaded archive with --skip-download).
    if args.skip_download:
        if not args.snapshot_date:
            raise SystemExit("--snapshot-date is required with --skip-download")
        date = args.snapshot_date
        print(f"[refresh] skipping download; using existing archive for {date}")
    else:
        snapshot = download_snapshot(downloads_dir, args.snapshot_date)
        date = snapshot.date
        manifest_path = setting_path(str(settings["manifest_path"]).format(date=date))
        create_manifest(date, snapshot.paths, snapshot.parts, manifest_path)
        print(f"[refresh] downloaded {len(snapshot.paths)} part(s) for {date}")

    archive_dir = downloads_dir / date
    manifest_path = setting_path(str(settings["manifest_path"]).format(date=date))

    # 2. Verify checksums against the manifest — fail loudly on any problem.
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found at {manifest_path}; cannot verify checksums")
    problems = verify_manifest(manifest_path, archive_dir)
    if problems:
        raise SystemExit(f"[refresh] checksum verification FAILED: {problems}")
    print(f"[refresh] checksums verified against {manifest_path}")

    # 3. Prune the archive to the D1 retention policy.
    pruned = prune_archive(downloads_dir, dry_run=args.prune_dry_run)
    verb = "would remove" if args.prune_dry_run else "removed"
    print(f"[refresh] retention: keep {pruned['keep']}; {verb} {pruned['removed']}")

    # 4. Extract the zips to NDJSON text (idempotent).
    extracted = extract_parts(archive_dir)
    print(f"[refresh] extracted/confirmed {len(extracted)} part(s) in {archive_dir}")
    sizes = archive_sizes(archive_dir)

    # 5. Load + reconcile. load_psc raises on a totals-line or written-file mismatch.
    mode = "governed" if data_governance else "private"
    output_dir = setting_path(
        args.output_dir or str(settings["output_dir"]).format(date=date, mode=mode)
    )
    parts_glob = str(archive_dir / f"psc-snapshot-{date}_*of*.txt")
    report = load_psc(
        parts_glob,
        output_dir,
        date,
        data_governance=data_governance,
        person_key_secret=person_key_secret,
        memory_limit_gb=args.duckdb_memory_gb or int(settings["duckdb_memory_gb"]),
    )
    elapsed = time.monotonic() - started

    print(f"[refresh] snapshot {date}  data_governance={report['data_governance']}")
    print(f"[refresh] lines {report['n_lines']:,}  bad {report['n_bad_lines']:,}")
    print(f"[refresh] categories sum to lines: {report['categories_sum_to_lines']}")
    print(f"[refresh] totals reconciliation: {report.get('totals_reconciliation')}")
    print(
        f"[refresh] archive: {sizes['n_zip_parts']} zip ({sizes['zipped_bytes']:,} B) "
        f"-> {sizes['n_txt_parts']} txt ({sizes['extracted_bytes']:,} B)"
    )
    print(f"[refresh] outputs: {report['outputs']}")
    print(f"[refresh] wall time: {elapsed:.1f}s")
    return 0 if report["categories_sum_to_lines"] else 1


def cmd_features(args: argparse.Namespace) -> int:
    """Build the per-company PSC feature table from a GOVERNED load (which carries the
    pseudonymous person_key). The tier is chosen by --data-governance: governed drops the
    companies-per-person band; private keeps it."""
    from .features import build_psc_features

    settings = load_psc_settings(args.settings)
    load_dir = setting_path(
        args.load_dir
        or str(settings["output_dir"]).format(date=args.snapshot_date, mode="governed")
    )
    records = load_dir / "psc_records.parquet"
    noc = load_dir / "psc_noc.parquet"
    data_governance = True if args.data_governance is None else args.data_governance
    mode = "governed" if data_governance else "private"
    output_dir = setting_path(
        args.output_dir
        or str(settings["output_dir"]).format(date=args.snapshot_date, mode=f"features-{mode}")
    )
    report = build_psc_features(
        records, noc, output_dir, args.snapshot_date,
        data_governance=data_governance,
        memory_limit_gb=args.duckdb_memory_gb or int(settings["duckdb_memory_gb"]),
    )
    print(f"tier: {report['tier']}  companies: {report['n_companies']:,}")
    print(f"information_state: {report['information_state_counts']}")
    print(f"distinct nature sets: {report['distinct_nature_sets']:,}  "
          f"distinct corporate regnos: {report['distinct_corporate_regnos']:,}")
    print(f"outputs: {report['outputs']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="config/settings.yaml")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser(
        "fetch", help="download today's published PSC snapshot (Task A); zips are kept"
    )
    fetch.add_argument("--downloads-dir")
    fetch.add_argument("--date", help="YYYY-MM-DD; default is whatever CH currently serves")
    fetch.set_defaults(func=cmd_fetch)

    load = commands.add_parser("load", help="load NDJSON parts into Parquet tables (Task B)")
    load.add_argument("--parts", required=True, help="glob of psc-snapshot part files")
    load.add_argument("--snapshot-date", required=True, help="YYYY-MM-DD")
    load.add_argument("--output-dir")
    load.add_argument(
        "--data-governance", action=argparse.BooleanOptionalAction, default=None,
        help="default True (see settings.yaml); requires PSC_PERSON_KEY_SECRET in .env",
    )
    load.add_argument("--duckdb-memory-gb", type=int, default=None)
    load.set_defaults(func=cmd_load)

    refresh = commands.add_parser(
        "refresh",
        help="end-to-end repeatable pipeline: download, verify, prune (D1), extract, load",
    )
    refresh.add_argument("--snapshot-date", help="YYYY-MM-DD; required with --skip-download")
    refresh.add_argument("--downloads-dir")
    refresh.add_argument("--output-dir")
    refresh.add_argument(
        "--skip-download", action="store_true",
        help="reuse an already-downloaded + manifested archive instead of fetching",
    )
    refresh.add_argument(
        "--prune-dry-run", action="store_true",
        help="report the D1 retention plan without deleting any snapshot directories",
    )
    refresh.add_argument(
        "--data-governance", action=argparse.BooleanOptionalAction, default=None,
        help="default True (see settings.yaml); requires PSC_PERSON_KEY_SECRET in .env",
    )
    refresh.add_argument("--duckdb-memory-gb", type=int, default=None)
    refresh.set_defaults(func=cmd_refresh)

    features = commands.add_parser(
        "features",
        help="build the per-company PSC feature table from a governed load (Task 2)",
    )
    features.add_argument("--snapshot-date", required=True, help="YYYY-MM-DD")
    features.add_argument("--load-dir", help="governed load dir (default from settings)")
    features.add_argument("--output-dir")
    features.add_argument(
        "--data-governance", action=argparse.BooleanOptionalAction, default=None,
        help="governed tier (default True) drops the companies-per-person band",
    )
    features.add_argument("--duckdb-memory-gb", type=int, default=None)
    features.set_defaults(func=cmd_features)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
