"""Synthetic-fixture tests for the snapshot archive maintenance (Handoff 08, Task 1)."""

import json
from pathlib import Path

from ukcompany.snapshot.archive import (
    plan_retention,
    prune_archive,
    verify_manifest,
)
from ukcompany.snapshot.download import sha256_file


def test_plan_retention_keeps_every_month_and_latest():
    # Monthly cadence: each dir is the sole snapshot of its month, so all are kept.
    months = ["2026-06", "2026-07", "2026-08"]
    plan = plan_retention(months)
    assert plan["keep"] == months
    assert plan["remove"] == []


def test_plan_retention_ignores_non_month_names():
    plan = plan_retention(["2026-08", "scratch", "2026-08-01"])
    assert plan["keep"] == ["2026-08"]
    assert plan["remove"] == []


def test_prune_archive_keeps_month_dirs_and_is_idempotent(tmp_path):
    for month in ["2026-06", "2026-07"]:
        (tmp_path / month).mkdir()
    (tmp_path / "not-a-month").mkdir()
    first = prune_archive(tmp_path)
    assert first["keep"] == ["2026-06", "2026-07"]
    assert first["removed"] == []
    assert (tmp_path / "not-a-month").exists()  # untouched
    assert prune_archive(tmp_path)["removed"] == []  # idempotent


def _write_manifest(tmp_path: Path, files: list[Path]) -> Path:
    manifest = {
        "snapshot_month": "2026-08",
        "files": [
            {"filename": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)}
            for p in files
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_verify_manifest_passes_and_detects_problems(tmp_path):
    archive = tmp_path / "2026-08"
    archive.mkdir()
    good = archive / "BasicCompanyData-2026-08-01-part1_2.zip"
    good.write_bytes(b"good archive bytes")
    tampered = archive / "BasicCompanyData-2026-08-01-part2_2.zip"
    tampered.write_bytes(b"original")
    manifest = _write_manifest(tmp_path, [good, tampered])

    assert verify_manifest(manifest, archive) == []  # intact

    tampered.write_bytes(b"CHANGED!")  # same length, different bytes
    problems = {p["filename"]: p["reason"] for p in verify_manifest(manifest, archive)}
    assert problems == {"BasicCompanyData-2026-08-01-part2_2.zip": "sha256_mismatch"}

    tampered.unlink()
    problems = {p["filename"]: p["reason"] for p in verify_manifest(manifest, archive)}
    assert problems == {"BasicCompanyData-2026-08-01-part2_2.zip": "missing"}
