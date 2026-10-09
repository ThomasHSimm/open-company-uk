import ast
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ukcompany.psc.download import sha256_file
from ukcompany.psc.walkthrough import (
    WalkthroughInputError,
    display_count,
    require_feature_build_ready,
    resolve_repository_root,
    run_checked,
    validate_snapshot_inputs,
)

SNAPSHOT_DATE = "2026-09-25"


def _snapshot_fixture(tmp_path: Path, *, parts: int = 2) -> tuple[Path, Path]:
    archive = tmp_path / SNAPSHOT_DATE
    archive.mkdir()
    files = []
    for number in range(1, parts + 1):
        stem = f"psc-snapshot-{SNAPSHOT_DATE}_{number}of{parts}"
        txt_path = archive / f"{stem}.txt"
        payload = f'{{"company_number":"0000000{number}","data":{{}}}}\n'.encode()
        txt_path.write_bytes(payload)
        zip_path = archive / f"{stem}.zip"
        with zipfile.ZipFile(zip_path, "w") as zipped:
            zipped.writestr(txt_path.name, payload)
        files.append(
            {
                "filename": zip_path.name,
                "size": zip_path.stat().st_size,
                "sha256": sha256_file(zip_path),
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"snapshot_date": SNAPSHOT_DATE, "files": files}), encoding="utf-8"
    )
    return archive, manifest


def test_validate_snapshot_inputs_rejects_checksum_failure(tmp_path):
    archive, manifest = _snapshot_fixture(tmp_path)
    (archive / f"psc-snapshot-{SNAPSHOT_DATE}_2of2.zip").write_bytes(b"corrupt")

    with pytest.raises(WalkthroughInputError, match="checksum verification failed"):
        validate_snapshot_inputs(
            manifest,
            archive,
            str(archive / f"psc-snapshot-{SNAPSHOT_DATE}_1of2.txt"),
            SNAPSHOT_DATE,
            sample=True,
            expected_parts=2,
        )


def test_validate_snapshot_inputs_rejects_incomplete_full_mode(tmp_path):
    archive, manifest = _snapshot_fixture(tmp_path)
    (archive / f"psc-snapshot-{SNAPSHOT_DATE}_2of2.txt").unlink()

    with pytest.raises(WalkthroughInputError, match="incomplete txt part set"):
        validate_snapshot_inputs(
            manifest,
            archive,
            str(archive / f"psc-snapshot-{SNAPSHOT_DATE}_*of2.txt"),
            SNAPSHOT_DATE,
            sample=False,
            expected_parts=2,
        )


def test_validate_snapshot_inputs_checks_consumed_extracted_bytes(tmp_path):
    archive, manifest = _snapshot_fixture(tmp_path)
    extracted = archive / f"psc-snapshot-{SNAPSHOT_DATE}_1of2.txt"
    extracted.write_bytes(b"x" * extracted.stat().st_size)

    with pytest.raises(WalkthroughInputError, match="extracted PSC TXT verification failed"):
        validate_snapshot_inputs(
            manifest,
            archive,
            str(extracted),
            SNAPSHOT_DATE,
            sample=True,
            expected_parts=2,
        )


def test_full_mode_requires_successful_totals_reconciliation():
    report = {
        "consistency_check": {"passed": True, "totals_line_reconciled": False},
        "totals_reconciliation": None,
    }
    with pytest.raises(RuntimeError, match="no totals-line reconciliation"):
        require_feature_build_ready(report, full_snapshot=True)


def test_display_count_suppresses_positive_counts_below_ten():
    assert display_count(None) == ""
    assert display_count(0) == "0"
    assert display_count(2) == "<10"
    assert display_count(9) == "<10"
    assert display_count(10) == "10"
    assert display_count(1234) == "1,234"


def test_run_checked_propagates_subprocess_failure(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        run_checked(
            [sys.executable, "-c", "import sys; print('diagnostic'); sys.exit(7)"],
            cwd=tmp_path,
        )
    assert exc_info.value.returncode == 7
    assert exc_info.value.stdout.strip() == "diagnostic"


def test_repository_root_resolves_from_root_and_notebooks():
    root = Path(__file__).resolve().parents[1]
    assert resolve_repository_root(root) == root
    assert resolve_repository_root(root / "notebooks") == root


def test_notebook_is_clean_and_all_code_parses():
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root / "notebooks/psc-walkthrough.ipynb").read_text())
    sources = []
    for cell in notebook["cells"]:
        assert cell.get("execution_count") is None
        assert cell.get("outputs", []) == []
        assert "execution" not in cell.get("metadata", {})
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            ast.parse(source)
            sources.append(source)
    all_code = "\n".join(sources)
    assert "sys.executable" in all_code
    assert '"python"' not in all_code
    assert "run_checked(" in all_code
    assert "require_feature_build_ready(" in all_code


def test_notebook_paths_links_and_outputs_are_safe():
    root = Path(__file__).resolve().parents[1]
    notebook_text = (root / "notebooks/psc-walkthrough.ipynb").read_text()
    assert "resolve_repository_root" in notebook_text
    assert "../docs/psc-data-guide.md" in notebook_text
    assert "../docs/psc-bulk-features.md" in notebook_text
    assert "PARTIAL SAMPLE" in notebook_text
    assert "FULL SNAPSHOT" in notebook_text
    notebook = json.loads(notebook_text)
    assert all(not cell.get("outputs") for cell in notebook["cells"])
