"""Dated, hashed provenance manifest for a downloaded PSC snapshot.

Same JSON envelope shape as `ukcompany.snapshot.manifest`, reusing its `sha256_file`
helper (via `psc.download`) rather than duplicating it. Row counts are not computed here —
NDJSON has no cheap row count the way a CSV header does, and `load_report.json` (Task B)
already reports the authoritative line count from the actual load. This manifest exists to
answer "is this archive intact", not "how many records does it contain".
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .download import PSC_LANDING_PAGE_URL, PscPart, sha256_file

MANIFEST_NAME = "manifest.json"


def create_manifest(
    date: str,
    paths: Iterable[str | Path],
    parts: Iterable[PscPart],
    output: str | Path,
    *,
    landing_page_url: str = PSC_LANDING_PAGE_URL,
) -> dict:
    """Hash archives and atomically write provenance JSON. Does not open the zips."""
    archive_paths = tuple(Path(path) for path in paths)
    source_parts = tuple(parts)
    if len(archive_paths) != len(source_parts):
        raise ValueError("PSC snapshot paths and source parts differ in length")
    manifest = {
        "snapshot_date": date,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "landing_page_url": landing_page_url,
        "total_zipped_bytes": sum(path.stat().st_size for path in archive_paths),
        "files": [
            {
                "filename": path.name,
                "source_url": part.url,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path, part in zip(archive_paths, source_parts, strict=True)
        ],
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)
    return manifest


def load_manifest(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def manifest_summary(manifest: dict) -> str:
    return "\n".join(
        [
            f"snapshot date: {manifest['snapshot_date']}",
            f"downloaded at: {manifest['downloaded_at']}",
            f"parts: {len(manifest['files'])}",
            f"total zipped bytes: {manifest['total_zipped_bytes']:,}",
            f"landing page: {manifest['landing_page_url']}",
        ]
    )
