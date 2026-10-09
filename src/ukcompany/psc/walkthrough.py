"""Safety helpers used by the PSC walkthrough notebook."""

from __future__ import annotations

import glob
import hashlib
import re
import subprocess
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from .archive import verify_manifest
from .manifest import load_manifest


class WalkthroughInputError(RuntimeError):
    """Raised when notebook inputs are missing, partial, or unverifiable."""


def resolve_repository_root(start: str | Path) -> Path:
    """Find the checkout root from the root itself or a directory below it."""
    start_path = Path(start).resolve()
    for candidate in (start_path, *start_path.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src/ukcompany").is_dir():
            return candidate
    raise FileNotFoundError(
        f"cannot find the open-company-uk repository root from {start_path}; "
        "start the kernel in the repository root or notebooks/"
    )


def display_count(value: int | None, *, threshold: int = 10) -> str:
    """Format an aggregate count, suppressing positive cells below ``threshold``."""
    if value is None:
        return ""
    return f"<{threshold}" if 0 < value < threshold else f"{value:,}"


def _part_identity(filename: str, snapshot_date: str, suffix: str) -> tuple[int, int]:
    match = re.fullmatch(
        rf"psc-snapshot-{re.escape(snapshot_date)}_(\d+)of(\d+)\.{re.escape(suffix)}",
        Path(filename).name,
    )
    if not match:
        raise WalkthroughInputError(
            f"unexpected PSC part filename {filename!r}; expected "
            f"psc-snapshot-{snapshot_date}_NofM.{suffix}"
        )
    return int(match.group(1)), int(match.group(2))


def _validate_identities(
    filenames: Sequence[str],
    snapshot_date: str,
    suffix: str,
    expected_parts: int,
    expected_numbers: set[int],
) -> dict[int, str]:
    identities: dict[int, str] = {}
    for filename in filenames:
        number, total = _part_identity(filename, snapshot_date, suffix)
        if total != expected_parts:
            raise WalkthroughInputError(
                f"{filename!r} says of{total}, but this walkthrough expects of{expected_parts}"
            )
        if number in identities:
            raise WalkthroughInputError(
                f"duplicate PSC part {number} in {suffix} inputs: "
                f"{identities[number]!r} and {filename!r}"
            )
        identities[number] = filename
    found = set(identities)
    if found != expected_numbers:
        missing = sorted(expected_numbers - found)
        unexpected = sorted(found - expected_numbers)
        raise WalkthroughInputError(
            f"incomplete {suffix} part set for {snapshot_date}: missing={missing}, "
            f"unexpected={unexpected}; found {len(found)} expected {len(expected_numbers)}"
        )
    return identities


def _stream_sha256(handle) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _verify_extracted_parts(archive_dir: Path, txt_by_number: Mapping[int, str]) -> list[dict]:
    """Compare each consumed TXT byte-for-byte (via SHA-256) with its ZIP member."""
    problems: list[dict] = []
    for number, txt_name in sorted(txt_by_number.items()):
        txt_path = Path(txt_name)
        zip_path = archive_dir / txt_path.with_suffix(".zip").name
        try:
            with zipfile.ZipFile(zip_path) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                matches = [item for item in members if Path(item.filename).name == txt_path.name]
                if len(matches) != 1:
                    problems.append(
                        {
                            "part": number,
                            "filename": txt_path.name,
                            "reason": "expected_txt_member_not_unique_in_zip",
                            "matches": len(matches),
                        }
                    )
                    continue
                member = matches[0]
                if txt_path.stat().st_size != member.file_size:
                    problems.append(
                        {
                            "part": number,
                            "filename": txt_path.name,
                            "reason": "extracted_size_mismatch",
                            "expected": member.file_size,
                            "actual": txt_path.stat().st_size,
                        }
                    )
                    continue
                with archive.open(member) as source, txt_path.open("rb") as extracted:
                    zip_hash = _stream_sha256(source)
                    txt_hash = _stream_sha256(extracted)
                if txt_hash != zip_hash:
                    problems.append(
                        {
                            "part": number,
                            "filename": txt_path.name,
                            "reason": "extracted_sha256_mismatch",
                            "expected": zip_hash,
                            "actual": txt_hash,
                        }
                    )
        except (FileNotFoundError, OSError, zipfile.BadZipFile) as exc:
            problems.append(
                {
                    "part": number,
                    "filename": txt_path.name,
                    "reason": "cannot_verify_extracted_part",
                    "detail": str(exc),
                }
            )
    return problems


def validate_snapshot_inputs(
    manifest_path: str | Path,
    archive_dir: str | Path,
    parts_glob: str,
    snapshot_date: str,
    *,
    sample: bool,
    expected_parts: int = 32,
) -> dict[str, object]:
    """Fail unless the notebook will consume the expected verified snapshot parts."""
    manifest_path = Path(manifest_path)
    archive_dir = Path(archive_dir)
    if not manifest_path.is_file():
        raise WalkthroughInputError(
            f"PSC manifest is missing: {manifest_path}. Run `ukcompany-psc fetch` for "
            f"{snapshot_date}, or set PSC_MANIFEST to the existing manifest."
        )
    if not archive_dir.is_dir():
        raise WalkthroughInputError(
            f"PSC archive directory is missing: {archive_dir}. Set PSC_SNAPSHOT_DIR to the "
            "directory containing the ZIP and extracted TXT parts."
        )

    manifest = load_manifest(manifest_path)
    if manifest.get("snapshot_date") != snapshot_date:
        raise WalkthroughInputError(
            f"manifest snapshot_date={manifest.get('snapshot_date')!r}, expected {snapshot_date!r}"
        )
    manifest_filenames = [entry.get("filename", "") for entry in manifest.get("files", [])]
    all_numbers = set(range(1, expected_parts + 1))
    _validate_identities(
        manifest_filenames, snapshot_date, "zip", expected_parts, all_numbers
    )

    checksum_problems = verify_manifest(manifest_path, archive_dir)
    if checksum_problems:
        raise WalkthroughInputError(
            f"PSC ZIP checksum verification failed before loading: {checksum_problems}"
        )

    txt_paths = sorted(glob.glob(parts_glob))
    selected_numbers = {1} if sample else all_numbers
    txt_by_number = _validate_identities(
        txt_paths, snapshot_date, "txt", expected_parts, selected_numbers
    )
    extracted_problems = _verify_extracted_parts(archive_dir, txt_by_number)
    if extracted_problems:
        raise WalkthroughInputError(
            "extracted PSC TXT verification failed; re-run extraction from the verified ZIPs: "
            f"{extracted_problems}"
        )

    return {
        "manifest_parts": expected_parts,
        "selected_parts": len(txt_paths),
        "selected_part_numbers": sorted(selected_numbers),
        "zip_checksums_verified": True,
        "consumed_txt_verified_against_zip": True,
    }


def require_feature_build_ready(report: Mapping[str, object], *, full_snapshot: bool) -> None:
    """Refuse feature construction from a failed or unreconciled full load."""
    consistency = report.get("consistency_check")
    if not isinstance(consistency, Mapping) or consistency.get("passed") is not True:
        raise RuntimeError("PSC load consistency checks did not pass; refusing to build features")
    if not full_snapshot:
        return
    reconciliation = report.get("totals_reconciliation")
    if consistency.get("totals_line_reconciled") is not True or not isinstance(
        reconciliation, Mapping
    ):
        raise RuntimeError(
            "full-mode PSC load has no totals-line reconciliation; the input is likely partial, "
            "so feature construction is blocked"
        )
    failed = [
        field
        for field, result in reconciliation.items()
        if not isinstance(result, Mapping) or result.get("match") is not True
    ]
    if failed:
        raise RuntimeError(
            f"full-mode PSC totals reconciliation did not pass for {failed}; refusing to build features"
        )


def run_checked(command: Sequence[str], *, cwd: str | Path) -> subprocess.CompletedProcess[str]:
    """Run a notebook subprocess and echo captured diagnostics before propagating failure."""
    try:
        return subprocess.run(
            list(command), cwd=Path(cwd), check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout, file=sys.stdout, end="" if exc.stdout.endswith("\n") else "\n")
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
        raise
