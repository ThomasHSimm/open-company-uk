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

# Registered-society and royal-charter bodies have 8-character company numbers
# whose tail can contain LETTERS (e.g. IP00120C, R0000173, SP3COLLS) and so do
# not match the strict 8-digit / 2-letter+6-digit forms above. They are
# legitimate register entries and are retrievable through the API, but the main
# pipeline keeps rejecting them (widening the strict validator is out of scope).
# `is_registered_society_number` is an EXPLICIT, narrow allow-list used only
# where these bodies must be fetched (the prospective study), so genuinely
# malformed numbers still hard-fail. The prefix is the maximal leading A-Z run.
REGISTERED_SOCIETY_ROYAL_CHARTER_PREFIXES = {
    "IP",  # registered society (industrial & provident society), England & Wales
    "SP",  # registered society, Scotland
    "NP",  # registered society, Northern Ireland
    "RS",  # registered society (post-2014 designation)
    "SL",  # Scottish registered-society / mutual 8-char form (not the SL+6-digit SLP)
    "R",   # royal charter / mutual series (R + 7 characters)
    "RC",  # royal charter body, England & Wales
    "SR",  # royal charter body, Scotland
    "NR",  # royal charter body, Northern Ireland
}

_SOCIETY_SHAPE = re.compile(r"^([A-Z]{1,2})[0-9A-Z]+$")


def is_registered_society_number(raw: object) -> bool:
    """True if `raw` is an 8-char registered-society / royal-charter number.

    Narrow by design: exactly 8 characters, alphanumeric, with a recognised
    society/charter prefix. Does not touch `normalise_company_number`.
    """
    if raw is None:
        return False
    s = str(raw).strip().upper().replace(" ", "")
    if len(s) != 8:
        return False
    m = _SOCIETY_SHAPE.match(s)
    return bool(m) and m.group(1) in REGISTERED_SOCIETY_ROYAL_CHARTER_PREFIXES


def society_fetch_key(raw: object) -> str:
    """Normalised fetch string for a society/charter number (upper, no spaces)."""
    return str(raw).strip().upper().replace(" ", "")


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
