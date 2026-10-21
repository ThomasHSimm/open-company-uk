"""Full-width, lazy Polars loader for Companies House snapshot parts."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ukcompany.duckdb_backend import (
    PathValue,
    expand_input_path,
    is_remote_uri,
    open_input_file,
)

MISSING_POLARS = (
    "Snapshot support requires Polars. Install it with: pip install 'open-company-uk[snapshot]'"
)

# Stable names used by initial downstream consumers. SnapshotLoader exposes the
# complete source schema unchanged; this mapping is convenience, not a rename.
COLUMNS = {
    "company_number": "CompanyNumber",
    "company_name": "CompanyName",
    "company_status": "CompanyStatus",
    "company_category": "CompanyCategory",
    "incorporation_date": "IncorporationDate",
    "postcode": "RegAddress.PostCode",
    "sic_1": "SICCode.SicText_1",
    "sic_2": "SICCode.SicText_2",
    "sic_3": "SICCode.SicText_3",
    "sic_4": "SICCode.SicText_4",
}


def _require_polars():
    try:
        return importlib.import_module("polars")
    except ImportError as exc:
        raise ImportError(MISSING_POLARS) from exc


def _extract_csv(
    archive: PathValue,
    *,
    cache_dir: str | Path | None = None,
    filesystem_options: dict[str, dict[str, Any]] | None = None,
) -> Path:
    remote = is_remote_uri(archive)
    if remote:
        cache_root = Path(cache_dir or tempfile.gettempdir()) / "ukcompany-snapshot"
        cache_key = hashlib.sha256(str(archive).encode("utf-8")).hexdigest()[:20]
        destination = cache_root / cache_key
        archive_handle = open_input_file(
            archive, "rb", filesystem_options=filesystem_options
        )
    else:
        archive_path = Path(archive)
        destination = archive_path.parent / "extracted" / archive_path.stem
        archive_handle = archive_path.open("rb")
    with archive_handle, zipfile.ZipFile(archive_handle) as zipped:
        csv_members = [item for item in zipped.infolist() if item.filename.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise ValueError(f"{archive} must contain exactly one CSV (found {len(csv_members)})")
        member = csv_members[0]
        if Path(member.filename).name != member.filename:
            raise ValueError(f"unsafe archive member path in {archive}: {member.filename}")
        output = destination / member.filename
        metadata_path = output.with_suffix(output.suffix + ".source.json")
        source_metadata = {
            "source": str(archive),
            "member": member.filename,
            "member_size": member.file_size,
            "member_crc": member.CRC,
        }
        if (
            output.exists()
            and output.stat().st_size == member.file_size
            and (
                not remote
                or (
                    metadata_path.exists()
                    and json.loads(metadata_path.read_text(encoding="utf-8")) == source_metadata
                )
            )
        ):
            return output
        destination.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        with zipped.open(member) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target)
        if temporary.stat().st_size != member.file_size:
            temporary.unlink()
            raise ValueError(f"extracted size mismatch for {archive}")
        temporary.replace(output)
        if remote:
            metadata_path.write_text(json.dumps(source_metadata, sort_keys=True), encoding="utf-8")
        return output


def _stage_remote_csv(
    source: str,
    *,
    cache_dir: str | Path | None = None,
    filesystem_options: dict[str, dict[str, Any]] | None = None,
) -> Path:
    cache_root = Path(cache_dir or tempfile.gettempdir()) / "ukcompany-snapshot"
    cache_key = hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]
    destination = cache_root / cache_key / Path(urlsplit(source).path).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with open_input_file(source, "rb", filesystem_options=filesystem_options) as remote:
        with temporary.open("wb") as local:
            shutil.copyfileobj(remote, local)
    temporary.replace(destination)
    return destination


class SnapshotLoader:
    """Scan one complete snapshot without collecting it into memory."""

    def __init__(
        self,
        parts: str | Path | Iterable[str | Path],
        *,
        cache_dir: str | Path | None = None,
        filesystem_options: dict[str, dict[str, Any]] | None = None,
    ):
        self.cache_dir = cache_dir
        self.filesystem_options = filesystem_options
        self._resolved_csv_paths: tuple[Path, ...] | None = None
        if isinstance(parts, (str, Path)):
            if is_remote_uri(parts):
                self.parts = tuple(
                    expand_input_path(parts, filesystem_options=filesystem_options)
                )
            else:
                candidate = Path(parts)
                if candidate.is_dir():
                    self.parts = tuple(sorted(candidate.glob("BasicCompanyData-*.zip")))
                else:
                    matches = expand_input_path(candidate)
                    self.parts = tuple(Path(match) for match in matches) or (candidate,)
        else:
            self.parts = tuple(
                str(part) if is_remote_uri(part) else Path(part) for part in parts
            )
        if not self.parts:
            raise ValueError("no snapshot CSV or ZIP parts found")

    def _csv_paths(self) -> list[Path]:
        if self._resolved_csv_paths is not None:
            return list(self._resolved_csv_paths)
        paths: list[Path] = []
        for part in self.parts:
            part_text = str(part)
            suffix = Path(urlsplit(part_text).path).suffix.casefold()
            if suffix == ".zip":
                paths.append(
                    _extract_csv(
                        part,
                        cache_dir=self.cache_dir,
                        filesystem_options=self.filesystem_options,
                    )
                )
            elif is_remote_uri(part):
                paths.append(
                    _stage_remote_csv(
                        str(part),
                        cache_dir=self.cache_dir,
                        filesystem_options=self.filesystem_options,
                    )
                )
            else:
                paths.append(Path(part))
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"snapshot part(s) not found: {', '.join(missing)}")
        self._resolved_csv_paths = tuple(paths)
        return paths

    def scan(self) -> Any:
        """Return a full-width LazyFrame; callers choose projections and filters.

        The real Companies House bulk file carries leading whitespace on several
        header names (the company-number column is literally `" CompanyNumber"`).
        Column names are stripped immediately after the scan so downstream sees
        `CompanyNumber` and the COLUMNS mapping resolves. Crucially, the string
        dtype override is keyed on the raw (possibly space-prefixed) header name
        so it actually fires - otherwise the column is type-inferred as int and
        leading zeros are silently stripped.
        """
        pl = _require_polars()
        paths = self._csv_paths()
        # Peek at the header row to locate the raw company-number column name,
        # which may differ from COLUMNS["company_number"] only by whitespace.
        raw_names = pl.scan_csv(paths).collect_schema().names()
        number_raw = next(
            (name for name in raw_names if name.strip() == COLUMNS["company_number"]),
            COLUMNS["company_number"],
        )
        frame = pl.scan_csv(paths, schema_overrides={number_raw: pl.String})
        rename = {name: name.strip() for name in raw_names if name != name.strip()}
        return frame.rename(rename) if rename else frame

    def head(self, n: int = 5) -> Any:
        """Collect only the first ``n`` rows for quick inspection."""
        return self.scan().head(n).collect()

    def columns(self) -> list[str]:
        """Return source column names without collecting snapshot rows."""
        return self.scan().collect_schema().names()
