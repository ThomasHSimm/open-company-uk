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

DEFAULTS = {
    "downloads_dir": "~/Downloads",
    "store_path": "data/accounts/accounts.sqlite",
    "long_output": "data/accounts/accounts-long.parquet",
    "extraction_report": "docs/accounts-extraction.md",
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
