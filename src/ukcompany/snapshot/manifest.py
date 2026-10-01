"""Dated, hashed provenance manifest for a downloaded company snapshot."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .download import LANDING_PAGE_URL, SnapshotPart, sha256_file
from .loader import SnapshotLoader, _require_polars

MANIFEST_NAME = "manifest.json"


def create_manifest(
    month: str,
    paths: Iterable[str | Path],
    parts: Iterable[SnapshotPart],
    output: str | Path,
    *,
    landing_page_url: str = LANDING_PAGE_URL,
) -> dict:
    """Count rows lazily, hash archives, and atomically write provenance JSON."""
    archive_paths = tuple(Path(path) for path in paths)
    source_parts = tuple(parts)
    if len(archive_paths) != len(source_parts):
        raise ValueError("snapshot paths and source parts differ in length")
    pl = _require_polars()
    row_count = SnapshotLoader(archive_paths).scan().select(pl.len()).collect().item()
    manifest = {
        "snapshot_month": month,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "landing_page_url": landing_page_url,
        "total_rows": row_count,
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
            f"snapshot month: {manifest['snapshot_month']}",
            f"downloaded at: {manifest['downloaded_at']}",
            f"parts: {len(manifest['files'])}",
            f"rows: {manifest['total_rows']}",
            f"landing page: {manifest['landing_page_url']}",
        ]
    )
