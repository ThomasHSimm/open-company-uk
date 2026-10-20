"""Inventory of locally held Companies House snapshots and archives.

Companies House keeps no historical archive of the register snapshot or the PSC
daily snapshot: whatever month is not downloaded is lost permanently, so the
copies on disk here are the only ones. The monthly bulk *accounts* archives are
different - Companies House republishes them, so they can be re-downloaded.

`collect_inventory` scans the data directory read-only (no network) and reports,
per source, which months are held, when they were downloaded, and - for the
irreplaceable sources - the provenance recorded in each manifest. The CLI
`ukcompany status` prints it so the maintainer can confirm nothing has been lost.

Every field is read defensively with `.get()`; a missing or malformed manifest
degrades to a partial record rather than raising, because the point of the
command is to surface gaps, not to fail on them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Register and PSC snapshots cannot be re-downloaded once a month passes;
# the accounts monthly archives are republished by Companies House.
IRREPLACEABLE_SOURCES = ("register", "psc")
REPLACEABLE_SOURCES = ("accounts",)

_ACCOUNTS_LONG_RE = re.compile(r"accounts-long-(\d{4}-\d{2})\.parquet$")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def inventory_register(data_root: Path) -> list[dict]:
    """Register (BasicCompanyData) snapshots, one per `snapshot/*/manifest.json`."""
    snapshot_dir = data_root / "snapshot"
    records: list[dict] = []
    for manifest_path in sorted(snapshot_dir.glob("*/manifest.json")):
        manifest = _load_json(manifest_path)
        records.append(
            {
                "month": manifest.get("snapshot_month") or manifest_path.parent.name,
                "downloaded_at": manifest.get("downloaded_at"),
                "rows": manifest.get("total_rows"),
                "parts": len(manifest.get("files") or []),
                "path": str(manifest_path.parent),
            }
        )
    return records


def inventory_psc(data_root: Path) -> list[dict]:
    """PSC daily snapshots.

    A manifested snapshot (`psc/*/manifest.json`) is reported with its recorded
    provenance. Dated PSC directories without a manifest are still listed - they
    hold derived parquet and are equally irreplaceable - but flagged as such.
    """
    psc_dir = data_root / "psc"
    records: list[dict] = []
    seen: set[str] = set()
    for manifest_path in sorted(psc_dir.glob("*/manifest.json")):
        manifest = _load_json(manifest_path)
        directory = manifest_path.parent
        seen.add(directory.name)
        records.append(
            {
                "date": manifest.get("snapshot_date") or directory.name,
                "downloaded_at": manifest.get("downloaded_at"),
                "parts": len(manifest.get("files") or []),
                "manifested": True,
                "path": str(directory),
            }
        )
    # Dated directories (YYYY-MM-DD, possibly with a -suffix) that carry derived
    # data but no manifest of their own.
    for directory in sorted(p for p in psc_dir.glob("*") if p.is_dir()):
        if directory.name in seen or not directory.name[:10].count("-") == 2:
            continue
        records.append(
            {
                "date": directory.name,
                "downloaded_at": None,
                "parts": 0,
                "manifested": False,
                "path": str(directory),
            }
        )
    return sorted(records, key=lambda r: r["date"])


def inventory_accounts(data_root: Path) -> dict:
    """Monthly bulk accounts coverage.

    Reports the distinct archive months present as extracted `accounts-long-*`
    parquet (the span that matters for analysis), the roots that hold them, and
    any raw monthly ZIP still on disk. The raw ZIPs are re-downloadable; the
    months are listed as a span rather than per-file because they routinely run
    to well over a hundred.
    """
    accounts_dir = data_root / "accounts"
    months: set[str] = set()
    roots: set[str] = set()
    if accounts_dir.exists():
        for parquet_path in accounts_dir.rglob("accounts-long-*.parquet"):
            match = _ACCOUNTS_LONG_RE.search(parquet_path.name)
            if match:
                months.add(match.group(1))
                roots.add(str(parquet_path.parent))
    zips = sorted(str(p) for p in accounts_dir.rglob("*.zip")) if accounts_dir.exists() else []
    ordered = sorted(months)
    return {
        "month_count": len(ordered),
        "span": (ordered[0], ordered[-1]) if ordered else None,
        "months": ordered,
        "roots": sorted(roots),
        "raw_zips": zips,
    }


def collect_inventory(data_root: str | Path = "data") -> dict:
    """Scan `data_root` and return the full held-snapshot inventory."""
    root = Path(data_root)
    return {
        "data_root": str(root),
        "register": inventory_register(root),
        "psc": inventory_psc(root),
        "accounts": inventory_accounts(root),
    }


def format_inventory(inventory: dict) -> str:
    """Render `collect_inventory` output as plain text for the CLI."""
    lines: list[str] = []
    lines.append(f"Local Companies House snapshot inventory (data root: {inventory['data_root']})")
    lines.append("")

    lines.append("Register (BasicCompanyData) - IRREPLACEABLE, no upstream archive:")
    register = inventory["register"]
    if not register:
        lines.append("  (none held)")
    for record in register:
        rows = f"{record['rows']:,}" if isinstance(record["rows"], int) else "?"
        lines.append(
            f"  {record['month']}: {record['parts']} parts, {rows} rows, "
            f"downloaded {record['downloaded_at'] or '?'}"
        )

    lines.append("")
    lines.append("PSC (daily snapshot) - IRREPLACEABLE, no upstream archive:")
    psc = inventory["psc"]
    if not psc:
        lines.append("  (none held)")
    for record in psc:
        note = "" if record["manifested"] else "  [no manifest - derived data only]"
        parts = f"{record['parts']} parts, " if record["manifested"] else ""
        lines.append(
            f"  {record['date']}: {parts}downloaded {record['downloaded_at'] or '?'}{note}"
        )

    lines.append("")
    lines.append("Accounts (monthly bulk archives) - re-downloadable from Companies House:")
    accounts = inventory["accounts"]
    if accounts["span"]:
        start, end = accounts["span"]
        lines.append(
            f"  extracted long-table months: {accounts['month_count']} "
            f"({start} through {end})"
        )
    else:
        lines.append("  extracted long-table months: (none held)")
    for root in accounts["roots"]:
        lines.append(f"    root: {root}")
    if accounts["raw_zips"]:
        lines.append(f"  raw monthly ZIPs on disk: {len(accounts['raw_zips'])}")
        for zip_path in accounts["raw_zips"]:
            lines.append(f"    {zip_path}")
    else:
        lines.append("  raw monthly ZIPs on disk: none (extracted parquet retained)")

    return "\n".join(lines)
