"""CLI for the PSC snapshot pipeline: fetch (Task A) and load (Task B).

    ukcompany-psc fetch                 # download today's published PSC snapshot, keep zips
    ukcompany-psc load --parts '...'    # load NDJSON parts into Parquet tables

Config (paths, defaults) in config/settings.yaml under `psc:`. The `--data-governance` /
`--no-data-governance` default comes from settings too (brief: default True). Scheduling
this from cron is out of scope here — see the brief's Task A point 4.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from ukcompany.cli import load_dotenv

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

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
