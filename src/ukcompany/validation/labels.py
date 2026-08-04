"""Load and normalise Insolvency Service record-level labels.

The real CSV's ``is_bulk`` values are ``Y``, ``NA``, and blank (inspection
2026-08); only ``Y`` denotes a bulk case.  The filter is therefore deny-Y, not
allow-N: blank, NA, and any other non-Y representation remain eligible.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from ukcompany.validate import NormalisedNumber, normalise_company_number


@dataclass(frozen=True)
class Label:
    case_type: str
    raw_case_type: str


@dataclass
class LabelSet:
    labels: dict[str, Label] = field(default_factory=dict)
    input_rows: int = 0
    dropped_bulk: int = 0
    dropped_administration_to_cvl: int = 0
    unusable: list[NormalisedNumber] = field(default_factory=list)
    duplicate_rows: int = 0


def controlled_case_type(raw: str) -> str:
    """Collapse publication labels to stable reporting groups."""
    value = raw.strip().lower()
    if "compulsory" in value and "liquidat" in value:
        return "compulsory_liquidation"
    if ("creditor" in value or "cvl" in value) and "liquidat" in value:
        return "creditors_voluntary_liquidation"
    if "administration" in value:
        return "administration"
    if "voluntary arrangement" in value or value == "cva":
        return "corporate_voluntary_arrangement"
    return "other"


def _columns(fieldnames: list[str] | None) -> dict[str, str]:
    actual = {name.strip().lower(): name for name in (fieldnames or [])}
    required = {"company_number", "case_type", "is_bulk"}
    missing = required - actual.keys()
    if missing:
        raise ValueError(f"labels CSV missing required column(s): {', '.join(sorted(missing))}")
    return actual


def load_labels(path: str | Path) -> LabelSet:
    """Load labels, applying the publication's two mandatory exclusions."""
    result = LabelSet()
    # The 2024 publication contains arbitrary legacy high bytes (including
    # values invalid in UTF-8 and Windows-1252). Latin-1 is lossless for those
    # bytes; the three fields consumed below are ASCII-valued.
    with Path(path).open(newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle)
        columns = _columns(reader.fieldnames)
        for row in reader:
            result.input_rows += 1
            # Real publication encoding (inspected 2026-08): Y / NA / blank.
            # Only an explicit Y is bulk; an allow-N filter drops every row.
            if (row.get(columns["is_bulk"]) or "").strip().upper() == "Y":
                result.dropped_bulk += 1
                continue
            raw_type = (row.get(columns["case_type"]) or "").strip()
            if raw_type.casefold() == "administration to cvl".casefold():
                result.dropped_administration_to_cvl += 1
                continue
            normalised = normalise_company_number(row.get(columns["company_number"]))
            if not normalised.valid:
                result.unusable.append(normalised)
                continue
            assert normalised.number is not None
            if normalised.number in result.labels:
                result.duplicate_rows += 1
                continue
            result.labels[normalised.number] = Label(
                case_type=controlled_case_type(raw_type), raw_case_type=raw_type
            )
    return result
