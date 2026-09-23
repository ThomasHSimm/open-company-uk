"""Command-line interface for bulk accounts extraction and pivoting."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .backfill import DEFAULT_BASE_URL, parse_month, run_backfill
from .extract import (
    archive_recorded_complete,
    connect_store,
    discover_archives,
    export_archive_parquet,
    export_completed_archives,
    export_manifest,
    export_parquet,
    parse_archive,
    process_archive,
    render_extraction_report,
    render_verification_report,
    verify_all_monthly_parquets,
)
from .inventory import write_concept_inventory, write_concept_inventory_from_parts
from .pivot import load_column_map, pivot_parquet, track_peak_rss
from .qa import render_restatement_rate_report, restatement_rate_over_parts, write_qa

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
    "scope": "all",
    "kinds": "all",
    "monthly_output_dir": "data/accounts/long",
    "long_input": "data/accounts/long/accounts-long-*.parquet",
    "extraction_report": "docs/accounts-extraction.md",
    "concept_inventory_csv": "docs/accounts-concept-inventory.csv",
    "concept_inventory_report": "docs/accounts-concept-inventory.md",
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


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def month_argument(value: str) -> tuple[int, int]:
    try:
        return parse_month(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def configured_scope(argument: str | None, settings: dict[str, object]) -> str | list[str]:
    value = argument if argument is not None else settings["scope"]
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)


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
    output_dir = setting_path(args.output_dir or settings["monthly_output_dir"])
    report = setting_path(args.report or settings["extraction_report"])
    scope = configured_scope(args.scope, settings)
    kinds = str(args.kinds or settings["kinds"])
    connection = connect_store(store)
    try:
        for index, archive in enumerate(archives, 1):
            print(f"[{index}/{len(archives)}] {archive.name}", flush=True)
            process_archive(
                connection,
                archive,
                limit=args.limit_per_zip,
                scope=scope,
                kinds=kinds,
            )
            if archive_recorded_complete(
                connection, archive.name, scope=scope, kinds=kinds
            ):
                export_archive_parquet(
                    connection,
                    archive.name,
                    output_dir,
                    scope=scope,
                    kinds=kinds,
                )
        if args.monolithic_output:
            print("Exporting opt-in monolithic LONG Parquet...", flush=True)
            export_parquet(connection, setting_path(args.monolithic_output))
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_extraction_report(connection), encoding="utf-8")
    finally:
        connection.close()
    print(f"Monthly LONG directory: {output_dir}")
    if args.monolithic_output:
        print(f"Monolithic LONG: {setting_path(args.monolithic_output)}")
    print(f"Report: {report}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    store = setting_path(args.store or settings["store_path"])
    output_dir = setting_path(args.output_dir or settings["monthly_output_dir"])
    report = setting_path(args.report or "docs/accounts-verification.md")
    connection = connect_store(store)
    try:
        results = verify_all_monthly_parquets(connection, output_dir)
    finally:
        connection.close()
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_verification_report(results), encoding="utf-8")
    print(f"Archives checked: {len(results):,}")
    print(f"Passed: {sum(result.ok for result in results):,}")
    print(f"Report: {report}")
    return int(any(not result.ok for result in results))


def cmd_export_manifest(args: argparse.Namespace) -> int:
    """Split the small `processed_archives` manifest out of a store, e.g. before deleting
    it or before switching the remaining run to --disposable-store."""
    settings = load_accounts_settings(args.settings)
    source_path = setting_path(args.source or settings["store_path"])
    destination_path = setting_path(args.destination)
    source = connect_store(source_path)
    destination = connect_store(destination_path)
    try:
        copied = export_manifest(source, destination)
    finally:
        source.close()
        destination.close()
    print(f"Manifest rows copied: {copied:,}")
    print(f"Destination: {destination_path}")
    return 0


def cmd_pivot(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    mapping = load_column_map(str(args.column_map or settings["column_map"]))
    long_path = setting_path(args.long or settings["long_input"])
    wide = setting_path(args.output or settings["wide_output"])
    provenance = setting_path(args.provenance_output or settings["wide_provenance_output"])
    if args.engine == "duckdb":
        from .ooc import pivot_duckdb

        with track_peak_rss() as peak_fn:
            pivot_duckdb(
                long_path,
                mapping,
                args.mode,
                wide,
                provenance,
                memory_limit_gb=args.duckdb_memory_gb,
            )
        peak = peak_fn()
    else:
        peak = pivot_parquet(long_path, mapping, args.mode, wide, provenance)
    print(f"WIDE: {wide}")
    print(f"Provenance: {provenance}")
    print(f"Peak memory: {format_bytes(peak)}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    """Member histogram and total/component reconciliation, via the per-file Polars pass
    (--engine polars) or an out-of-core DuckDB group-by (--engine duckdb, required at
    full-history scale — the Polars pass OOM'd at a 25 GB cgroup cap over 152 archives)."""
    settings = load_accounts_settings(args.settings)
    long_path = setting_path(args.long or settings["long_input"])
    histogram = setting_path(args.histogram or settings["member_histogram"])
    reconciliation = setting_path(args.reconciliation or settings["reconciliation_output"])
    report = setting_path(args.report or settings["qa_report"])
    if args.engine == "duckdb":
        from .ooc import write_qa_duckdb

        with track_peak_rss() as peak_fn:
            write_qa_duckdb(
                long_path, histogram, reconciliation, report,
                memory_limit_gb=args.duckdb_memory_gb,
            )
        peak = peak_fn()
    else:
        peak = write_qa(long_path, histogram, reconciliation, report)
    print(f"Member histogram: {histogram}")
    print(f"Reconciliation: {reconciliation}")
    print(f"QA report: {report}")
    print(f"Peak memory: {format_bytes(peak)}")
    return 0


def cmd_restatement(args: argparse.Namespace) -> int:
    """Decision 6: restatement rate over a CONTINUOUS month range, via a running tally
    (--engine python) or an out-of-core DuckDB window function (--engine duckdb, required
    at full-history scale — the Python dict tally needed 17.8 GB over 24 months alone)."""
    report_output = setting_path(args.report)
    with track_peak_rss() as peak:
        if args.engine == "duckdb":
            from .ooc import restatement_rate_duckdb

            result = restatement_rate_duckdb(
                args.long, scope_label=args.scope_label, memory_limit_gb=args.duckdb_memory_gb
            )
        else:
            result = restatement_rate_over_parts(args.long, scope_label=args.scope_label)
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(render_restatement_rate_report(result), encoding="utf-8")
    print(f"Restatement report: {report_output}")
    print(
        f"Disagreement rate: {result.disagreement_rate:.2%} of "
        f"{result.keys_repeated:,} repeated keys"
    )
    print(f"Peak memory: {format_bytes(peak())}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    store = setting_path(args.store or settings["store_path"])
    downloads = setting_path(args.downloads or settings["downloads_dir"])
    coverage = setting_path(args.coverage_report or settings["coverage_report"])
    output_dir = setting_path(args.output_dir or settings["monthly_output_dir"])
    extraction_report = setting_path(args.report or settings["extraction_report"])
    keep_zips = bool(settings["keep_zips"]) if args.keep_zips is None else args.keep_zips
    scope = configured_scope(args.scope, settings)
    kinds = str(args.kinds or settings["kinds"])
    connection = connect_store(store)
    try:
        summary = run_backfill(
            connection,
            args.from_month,
            args.to_month,
            downloads=downloads,
            output_dir=output_dir,
            base_url=str(args.base_url or settings["base_url"]),
            keep_zips=keep_zips,
            limit_per_zip=args.limit_per_zip,
            chunk_size=int(settings["download_chunk_size"]),
            retries=int(settings["download_retries"]),
            backoff=float(settings["download_backoff_seconds"]),
            timeout=float(settings["download_timeout_seconds"]),
            report_output=coverage,
            scope=scope,
            kinds=kinds,
            disposable_store=args.disposable_store,
        )
        if args.monolithic_output:
            print("Exporting opt-in monolithic LONG Parquet...", flush=True)
            export_parquet(connection, setting_path(args.monolithic_output))
        extraction_report.parent.mkdir(parents=True, exist_ok=True)
        extraction_report.write_text(render_extraction_report(connection), encoding="utf-8")
    finally:
        connection.close()
    print(f"Monthly LONG directory: {output_dir}")
    if args.monolithic_output:
        print(f"Monolithic LONG: {setting_path(args.monolithic_output)}")
    print(f"Extraction report: {extraction_report}")
    if args.disposable_store:
        print(
            "Note: --disposable-store means the store holds manifest rows only; "
            "the extraction report's observation-level stats are not populated. "
            "Use `ukcompany-accounts inventory` (reads --long) for full-scale stats."
        )
    print(f"Coverage report: {coverage}")
    return int(summary.has_gaps)


def cmd_export(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    store = setting_path(args.store or settings["store_path"])
    output_dir = setting_path(args.output_dir or settings["monthly_output_dir"])
    scope = configured_scope(args.scope, settings)
    kinds = str(args.kinds or settings["kinds"])
    connection = connect_store(store)
    try:
        outputs = export_completed_archives(
            connection,
            output_dir,
            start=args.from_month,
            end=args.to_month,
            scope=scope,
            kinds=kinds,
        )
        if args.monolithic_output:
            export_parquet(connection, setting_path(args.monolithic_output))
    finally:
        connection.close()
    print(f"Monthly Parquets written: {len(outputs):,}")
    print(f"Monthly LONG directory: {output_dir}")
    if args.monolithic_output:
        print(f"Monolithic LONG: {setting_path(args.monolithic_output)}")
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    settings = load_accounts_settings(args.settings)
    csv_output = setting_path(args.csv or settings["concept_inventory_csv"])
    report_output = setting_path(args.report or settings["concept_inventory_report"])
    if args.store:
        # Opt-in path for anyone who kept a monolithic store (see Decision 2); this never
        # requires touching Parquets and is unchanged from the pre-streaming behaviour.
        connection = connect_store(setting_path(args.store))
        try:
            inventory = write_concept_inventory(connection, csv_output, report_output)
        finally:
            connection.close()
        peak = None
    else:
        # Default: read the archived Parquets directly, so inventory works even after a
        # disposable-store run has discarded the scratch database (see pivot/pivot_long_over_parts).
        long_path = setting_path(args.long or settings["long_input"])
        inventory, peak = write_concept_inventory_from_parts(long_path, csv_output, report_output)
    print(f"Concepts inventoried: {len(inventory.rows):,}")
    print(f"Concept inventory CSV: {csv_output}")
    print(f"Concept inventory report: {report_output}")
    if peak is not None:
        print(f"Peak memory: {format_bytes(peak)}")
    return int(
        bool(
            inventory.audit.non_numeric_coercions
            or inventory.audit.numeric_unit_gaps
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="config/settings.yaml")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="extract ZIPs into per-month LONG Parquets")
    extract.add_argument("archives", nargs="*", help="ZIP paths; otherwise discover downloads")
    extract.add_argument("--downloads")
    extract.add_argument("--store")
    extract.add_argument("--output-dir")
    extract.add_argument("--monolithic-output")
    extract.add_argument("--report")
    extract.add_argument("--limit-per-zip", type=int)
    extract.add_argument("--scope", help="all or a comma-separated local-name list")
    extract.add_argument("--kinds", choices=("all", "numeric-only"))
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
    run.add_argument("--output-dir")
    run.add_argument("--monolithic-output")
    run.add_argument("--report")
    run.add_argument("--scope", help="all or a comma-separated local-name list")
    run.add_argument("--kinds", choices=("all", "numeric-only"))
    run.add_argument(
        "--disposable-store",
        action="store_true",
        help="extract each month into a throwaway working store instead of one monolith "
        "(recommended for full-history runs; see Decision 2 in accounts-backfill.md)",
    )
    run.set_defaults(func=cmd_run)
    export = commands.add_parser("export", help="rewrite completed per-month Parquets")
    export.add_argument("--store")
    export.add_argument("--output-dir")
    export.add_argument("--from", dest="from_month", metavar="YYYY-MM", type=month_argument)
    export.add_argument("--to", dest="to_month", metavar="YYYY-MM", type=month_argument)
    export.add_argument("--monolithic-output")
    export.add_argument("--scope", help="all or a comma-separated local-name list")
    export.add_argument("--kinds", choices=("all", "numeric-only"))
    export.set_defaults(func=cmd_export)
    verify = commands.add_parser(
        "verify", help="check manifest observation counts against archived Parquet row counts"
    )
    verify.add_argument("--store")
    verify.add_argument("--output-dir")
    verify.add_argument("--report")
    verify.set_defaults(func=cmd_verify)
    export_manifest_parser = commands.add_parser(
        "export-manifest",
        help="copy the small processed_archives manifest out of a store (e.g. before "
        "deleting it, or before switching the rest of a run to --disposable-store)",
    )
    export_manifest_parser.add_argument("--source", help="store to read from; default store_path")
    export_manifest_parser.add_argument("--destination", required=True)
    export_manifest_parser.set_defaults(func=cmd_export_manifest)
    inventory = commands.add_parser(
        "inventory", help="write the Stage 1 concept dictionary and read-correctness audit"
    )
    inventory.add_argument("--long", help="archived Parquet glob; default source")
    inventory.add_argument(
        "--store", help="opt-in: read a monolithic SQLite store instead of --long"
    )
    inventory.add_argument("--csv")
    inventory.add_argument("--report")
    inventory.set_defaults(func=cmd_inventory)
    pivot = commands.add_parser("pivot", help="create WIDE and cell provenance Parquets")
    pivot.add_argument("--long")
    pivot.add_argument(
        "--column-map",
        help="reviewed JSON map; defaults to accounts.column_map in settings",
    )
    pivot.add_argument("--mode", choices=("latest", "as_first_reported"), required=True)
    pivot.add_argument("--output")
    pivot.add_argument("--provenance-output")
    pivot.add_argument(
        "--engine",
        choices=("polars", "duckdb"),
        default="polars",
        help="'duckdb' is out-of-core and required at full-history scale; "
        "'polars' (default) matches prior tested behaviour at sample scale",
    )
    pivot.add_argument("--duckdb-memory-gb", type=int, default=8)
    pivot.set_defaults(func=cmd_pivot)
    qa = commands.add_parser("qa", help="write member histogram and reconciliation QA")
    qa.add_argument("--long")
    qa.add_argument("--histogram")
    qa.add_argument("--reconciliation")
    qa.add_argument("--report")
    qa.add_argument(
        "--engine",
        choices=("polars", "duckdb"),
        default="polars",
        help="'duckdb' is out-of-core and required at full-history scale; "
        "'polars' (default) matches prior tested behaviour at sample scale",
    )
    qa.add_argument("--duckdb-memory-gb", type=int, default=8)
    qa.set_defaults(func=cmd_qa)
    restatement = commands.add_parser(
        "restatement",
        help="restatement rate via a month-ordered running tally, over a CONTINUOUS "
        "month-range glob only (Decision 6) — never the full archive with gaps",
    )
    restatement.add_argument(
        "--long", required=True, help="glob over a continuous month range, e.g. "
        "'data/accounts/long/accounts-long-202[23]-*.parquet' for 2022-2023"
    )
    restatement.add_argument("--scope-label", required=True)
    restatement.add_argument("--report", required=True)
    restatement.add_argument(
        "--engine",
        choices=("python", "duckdb"),
        default="python",
        help="'duckdb' is out-of-core and required at full-history scale; "
        "'python' (default) matches prior tested behaviour at sample scale",
    )
    restatement.add_argument("--duckdb-memory-gb", type=int, default=8)
    restatement.set_defaults(func=cmd_restatement)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
