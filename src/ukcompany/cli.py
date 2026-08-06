"""CLI: validate -> fetch -> derive -> score.

    ukcompany run --input companies.csv          # full pipeline
    ukcompany run --input companies.csv --no-fetch   # re-derive/score from cache only
    ukcompany rules-doc                          # regenerate docs/rules.md
    ukcompany snapshot fetch                     # cache current monthly bulk snapshot
    ukcompany snapshot info                      # inspect latest cached snapshot

Input CSV needs a `company_number` column (or pass a single-column file).
Config (paths etc.) in config/settings.yaml; API key ONLY via CH_API_KEY env.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

import yaml

from . import cache as cache_mod
from . import fetch as fetch_mod
from .client import CHClient
from .derive import derive_all, generate_data_dictionary_md
from .rules import generate_rules_md
from .score import score_all, summarise, write_csv
from .validate import validate_input
from .validation.evaluate import evaluate
from .validation.labels import load_labels
from .validation.report import write_report

log = logging.getLogger("ukcompany")


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (stdlib only - a dependency would be overkill).

    KEY=value lines; '#' comments and blanks ignored; surrounding quotes
    stripped. Real environment variables take precedence over the file, so an
    exported CH_API_KEY still wins - the file is a convenience, not an override.
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


DEFAULT_SETTINGS = {
    "paths": {
        "cache_dir": "data/raw",
        "output_dir": "data/processed",
        "snapshot_dir": "data/snapshot",
    },
    "fetch": {
        "max_age_days": 7,
    },
}


def load_settings(path: str | None) -> dict:
    settings = {k: dict(v) for k, v in DEFAULT_SETTINGS.items()}
    if path and Path(path).exists():
        user = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for section, values in user.items():
            settings.setdefault(section, {}).update(values or {})
    return settings


def read_input_numbers(path: str) -> list[str]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            return []
        header_norm = [h.strip().lower() for h in header]
        if "company_number" in header_norm:
            idx = header_norm.index("company_number")
        elif len(header) == 1:
            idx = 0
            # single column, header might itself be a number
            if header[0].strip() and not header[0].strip().lower().startswith("company"):
                rows.append(header[0])
        else:
            raise SystemExit(f"Input {path} has no 'company_number' column (found: {header}).")
        rows += [row[idx] for row in reader if row and len(row) > idx]
    return rows


def cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings(args.settings)
    cache = cache_mod.RawCache(settings["paths"]["cache_dir"])
    out_dir = Path(settings["paths"]["output_dir"])

    report = validate_input(read_input_numbers(args.input))
    print("-- input validation --")
    print(report.summary())
    if report.invalid and not args.allow_invalid:
        print(
            "\nInvalid company numbers present. Fix the input (or pass --allow-invalid "
            "to proceed with the valid subset). Refusing to silently drop rows.",
            file=sys.stderr,
        )
        return 2
    numbers = report.numbers
    if not numbers:
        print("No valid company numbers in input.", file=sys.stderr)
        return 2

    if not args.no_fetch:
        client = CHClient()
        stats = fetch_mod.fetch_companies(
            client, cache, numbers, max_age_days=float(settings["fetch"]["max_age_days"])
        )
        print("-- fetch --")
        print(stats.summary())

    profiles = [c for c in (cache.read(n, fetch_mod.PROFILE) for n in numbers) if c is not None]
    missing = set(numbers) - {p.company_number for p in profiles}
    if missing:
        print(f"WARNING: {len(missing)} numbers have no cached profile (run without --no-fetch?)")
    insolvency = {n: c for n in numbers if (c := cache.read(n, fetch_mod.INSOLVENCY)) is not None}
    officers = {n: c for n in numbers if (c := cache.read(n, fetch_mod.OFFICERS)) is not None}
    psc = {n: c for n in numbers if (c := cache.read(n, fetch_mod.PSC)) is not None}
    psc_stmts = {
        n: c for n in numbers if (c := cache.read(n, fetch_mod.PSC_STATEMENTS)) is not None
    }
    records = derive_all(profiles, insolvency, officers, psc, psc_stmts)
    result = score_all(records)

    write_csv(records, out_dir / "companies.csv")
    write_csv(
        result["flags"],
        out_dir / "flags.csv",
        ["company_number", "rule_id", "severity", "evidence", "observed_at"],
    )
    write_csv(result["excluded"], out_dir / "excluded.csv")
    write_csv(result["not_found"], out_dir / "not_found.csv")

    print("-- score --")
    print(summarise(result, n_input=len(numbers)))
    print(f"\noutputs in {out_dir}/  (companies.csv, flags.csv, excluded.csv, not_found.csv)")
    return 0


def cmd_data_dict(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_data_dictionary_md(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_rules_doc(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_rules_md(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    settings = load_settings(args.settings)
    cache = cache_mod.RawCache(settings["paths"]["cache_dir"])
    labels = load_labels(args.labels)
    control = read_input_numbers(args.control) if args.control else None
    result = evaluate(labels.labels, cache, control)
    output = write_report(result, labels, args.out)

    print("-- insolvency agreement validation (cache only; no fetching) --")
    print(
        f"overall conditional recall: {result.recall():.1%}"
        if result.recall() is not None
        else "overall conditional recall: n/a"
    )
    for case_type in result.case_types():
        recall = result.recall(case_type)
        print(f"{case_type}: {recall:.1%}" if recall is not None else f"{case_type}: n/a")
    print(f"SOLVENT_WINDING_UP errors: {len(result.solvent_winding_up_errors)}")
    print(f"report: {output}")
    return 0


def _snapshot_cache_dir(args: argparse.Namespace) -> Path:
    if args.cache_dir:
        return Path(args.cache_dir)
    return Path(load_settings(args.settings)["paths"]["snapshot_dir"])


def cmd_snapshot_fetch(args: argparse.Namespace) -> int:
    from .snapshot.download import download_snapshot
    from .snapshot.manifest import MANIFEST_NAME, create_manifest, manifest_summary

    cache_dir = _snapshot_cache_dir(args)
    downloaded = download_snapshot(cache_dir, args.month)
    manifest_path = cache_dir / downloaded.month / MANIFEST_NAME
    manifest = create_manifest(downloaded.month, downloaded.paths, downloaded.parts, manifest_path)
    print(manifest_summary(manifest))
    print(f"manifest: {manifest_path}")
    return 0


def cmd_snapshot_info(args: argparse.Namespace) -> int:
    from .snapshot.loader import SnapshotLoader
    from .snapshot.manifest import MANIFEST_NAME, load_manifest, manifest_summary

    cache_dir = _snapshot_cache_dir(args)
    if args.month:
        snapshot_dir = cache_dir / args.month
    else:
        candidates = sorted(path.parent for path in cache_dir.glob(f"*/{MANIFEST_NAME}"))
        if not candidates:
            raise SystemExit(f"No snapshot manifests found under {cache_dir}")
        snapshot_dir = candidates[-1]
    manifest = load_manifest(snapshot_dir / MANIFEST_NAME)
    print(manifest_summary(manifest))
    print("columns:")
    for column in SnapshotLoader(snapshot_dir).columns():
        print(f"  {column}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="ukcompany", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="validate + fetch + derive + score")
    p_run.add_argument("--input", required=True, help="CSV with a company_number column")
    p_run.add_argument("--settings", default="config/settings.yaml")
    p_run.add_argument("--no-fetch", action="store_true", help="re-derive/score from cache only")
    p_run.add_argument("--allow-invalid", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_doc = sub.add_parser("rules-doc", help="regenerate docs/rules.md from the registry")
    p_doc.add_argument("--out", default="docs/rules.md")
    p_doc.set_defaults(func=cmd_rules_doc)

    p_dd = sub.add_parser("data-dict", help="regenerate docs/data-dictionary.md from field docs")
    p_dd.add_argument("--out", default="docs/data-dictionary.md")
    p_dd.set_defaults(func=cmd_data_dict)

    p_validate = sub.add_parser(
        "validate", help="evaluate cached scoring against insolvency labels"
    )
    p_validate.add_argument("--labels", required=True, help="Insolvency Service record-level CSV")
    p_validate.add_argument("--control", help="optional CSV of control company numbers")
    p_validate.add_argument("--out", default="data/insolvency-validation.md")
    p_validate.add_argument("--settings", default="config/settings.yaml")
    p_validate.set_defaults(func=cmd_validate)

    p_snapshot = sub.add_parser("snapshot", help="manage monthly Companies House snapshots")
    snapshot_sub = p_snapshot.add_subparsers(dest="snapshot_command", required=True)

    p_snapshot_fetch = snapshot_sub.add_parser("fetch", help="download and manifest a snapshot")
    p_snapshot_fetch.add_argument("--month", help="snapshot month YYYY-MM (default: current)")
    p_snapshot_fetch.add_argument("--cache-dir")
    p_snapshot_fetch.add_argument("--settings", default="config/settings.yaml")
    p_snapshot_fetch.set_defaults(func=cmd_snapshot_fetch)

    p_snapshot_info = snapshot_sub.add_parser("info", help="show manifest and source columns")
    p_snapshot_info.add_argument("--month", help="snapshot month YYYY-MM (default: latest cached)")
    p_snapshot_info.add_argument("--cache-dir")
    p_snapshot_info.add_argument("--settings", default="config/settings.yaml")
    p_snapshot_info.set_defaults(func=cmd_snapshot_info)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
