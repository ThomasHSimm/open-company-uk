"""Command-line interface for bulk accounts extraction and pivoting."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .backfill import DEFAULT_BASE_URL, parse_month, run_backfill
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
    "base_url": DEFAULT_BASE_URL,
    "keep_zips": False,
    "download_chunk_size": 8 * 1024 * 1024,
    "download_retries": 2,
    "download_backoff_seconds": 5.0,
    "download_timeout_seconds": 120.0,
    "coverage_report": "docs/accounts-coverage.md",
    "long_output": "data/accounts/accounts-long.parquet",
    "extraction_report": "docs/accounts-extraction.md",
    "column_map": "config/accounts-wide-columns.json",
    "wide_output": "data/accounts/accounts-wide.parquet",
    "wide_provenance_output": "data/accounts/accounts-wide-provenance.parquet",
    "member_histogram": "docs/accounts-member-frequency.csv",
    "reconciliation_output": "docs/accounts-component-reconciliation.csv",
    "qa_report": "docs/accounts-qa.md",
}


def load_accounts_settings(path: str | Path) -> dict[str, object]:
    values = dict(DEFAULTS)
    settings_path = Path(path)
    if settings_path.exists():
        raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        values.update(raw.get("accounts", {}))
    return values


def setting_path(value: object) -> Path:
    return Path(str(value)).expanduser()


def month_argument(value: str) -> tuple[int, int]:
    try:
        return parse_month(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def cmd_extract(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    archives = (
        [parse_archive(path) for path in args.archives]
        if args.archives
        else discover_archives(args.downloads or settings["downloads_dir"])
    )
    if not archives:
        raise SystemExit("no Accounts_Monthly_Data archives found")
    store = setting_path(args.store or settings["store_path"])
    output = setting_path(args.output or settings["long_output"])
    report = setting_path(args.report or settings["extraction_report"])
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
    mapping = load_column_map(str(args.column_map or settings["column_map"]))
    long_path = setting_path(args.long or settings["long_output"])
    wide = setting_path(args.output or settings["wide_output"])
    provenance = setting_path(args.provenance_output or settings["wide_provenance_output"])
    pivot_parquet(long_path, mapping, args.mode, wide, provenance)
    print(f"WIDE: {wide}")
    print(f"Provenance: {provenance}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    long_path = setting_path(args.long or settings["long_output"])
    histogram = setting_path(args.histogram or settings["member_histogram"])
    reconciliation = setting_path(args.reconciliation or settings["reconciliation_output"])
    report = setting_path(args.report or settings["qa_report"])
    write_qa(long_path, histogram, reconciliation, report)
    print(f"Member histogram: {histogram}")
    print(f"Reconciliation: {reconciliation}")
    print(f"QA report: {report}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    store = setting_path(args.store or settings["store_path"])
    downloads = setting_path(args.downloads or settings["downloads_dir"])
    coverage = setting_path(args.coverage_report or settings["coverage_report"])
    output = setting_path(args.output or settings["long_output"])
    extraction_report = setting_path(args.report or settings["extraction_report"])
    keep_zips = bool(settings["keep_zips"]) if args.keep_zips is None else args.keep_zips
    connection = connect_store(store)
    try:
        summary = run_backfill(
            connection,
            args.from_month,
            args.to_month,
            downloads=downloads,
            base_url=str(args.base_url or settings["base_url"]),
            keep_zips=keep_zips,
            limit_per_zip=args.limit_per_zip,
            chunk_size=int(settings["download_chunk_size"]),
            retries=int(settings["download_retries"]),
            backoff=float(settings["download_backoff_seconds"]),
            timeout=float(settings["download_timeout_seconds"]),
            report_output=coverage,
        )
        print("Exporting LONG Parquet...", flush=True)
        export_parquet(connection, output)
        extraction_report.parent.mkdir(parents=True, exist_ok=True)
        extraction_report.write_text(render_extraction_report(connection), encoding="utf-8")
    finally:
        connection.close()
    print(f"LONG: {output}")
    print(f"Extraction report: {extraction_report}")
    print(f"Coverage report: {coverage}")
    return int(summary.has_gaps)


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
    run = commands.add_parser("run", help="fetch, extract, then safely delete a month range")
    run.add_argument(
        "--from",
        dest="from_month",
        required=True,
        metavar="YYYY-MM",
        type=month_argument,
    )
    run.add_argument(
        "--to",
        dest="to_month",
        required=True,
        metavar="YYYY-MM",
        type=month_argument,
    )
    run.add_argument("--downloads")
    run.add_argument("--store")
    run.add_argument("--base-url")
    run.add_argument("--keep-zips", action=argparse.BooleanOptionalAction, default=None)
    run.add_argument("--limit-per-zip", type=int)
    run.add_argument("--coverage-report")
    run.add_argument("--output")
    run.add_argument("--report")
    run.set_defaults(func=cmd_run)
    pivot = commands.add_parser("pivot", help="create WIDE and cell provenance Parquets")
    pivot.add_argument("--long")
    pivot.add_argument(
        "--column-map",
        help="reviewed JSON map; defaults to accounts.column_map in settings",
    )
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
