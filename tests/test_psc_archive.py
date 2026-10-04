"""Synthetic-fixture tests for the PSC archive maintenance (Handoff 07, Task 1).

All filesystem-only: checksum verification, D1 retention, extraction, size reporting. No
network, no real snapshot data.
"""

import json
import zipfile
from pathlib import Path

from ukcompany.psc.archive import (
    archive_sizes,
    extract_parts,
    plan_retention,
    prune_archive,
    verify_manifest,
)
from ukcompany.psc.download import sha256_file


def test_plan_retention_keeps_first_of_month_and_latest():
    dates = [
        "2026-01-05", "2026-01-12", "2026-01-30",  # Jan: keep 05
        "2026-02-01", "2026-02-15",                # Feb: keep 01
        "2026-03-09",                              # Mar: keep 09 (also latest)
    ]
    plan = plan_retention(dates)
    assert plan["keep"] == ["2026-01-05", "2026-02-01", "2026-03-09"]
    assert plan["remove"] == ["2026-01-12", "2026-01-30", "2026-02-15"]


def test_plan_retention_single_date_is_kept():
    assert plan_retention(["2026-09-25"]) == {"keep": ["2026-09-25"], "remove": []}


def test_plan_retention_ignores_non_date_names():
    plan = plan_retention(["2026-01-05", "not-a-date", "scratch"])
    assert plan["keep"] == ["2026-01-05"]
    assert plan["remove"] == []


def test_prune_archive_removes_only_non_retained_and_is_idempotent(tmp_path):
    for date in ["2026-01-05", "2026-01-20", "2026-02-02"]:
        (tmp_path / date).mkdir()
    (tmp_path / "keep-me-not-a-date").mkdir()  # untouched

    first = prune_archive(tmp_path)
    assert first["keep"] == ["2026-01-05", "2026-02-02"]
    assert first["removed"] == ["2026-01-20"]
    assert not (tmp_path / "2026-01-20").exists()
    assert (tmp_path / "2026-01-05").exists()
    assert (tmp_path / "2026-02-02").exists()
    assert (tmp_path / "keep-me-not-a-date").exists()

    # Idempotent: a second run removes nothing.
    second = prune_archive(tmp_path)
    assert second["removed"] == []
    assert second["keep"] == ["2026-01-05", "2026-02-02"]


def test_prune_archive_dry_run_deletes_nothing(tmp_path):
    # 2026-01-20 is neither first-of-month (05) nor latest (2026-02-02), so it is the one
    # the policy would remove — but dry_run must leave it on disk.
    for date in ["2026-01-05", "2026-01-20", "2026-02-02"]:
        (tmp_path / date).mkdir()
    result = prune_archive(tmp_path, dry_run=True)
    assert result["removed"] == ["2026-01-20"]
    assert (tmp_path / "2026-01-20").exists()  # still there


def _write_manifest(tmp_path: Path, files: list[Path]) -> Path:
    manifest = {
        "snapshot_date": "2026-09-25",
        "files": [
            {"filename": p.name, "size": p.stat().st_size, "sha256": sha256_file(p)}
            for p in files
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_verify_manifest_passes_for_intact_archive(tmp_path):
    archive = tmp_path / "2026-09-25"
    archive.mkdir()
    part = archive / "psc-snapshot-2026-09-25_1of1.zip"
    part.write_bytes(b"intact archive bytes")
    manifest = _write_manifest(tmp_path, [part])
    assert verify_manifest(manifest, archive) == []


def test_verify_manifest_detects_tamper_size_and_missing(tmp_path):
    archive = tmp_path / "2026-09-25"
    archive.mkdir()
    good = archive / "good.zip"
    good.write_bytes(b"good")
    tampered = archive / "tampered.zip"
    tampered.write_bytes(b"original")
    resized = archive / "resized.zip"
    resized.write_bytes(b"1234")
    gone = archive / "gone.zip"
    gone.write_bytes(b"temporary")
    manifest = _write_manifest(tmp_path, [good, tampered, resized, gone])

    tampered.write_bytes(b"CHANGED!")  # same length, different bytes -> sha mismatch
    resized.write_bytes(b"12345")       # different length -> size mismatch
    gone.unlink()                       # missing

    problems = {p["filename"]: p["reason"] for p in verify_manifest(manifest, archive)}
    assert problems == {
        "tampered.zip": "sha256_mismatch",
        "resized.zip": "size_mismatch",
        "gone.zip": "missing",
    }


def test_extract_parts_is_idempotent(tmp_path):
    archive = tmp_path / "2026-09-25"
    archive.mkdir()
    zip_path = archive / "psc-snapshot-2026-09-25_1of1.zip"
    member = "psc-snapshot-2026-09-25_1of1.txt"
    payload = b'{"company_number":"00000001","data":{}}\n'
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(member, payload)

    extracted = extract_parts(archive)
    assert [p.name for p in extracted] == [member]
    assert (archive / member).read_bytes() == payload

    # Second run: member already present at the right size -> no re-extract, same content.
    again = extract_parts(archive)
    assert [p.name for p in again] == [member]
    assert (archive / member).read_bytes() == payload


def test_archive_sizes_reports_zip_and_txt(tmp_path):
    archive = tmp_path / "2026-09-25"
    archive.mkdir()
    (archive / "a.zip").write_bytes(b"zipbytes")
    (archive / "a.txt").write_bytes(b"txtcontent-longer")
    sizes = archive_sizes(archive)
    assert sizes["n_zip_parts"] == 1
    assert sizes["n_txt_parts"] == 1
    assert sizes["zipped_bytes"] == len(b"zipbytes")
    assert sizes["extracted_bytes"] == len(b"txtcontent-longer")
