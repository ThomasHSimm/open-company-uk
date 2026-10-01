"""Load and normalise Insolvency Service record-level labels.

The real CSV's ``is_bulk`` values are ``Y``, ``NA``, and blank (inspection
2026-08); only ``Y`` denotes a bulk case.  The filter is therefore deny-Y, not
allow-N: blank, NA, and any other non-Y representation remain eligible.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from ukcompany.validate import NormalisedNumber, normalise_company_number

# A well-formed month_registered is exactly YYYY-MM. ~0.15% of publication rows
# have an unescaped comma in a text field (e.g. company_name), shifting every
# later column one place right - the tell is a non-date value (a case_type or
# register location) sitting in month_registered. Such rows carry the WRONG
# case_type/SIC too, so they are quarantined, never repaired (repairing = guessing
# where the comma was = silent mis-banding).
_VALID_MONTH = re.compile(r"^\d{4}-\d{2}$")
_SHIFTED_SAMPLE_LIMIT = 5

# SIC 2007 SECTION letter for each DIVISION (the 2-digit level), as published by
# ONS. A fixed lookup, not data-driven: (section, lowest division, highest
# division) inclusive. Divisions absent from any range (e.g. 04, 34, 40, 44)
# do not exist in SIC 2007 and resolve to "unknown".
_SECTION_RANGES: tuple[tuple[str, int, int], ...] = (
    ("A", 1, 3),  # Agriculture, forestry and fishing
    ("B", 5, 9),  # Mining and quarrying
    ("C", 10, 33),  # Manufacturing
    ("D", 35, 35),  # Electricity, gas, steam and air conditioning supply
    ("E", 36, 39),  # Water supply; sewerage, waste management and remediation
    ("F", 41, 43),  # Construction
    ("G", 45, 47),  # Wholesale and retail trade; repair of motor vehicles
    ("H", 49, 53),  # Transportation and storage
    ("I", 55, 56),  # Accommodation and food service activities
    ("J", 58, 63),  # Information and communication
    ("K", 64, 66),  # Financial and insurance activities
    ("L", 68, 68),  # Real estate activities
    ("M", 69, 75),  # Professional, scientific and technical activities
    ("N", 77, 82),  # Administrative and support service activities
    ("O", 84, 84),  # Public administration and defence; compulsory social security
    ("P", 85, 85),  # Education
    ("Q", 86, 88),  # Human health and social work activities
    ("R", 90, 93),  # Arts, entertainment and recreation
    ("S", 94, 96),  # Other service activities
    ("T", 97, 98),  # Activities of households as employers
    ("U", 99, 99),  # Activities of extraterritorial organisations and bodies
)


def sic_section_from_code(code: str | None) -> str:
    """Map a 1-or-2-digit SIC division code to its SIC-2007 section letter.

    The leading (up to two) digits are read as the division number and matched
    against the published section ranges. Blank, non-numeric, or a division
    outside every range yields ``"unknown"``. This single lookup is shared by
    the label side (raw Insolvency Service SIC) and the snapshot side, so both
    cohorts are sectioned identically.
    """
    digits = "".join(character for character in (code or "") if character.isdigit())
    if not digits:
        return "unknown"
    division = int(digits[:2])
    for section, low, high in _SECTION_RANGES:
        if low <= division <= high:
            return section
    return "unknown"


@dataclass(frozen=True)
class Label:
    case_type: str
    raw_case_type: str
    # Pre-distress structural covariates retained for stratified control drawing.
    # sic_section is the SIC-2007 section letter (or "unknown"); month_registered
    # is the raw incorporation month string from the publication (may be blank).
    sic_section: str = "unknown"
    month_registered: str = ""


@dataclass
class LabelSet:
    labels: dict[str, Label] = field(default_factory=dict)
    input_rows: int = 0
    dropped_bulk: int = 0
    dropped_administration_to_cvl: int = 0
    unusable: list[NormalisedNumber] = field(default_factory=list)
    duplicate_rows: int = 0
    unusable_shifted: int = 0
    shifted_samples: list[str] = field(default_factory=list)


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


def _optional(row: dict, columns: dict[str, str], key: str) -> str:
    """Read an optional column by its lower-cased name; blank when absent.

    Older/other publications lack the SIC and month columns, so these are never
    required - absence is tolerated exactly like a blank value.
    """
    source = columns.get(key)
    if source is None:
        return ""
    return (row.get(source) or "").strip()


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
            # Quarantine field-shifted rows before trusting case_type/SIC. When
            # the publication carries month_registered, a value that is not a
            # bare YYYY-MM month is the signature of an unescaped-comma column
            # shift; that row's case_type and SIC are wrong too, so it must never
            # become a label (and is never repaired - see _VALID_MONTH).
            month_registered = _optional(row, columns, "month_registered")
            if "month_registered" in columns and not _VALID_MONTH.match(month_registered):
                result.unusable_shifted += 1
                if len(result.shifted_samples) < _SHIFTED_SAMPLE_LIMIT:
                    result.shifted_samples.append(month_registered)
                continue
            if normalised.number in result.labels:
                result.duplicate_rows += 1
                continue
            # Retain pre-distress structural covariates when the publication
            # carries them. sic07_2_digit is the raw SIC division code (bare, not
            # the snapshot's "code - label" text); month_registered is the
            # incorporation-month proxy. Both are optional.
            sic_code = _optional(row, columns, "sic07_2_digit")
            result.labels[normalised.number] = Label(
                case_type=controlled_case_type(raw_type),
                raw_case_type=raw_type,
                sic_section=sic_section_from_code(sic_code),
                month_registered=month_registered,
            )
    return result
