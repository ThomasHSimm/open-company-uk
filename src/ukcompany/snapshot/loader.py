"""Full-width, lazy Polars loader for Companies House snapshot parts."""

from __future__ import annotations

import importlib
import shutil
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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


def _extract_csv(archive: Path) -> Path:
    destination = archive.parent / "extracted" / archive.stem
    with zipfile.ZipFile(archive) as zipped:
        csv_members = [item for item in zipped.infolist() if item.filename.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise ValueError(f"{archive} must contain exactly one CSV (found {len(csv_members)})")
        member = csv_members[0]
        if Path(member.filename).name != member.filename:
            raise ValueError(f"unsafe archive member path in {archive}: {member.filename}")
        output = destination / member.filename
        if output.exists() and output.stat().st_size == member.file_size:
            return output
        destination.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        with zipped.open(member) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target)
        if temporary.stat().st_size != member.file_size:
            temporary.unlink()
            raise ValueError(f"extracted size mismatch for {archive}")
        temporary.replace(output)
        return output


class SnapshotLoader:
    """Scan one complete snapshot without collecting it into memory."""

    def __init__(self, parts: str | Path | Iterable[str | Path]):
        if isinstance(parts, (str, Path)):
            candidate = Path(parts)
            if candidate.is_dir():
                self.parts = tuple(sorted(candidate.glob("BasicCompanyData-*.zip")))
            else:
                self.parts = (candidate,)
        else:
            self.parts = tuple(Path(part) for part in parts)
        if not self.parts:
            raise ValueError("no snapshot CSV or ZIP parts found")

    def _csv_paths(self) -> list[Path]:
        paths = [
            _extract_csv(path) if path.suffix.casefold() == ".zip" else path for path in self.parts
        ]
        missing = [str(path) for path in paths if not path.exists()]
        if missing:
            raise FileNotFoundError(f"snapshot part(s) not found: {', '.join(missing)}")
        return paths

    def scan(self) -> Any:
        """Return a full-width LazyFrame; callers choose projections and filters."""
        pl = _require_polars()
        return pl.scan_csv(
            self._csv_paths(),
            schema_overrides={COLUMNS["company_number"]: pl.String},
        )

    def head(self, n: int = 5) -> Any:
        """Collect only the first ``n`` rows for quick inspection."""
        return self.scan().head(n).collect()

    def columns(self) -> list[str]:
        """Return source column names without collecting snapshot rows."""
        return self.scan().collect_schema().names()
