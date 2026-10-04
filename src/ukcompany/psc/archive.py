"""Archive maintenance for the PSC snapshot pipeline (Handoff 07, Task 1).

Three concerns the repeatable load needs that `download`/`manifest`/`loader` don't cover:

* **Checksum verification** - re-hash the archived zips against `manifest.json` so a silent
  bit-rot or truncated download is caught *before* a load reads it.
* **Retention (decision D1)** - keep the first snapshot of each month plus the latest, drop
  the rest, so a daily cron does not accumulate ~0.75 TB/yr. Idempotent: re-running keeps
  exactly the same set.
* **Extraction** - CH serves `.zip` parts, but DuckDB's NDJSON reader cannot open a zip
  (it understands gzip/zstd, not the zip container), so the loader reads extracted `.txt`.
  This unzips each part once, idempotently.

All functions are pure filesystem operations with no network, so they are unit-testable with
synthetic fixtures.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .download import sha256_file
from .manifest import load_manifest

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def verify_manifest(manifest_path: str | Path, archive_dir: str | Path) -> list[dict]:
    """Re-hash every file named in the manifest against the copy in `archive_dir`.

    Returns a list of problem records (empty == every file present and matching). A caller
    that wants fail-loud behaviour raises on a non-empty result; this function only reports,
    so tests can assert on the specific failure kinds.
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
        actual_size = path.stat().st_size
        if "size" in entry and actual_size != entry["size"]:
            problems.append(
                {
                    "filename": filename,
                    "reason": "size_mismatch",
                    "expected": entry["size"],
                    "actual": actual_size,
                }
            )
            continue
        actual_sha = sha256_file(path)
        if actual_sha != entry["sha256"]:
            problems.append(
                {
                    "filename": filename,
                    "reason": "sha256_mismatch",
                    "expected": entry["sha256"],
                    "actual": actual_sha,
                }
            )
    return problems


def plan_retention(dates: list[str]) -> dict[str, list[str]]:
    """Decision D1: keep the first snapshot of each calendar month plus the single latest.

    Pure function over a list of YYYY-MM-DD strings so the policy itself is testable without
    touching the filesystem. Returns {"keep": [...], "remove": [...]}, both sorted.
    """
    valid = sorted(d for d in dates if _DATE_DIR_RE.fullmatch(d))
    keep: set[str] = set()
    first_of_month: dict[str, str] = {}
    for date in valid:
        month = date[:7]  # YYYY-MM
        if month not in first_of_month:
            first_of_month[month] = date
            keep.add(date)
    if valid:
        keep.add(valid[-1])  # latest overall
    remove = [d for d in valid if d not in keep]
    return {"keep": sorted(keep), "remove": sorted(remove)}


def prune_archive(downloads_dir: str | Path, *, dry_run: bool = False) -> dict:
    """Apply the D1 retention policy to the date-keyed snapshot directories under
    `downloads_dir`. Only directories whose name is a YYYY-MM-DD date are considered;
    anything else is left untouched. Idempotent."""
    root = Path(downloads_dir)
    if not root.exists():
        return {"keep": [], "removed": []}
    date_dirs = [p.name for p in root.iterdir() if p.is_dir() and _DATE_DIR_RE.fullmatch(p.name)]
    plan = plan_retention(date_dirs)
    removed: list[str] = []
    if not dry_run:
        import shutil

        for date in plan["remove"]:
            shutil.rmtree(root / date)
            removed.append(date)
    else:
        removed = plan["remove"]
    return {"keep": plan["keep"], "removed": removed}


def extract_parts(snapshot_dir: str | Path) -> list[Path]:
    """Extract each `.zip` part in `snapshot_dir` to its `.txt` member, idempotently.

    DuckDB's NDJSON reader cannot open a zip container, so the loader needs extracted text.
    Skips a member that is already present at the expected size, so re-running is cheap and
    safe. Returns the sorted list of extracted `.txt` paths."""
    directory = Path(snapshot_dir)
    extracted: list[Path] = []
    for zip_path in sorted(directory.glob("*.zip")):
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                target = directory / Path(info.filename).name
                if not (target.exists() and target.stat().st_size == info.file_size):
                    with archive.open(info) as source, target.open("wb") as handle:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            handle.write(chunk)
                extracted.append(target)
    return sorted(extracted)


def archive_sizes(snapshot_dir: str | Path) -> dict:
    """Report zipped vs extracted bytes for one snapshot directory, for the load report."""
    directory = Path(snapshot_dir)
    zipped = sum(p.stat().st_size for p in directory.glob("*.zip"))
    extracted = sum(p.stat().st_size for p in directory.glob("*.txt"))
    return {
        "snapshot_dir": str(directory),
        "zipped_bytes": zipped,
        "extracted_bytes": extracted,
        "n_zip_parts": len(list(directory.glob("*.zip"))),
        "n_txt_parts": len(list(directory.glob("*.txt"))),
    }
