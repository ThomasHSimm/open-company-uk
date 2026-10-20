"""Tests for the local-snapshot inventory (`ukcompany status`).

Synthetic directory trees only: no real company data, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from ukcompany.status import collect_inventory, format_inventory


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    # Two register snapshots.
    _write_json(
        root / "snapshot" / "2026-08" / "manifest.json",
        {
            "snapshot_month": "2026-08",
            "downloaded_at": "2026-08-06T12:42:26+00:00",
            "total_rows": 100,
            "files": [{"filename": f"part{i}.zip"} for i in range(7)],
        },
    )
    _write_json(
        root / "snapshot" / "2026-10" / "manifest.json",
        {
            "snapshot_month": "2026-10",
            "downloaded_at": "2026-10-05T09:11:32+00:00",
            "total_rows": 110,
            "files": [{"filename": f"part{i}.zip"} for i in range(7)],
        },
    )
    # One manifested PSC snapshot and one dated directory without a manifest.
    _write_json(
        root / "psc" / "2026-09-25" / "manifest.json",
        {
            "snapshot_date": "2026-09-25",
            "downloaded_at": "2026-09-25T20:32:25+00:00",
            "files": [{"filename": f"psc_{i}.zip"} for i in range(32)],
        },
    )
    (root / "psc" / "2026-09-18" / "governed").mkdir(parents=True)
    # Accounts: three extracted months in one root, one raw ZIP.
    for month in ("2014-01", "2014-02", "2026-09"):
        parquet = root / "accounts" / "long" / f"accounts-long-{month}.parquet"
        parquet.parent.mkdir(parents=True, exist_ok=True)
        parquet.write_bytes(b"PAR1")
    zip_path = root / "accounts" / "downloads" / "Accounts_Monthly_Data-September2026.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"PK")
    return root


def test_register_inventory_lists_both_months(tmp_path):
    inventory = collect_inventory(_build_data_root(tmp_path))
    months = [r["month"] for r in inventory["register"]]
    assert months == ["2026-08", "2026-10"]
    assert inventory["register"][0]["parts"] == 7
    assert inventory["register"][1]["rows"] == 110


def test_psc_inventory_flags_unmanifested_dir(tmp_path):
    inventory = collect_inventory(_build_data_root(tmp_path))
    by_date = {r["date"]: r for r in inventory["psc"]}
    assert by_date["2026-09-25"]["manifested"] is True
    assert by_date["2026-09-25"]["parts"] == 32
    assert by_date["2026-09-18"]["manifested"] is False


def test_accounts_inventory_reports_span_and_zips(tmp_path):
    inventory = collect_inventory(_build_data_root(tmp_path))
    accounts = inventory["accounts"]
    assert accounts["month_count"] == 3
    assert accounts["span"] == ("2014-01", "2026-09")
    assert len(accounts["raw_zips"]) == 1


def test_empty_data_root_degrades_gracefully(tmp_path):
    inventory = collect_inventory(tmp_path / "nonexistent")
    assert inventory["register"] == []
    assert inventory["psc"] == []
    assert inventory["accounts"]["span"] is None
    # Formatting an empty inventory must not raise and must flag the gaps.
    rendered = format_inventory(inventory)
    assert "(none held)" in rendered


def test_malformed_register_manifest_does_not_raise(tmp_path):
    root = tmp_path / "data"
    bad = root / "snapshot" / "2026-08" / "manifest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{ not valid json", encoding="utf-8")
    inventory = collect_inventory(root)
    # Falls back to the directory name; row count unknown.
    assert inventory["register"][0]["month"] == "2026-08"
    assert inventory["register"][0]["rows"] is None
    assert "?" in format_inventory(inventory)
