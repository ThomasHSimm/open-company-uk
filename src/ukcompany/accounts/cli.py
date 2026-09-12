"""Command-line interface for bulk accounts extraction and pivoting."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .extract import (
    connect_store,
    discover_archives,
    export_parquet,
    parse_archive,
    process_archive,
    render_extraction_report,
)
from .pivot import load_column_map, pivot_parquet
from .qa import write_qa

DEFAULTS = {
    "downloads_dir": "~/Downloads",
    "store_path": "data/accounts/accounts.sqlite",
    "long_output": "data/accounts/accounts-long.parquet",
    "extraction_report": "docs/accounts-extraction.md",
    "wide_output": "data/accounts/accounts-wide.parquet",
    "wide_provenance_output": "data/accounts/accounts-wide-provenance.parquet",
    "member_histogram": "docs/accounts-member-frequency.csv",
    "reconciliation_output": "docs/accounts-component-reconciliation.csv",
    "qa_report": "docs/accounts-qa.md",
}


def load_accounts_settings(path: str | Path) -> dict[str, str]:
    values = dict(DEFAULTS)
    settings_path = Path(path)
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        values.update(raw.get("accounts", {}))
    return values


def cmd_extract(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    archives = (
        [parse_archive(path) for path in args.archives]
        if args.archives
        else discover_archives(args.downloads or settings["downloads_dir"])
    )
    if not archives:
        raise SystemExit("no Accounts_Monthly_Data archives found")
    store = Path(args.store or settings["store_path"]).expanduser()
    output = Path(args.output or settings["long_output"]).expanduser()
    report = Path(args.report or settings["extraction_report"]).expanduser()
    connection = connect_store(store)
    try:
        for index, archive in enumerate(archives, 1):
            print(f"[{index}/{len(archives)}] {archive.name}", flush=True)
            process_archive(connection, archive, limit=args.limit_per_zip)
        print("Exporting LONG Parquet...", flush=True)
        export_parquet(connection, output)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_extraction_report(connection), encoding="utf-8")
    finally:
        connection.close()
    print(f"LONG: {output}")
    print(f"Report: {report}")
    return 0


def cmd_pivot(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    mapping = load_column_map(args.column_map)
    long_path = Path(args.long or settings["long_output"]).expanduser()
    wide = Path(args.output or settings["wide_output"]).expanduser()
    provenance = Path(
        args.provenance_output or settings["wide_provenance_output"]
    ).expanduser()
    pivot_parquet(long_path, mapping, args.mode, wide, provenance)
    print(f"WIDE: {wide}")
    print(f"Provenance: {provenance}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    long_path = Path(args.long or settings["long_output"]).expanduser()
    histogram = Path(args.histogram or settings["member_histogram"]).expanduser()
    reconciliation = Path(
        args.reconciliation or settings["reconciliation_output"]
    ).expanduser()
    report = Path(args.report or settings["qa_report"]).expanduser()
    write_qa(long_path, histogram, reconciliation, report)
    print(f"Member histogram: {histogram}")
    print(f"Reconciliation: {reconciliation}")
    print(f"QA report: {report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="config/settings.yaml")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="extract monthly ZIPs into LONG Parquet")
    extract.add_argument("archives", nargs="*", help="ZIP paths; otherwise discover downloads")
    extract.add_argument("--downloads")
    extract.add_argument("--store")
    extract.add_argument("--output")
    extract.add_argument("--report")
    extract.add_argument("--limit-per-zip", type=int)
    extract.set_defaults(func=cmd_extract)
    pivot = commands.add_parser("pivot", help="create WIDE and cell provenance Parquets")
    pivot.add_argument("--long")
    pivot.add_argument("--column-map", required=True)
    pivot.add_argument("--mode", choices=("latest", "as_first_reported"), required=True)
    pivot.add_argument("--output")
    pivot.add_argument("--provenance-output")
    pivot.set_defaults(func=cmd_pivot)
    qa = commands.add_parser("qa", help="write member histogram and reconciliation QA")
    qa.add_argument("--long")
    qa.add_argument("--histogram")
    qa.add_argument("--reconciliation")
    qa.add_argument("--report")
    qa.set_defaults(func=cmd_qa)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
