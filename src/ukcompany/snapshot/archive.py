"""Archive maintenance for the monthly basic-company snapshot (Handoff 08, Task 1).

Mirrors `ukcompany.psc.archive`: checksum verification against the manifest and a retention
policy, as filesystem-only, synthetically testable functions. The basic snapshot is published
monthly (one dated `YYYY-MM-01` set per month), so the "first snapshot of each month plus the
latest" policy keeps every monthly set - there is never more than one per month to drop. The
policy is still implemented (and tested) so the cadence assumption is explicit and would prune
correctly if a finer cadence ever appeared.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .download import sha256_file
from .manifest import load_manifest

_MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")


def verify_manifest(manifest_path: str | Path, archive_dir: str | Path) -> list[dict]:
    """Re-hash every file named in the manifest against the copy in `archive_dir`.

    Returns a list of problem records (empty == every file present and matching). Reports
    only; a fail-loud caller raises on a non-empty result.
    """
    manifest = load_manifest(manifest_path)
    archive = Path(archive_dir)
    problems: list[dict] = []
    for entry in manifest.get("files", []):
        filename = entry["filename"]
        path = archive / filename
        if not path.exists():
            problems.append({"filename": filename, "reason": "missing"})
            continue
        if "size" in entry and path.stat().st_size != entry["size"]:
            problems.append({
                "filename": filename, "reason": "size_mismatch",
                "expected": entry["size"], "actual": path.stat().st_size,
            })
            continue
        actual_sha = sha256_file(path)
        if actual_sha != entry["sha256"]:
            problems.append({
                "filename": filename, "reason": "sha256_mismatch",
                "expected": entry["sha256"], "actual": actual_sha,
            })
    return problems


def plan_retention(months: list[str]) -> dict[str, list[str]]:
    """Keep the first snapshot of each calendar month plus the latest. The basic snapshot is
    monthly (dirs named ``YYYY-MM``), so each directory is the sole snapshot of its month and
    all are kept; the latest is kept explicitly too. Pure function for testability."""
    valid = sorted(m for m in months if _MONTH_DIR_RE.fullmatch(m))
    keep: set[str] = set()
    seen_months: set[str] = set()
    for month in valid:
        if month not in seen_months:  # first (and only) snapshot of this month
            seen_months.add(month)
            keep.add(month)
    if valid:
        keep.add(valid[-1])  # latest overall
    remove = [m for m in valid if m not in keep]
    return {"keep": sorted(keep), "remove": sorted(remove)}


def prune_archive(snapshots_dir: str | Path, *, dry_run: bool = False) -> dict:
    """Apply the retention policy to the month-keyed snapshot directories under
    `snapshots_dir`. Only ``YYYY-MM`` directories are considered; anything else is left
    untouched. Idempotent."""
    root = Path(snapshots_dir)
    if not root.exists():
        return {"keep": [], "removed": []}
    month_dirs = [p.name for p in root.iterdir() if p.is_dir() and _MONTH_DIR_RE.fullmatch(p.name)]
    plan = plan_retention(month_dirs)
    removed: list[str] = []
    if not dry_run:
        for month in plan["remove"]:
            shutil.rmtree(root / month)
            removed.append(month)
    else:
        removed = plan["remove"]
    return {"keep": plan["keep"], "removed": removed}
