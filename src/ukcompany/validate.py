"""Company number validation and normalisation.

CH company numbers are 8 characters: either 8 digits (England & Wales) or a
2-letter prefix + 6 digits (SC Scotland, NI Northern Ireland, OC E&W LLP, ...).

The critical failure mode this module defends against: numbers that passed
through Excel/CSV-as-integer lose their leading zeros. That loss is
NON-RANDOM - it hits digit-only (English/Welsh) numbers and spares prefixed
ones, so silent 404s would bias any downstream analysis by jurisdiction.
Hence: normalise what is unambiguously fixable, record that it was fixed,
hard-fail the rest with a report. Never silently drop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Common registered prefixes. Deliberately not exhaustive (CH has many rare
# ones); unknown 2-letter prefixes are accepted with a warning rather than
# rejected, because rejecting a real rare prefix is worse than warning.
KNOWN_PREFIXES = {
    "SC",  # Scotland
    "NI",  # Northern Ireland
    "OC",  # E&W LLP
    "SO",  # Scottish LLP
    "NC",  # NI LLP
    "FC",  # overseas company
    "SF",  # overseas (Scotland)
    "NF",  # overseas (NI)
    "CE",  # charitable incorporated organisation (E&W)
    "CS",  # Scottish charitable incorporated organisation
    "IP",  # industrial & provident
    "SP",  # Scottish industrial & provident
    "RS",  # registered society
    "SL",  # Scottish limited partnership
    "LP",  # limited partnership (E&W)
    "NL",  # NI limited partnership
    "RC",  # royal charter
    "SR",  # Scottish royal charter
    "GE",  # European economic interest grouping (historic)
}

_DIGITS = re.compile(r"^\d{1,8}$")
_PREFIXED = re.compile(r"^([A-Z]{2})(\d{1,6})$")


@dataclass(frozen=True)
class NormalisedNumber:
    raw: str
    number: str | None  # normalised 8-char number, None if invalid
    status: str  # "ok" | "fixed" | "invalid"
    note: str = ""

    @property
    def valid(self) -> bool:
        return self.number is not None


def normalise_company_number(raw: object) -> NormalisedNumber:
    """Normalise a single company number. Never raises; returns a status record."""
    if raw is None:
        return NormalisedNumber(raw="", number=None, status="invalid", note="empty value")
    s = str(raw).strip().upper().replace(" ", "")
    if s in ("", "NAN", "NONE", "NULL"):
        return NormalisedNumber(raw=str(raw), number=None, status="invalid", note="empty value")

    # Excel float damage: "1234567.0"
    if s.endswith(".0") and _DIGITS.match(s[:-2] or ""):
        s = s[:-2]
        note_float = "stripped trailing .0 (spreadsheet float); "
    else:
        note_float = ""

    if _DIGITS.match(s):
        if len(s) == 8:
            return NormalisedNumber(
                raw=str(raw), number=s, status="ok", note=note_float.strip("; ")
            )
        padded = s.zfill(8)
        return NormalisedNumber(
            raw=str(raw),
            number=padded,
            status="fixed",
            note=note_float + f"zero-padded {len(s)}->8 digits (likely spreadsheet damage)",
        )

    m = _PREFIXED.match(s)
    if m:
        prefix, digits = m.groups()
        fixed = len(digits) < 6
        number = prefix + digits.zfill(6)
        notes = []
        if note_float:
            notes.append(note_float.strip("; "))
        if fixed:
            notes.append(f"zero-padded digit part {len(digits)}->6")
        if prefix not in KNOWN_PREFIXES:
            notes.append(f"unrecognised prefix '{prefix}' - accepted, verify manually")
        return NormalisedNumber(
            raw=str(raw),
            number=number,
            status="fixed" if fixed else "ok",
            note="; ".join(notes),
        )

    return NormalisedNumber(
        raw=str(raw),
        number=None,
        status="invalid",
        note="does not match 8-digit or 2-letter+6-digit format",
    )


@dataclass
class ValidationReport:
    ok: list[NormalisedNumber]
    fixed: list[NormalisedNumber]
    invalid: list[NormalisedNumber]
    duplicates: list[str]

    @property
    def numbers(self) -> list[str]:
        """Deduplicated normalised numbers, input order preserved."""
        seen: set[str] = set()
        out: list[str] = []
        for r in [*self.ok, *self.fixed]:
            assert r.number is not None
            if r.number not in seen:
                seen.add(r.number)
                out.append(r.number)
        return out

    def summary(self) -> str:
        lines = [
            f"input rows: {len(self.ok) + len(self.fixed) + len(self.invalid)}",
            f"ok: {len(self.ok)}  fixed: {len(self.fixed)}  invalid: {len(self.invalid)}  "
            f"duplicates: {len(self.duplicates)}",
        ]
        for r in self.fixed:
            lines.append(f"  FIXED   {r.raw!r} -> {r.number}  ({r.note})")
        for r in self.invalid:
            lines.append(f"  INVALID {r.raw!r}  ({r.note})")
        for d in self.duplicates:
            lines.append(f"  DUP     {d}")
        return "\n".join(lines)


def validate_input(raw_numbers: list[object]) -> ValidationReport:
    results = [normalise_company_number(x) for x in raw_numbers]
    ok = [r for r in results if r.status == "ok"]
    fixed = [r for r in results if r.status == "fixed"]
    invalid = [r for r in results if r.status == "invalid"]
    seen: set[str] = set()
    duplicates: list[str] = []
    for r in [*ok, *fixed]:
        assert r.number is not None
        if r.number in seen:
            duplicates.append(r.number)
        seen.add(r.number)
    return ValidationReport(ok=ok, fixed=fixed, invalid=invalid, duplicates=duplicates)
