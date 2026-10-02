"""Nature-of-control enumeration and decomposition - the single source of truth.

Companies House records each PSC's control as verbatim "nature of control" codes,
e.g. ``ownership-of-shares-25-to-50-percent`` or
``voting-rights-50-to-75-percent-limited-liability-partnership``. The per-company
derive path (``derive.derive_psc``) and the bulk-snapshot loader
(``feature/psc-loader``'s DuckDB ``psc_noc`` query) both need to split these the
same way; this module is the ONE place that enumerates and decomposes them so the
two paths cannot silently drift (the DuckDB path mirrors these constants in SQL -
keep them aligned when that branch merges).

Codes are matched VERBATIM against Companies House's published enumeration: the
``description:`` section of ``psc_descriptions.yml`` in companieshouse/api-
enumerations lists the 86 nature-of-control codes. (The file's SEPARATE
``statement_description:`` section holds the statement codes, handled by
``rules.PSC_UNRESOLVED_STATEMENT_CODES`` - two different sections of one file.)
Decomposition is validated against all 86 vendored codes in
``tests/fixtures/psc_descriptions_natures.yml`` (commit ``0d3fb78``); any code whose
core right is not recognised is returned in ``unmapped`` rather than guessed at.

Nothing here reads names, nationality or any personal field - only the control
codes, the item ``kind``, and (for corporate PSCs) the company-identifier fields.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .validate import normalise_company_number

# Entity-type suffix variants, INCLUDING the compound forms (a trust/firm holding via
# an LLP, or ROE control-over-trust/firm). The un-suffixed form is "plain".
# decompose_nature strips the LONGEST matching suffix, so a compound is never
# half-stripped into the wrong core (the bug the first version had). NB the bulk loader
# (feature/psc-loader) currently lists only the four single suffixes and must be aligned
# to THIS set before the two mappings are merged into one.
NOC_SUFFIXES = (
    "-as-control-over-trust-registered-overseas-entity",
    "-as-control-over-firm-registered-overseas-entity",
    "-as-trust-limited-liability-partnership",
    "-as-firm-limited-liability-partnership",
    "-as-trust-registered-overseas-entity",
    "-as-firm-registered-overseas-entity",
    "-limited-liability-partnership",
    "-registered-overseas-entity",
    "-as-trust",
    "-as-firm",
)
SUFFIXES_LONGEST_FIRST = tuple(sorted(NOC_SUFFIXES, key=len, reverse=True))

# Rankable ownership/voting bands, in increasing order of control, used to pick a single
# "maximum" band per company. ROE codes phrase their threshold as "more-than-25-percent":
# decompose_nature CAPTURES that as the band value (so it is not lost), but it is
# deliberately NOT ranked here - it is not ordinally comparable to the "-to-" bands - so
# an ROE-only holding yields a maximum band of None.
OWNERSHIP_BANDS = ("25-to-50-percent", "50-to-75-percent", "75-to-100-percent")
_BAND_RANK = {band: rank for rank, band in enumerate(OWNERSHIP_BANDS, start=1)}
# Public so the bulk-snapshot loader can build its DuckDB `regexp_extract` from the SAME
# pattern instead of hardcoding its own copy (single source of truth for the band form).
BAND_PATTERN = r"(\d+-to-\d+-percent|more-than-\d+-percent)"
_BAND_RE = re.compile(BAND_PATTERN)

# Core rights recognised after suffix and band are stripped. Only the first four drive
# features (bands / appointment / influence); the remainder are recognised so they are
# NOT reported as unmapped, but they intentionally drive no feature. Both `part-` and
# plain `right-to-share-surplus-assets` are real enumeration forms;
# `registered-owner-as-nominee` is the ROE nominee family (jurisdiction infix, no band).
CORE_PREFIXES = {
    "ownership-of-shares-": "ownership-of-shares",
    "voting-rights-": "voting-rights",
    "right-to-appoint-and-remove-": "right-to-appoint-and-remove",
    "part-right-to-share-surplus-assets-": "part-right-to-share-surplus-assets",
    "right-to-share-surplus-assets-": "right-to-share-surplus-assets",
    "registered-owner-as-nominee-": "registered-owner-as-nominee",
}
CORE_EXACT = {"significant-influence-or-control": "significant-influence-or-control"}

# Per-company API PSC item `kind` values -> coarse category. Beneficial-owner
# variants (registered-overseas-entity regime) map onto the same base category so
# ROE ownership is not dropped from the counts. Anything unrecognised -> "other".
KIND_TO_CATEGORY = {
    "individual-person-with-significant-control": "individual",
    "individual-beneficial-owner": "individual",
    "corporate-entity-person-with-significant-control": "corporate",
    "corporate-entity-beneficial-owner": "corporate",
    "legal-person-person-with-significant-control": "legal-person",
    "legal-person-beneficial-owner": "legal-person",
    "super-secure-person-with-significant-control": "super-secure",
    "super-secure-beneficial-owner": "super-secure",
}
KIND_CATEGORIES = ("individual", "corporate", "legal-person", "super-secure")


@dataclass(frozen=True)
class NatureParts:
    """One decomposed nature-of-control code."""

    raw: str
    core: str | None  # recognised core right, or None if unmapped
    suffix_family: str  # "plain" / "as-firm" / "as-trust" / "limited-liability-partnership" / ...
    band: str | None  # "25-to-50-percent" etc., or None


def decompose_nature(raw: str) -> NatureParts:
    """Split a verbatim nature code into (core right, suffix family, band).

    Mirrors the bulk loader: strip a known entity-type suffix, then read the
    ``N-to-M-percent`` band if present, then match the remaining core right. An
    unrecognised core right yields ``core=None`` (caller counts it as unmapped) -
    we never guess.
    """
    suffix_family = "plain"
    base = raw
    for suffix in SUFFIXES_LONGEST_FIRST:
        if raw.endswith(suffix):
            suffix_family = suffix.lstrip("-")
            base = raw[: -len(suffix)]
            break

    band_match = _BAND_RE.search(base)
    band = band_match.group(1) if band_match else None

    core: str | None = None
    if base in CORE_EXACT:
        core = CORE_EXACT[base]
    else:
        for prefix, name in CORE_PREFIXES.items():
            if base.startswith(prefix):
                core = name
                break
    return NatureParts(raw=raw, core=core, suffix_family=suffix_family, band=band)


def _max_band(bands: Iterable[str | None]) -> str | None:
    ranked = [(b, _BAND_RANK[b]) for b in bands if b in _BAND_RANK]
    return max(ranked, key=lambda pair: pair[1])[0] if ranked else None


@dataclass(frozen=True)
class NatureSummary:
    max_ownership_band: str | None
    max_voting_band: str | None
    has_appointment_rights: bool
    has_significant_influence: bool
    n_distinct_natures: int
    unmapped: tuple[str, ...]  # distinct codes whose core right was not recognised


def summarise_natures(natures: Iterable[str]) -> NatureSummary:
    """Structured features over a set of verbatim nature codes.

    ``natures`` should already be scoped to the records the caller wants (the
    derive path passes ACTIVE PSC records only). Distinctness is over the raw
    codes. ``has_appointment_rights`` covers the whole
    ``right-to-appoint-and-remove-*`` family (directors, LLP members, firm/trust
    persons), not directors alone - documented in FIELD_DOCS.
    """
    distinct = sorted(set(natures))
    ownership_bands: list[str | None] = []
    voting_bands: list[str | None] = []
    has_appointment = False
    has_influence = False
    unmapped: list[str] = []
    for raw in distinct:
        parts = decompose_nature(raw)
        if parts.core is None:
            unmapped.append(raw)
            continue
        if parts.core == "ownership-of-shares":
            ownership_bands.append(parts.band)
        elif parts.core == "voting-rights":
            voting_bands.append(parts.band)
        elif parts.core == "right-to-appoint-and-remove":
            has_appointment = True
        elif parts.core == "significant-influence-or-control":
            has_influence = True
    return NatureSummary(
        max_ownership_band=_max_band(ownership_bands),
        max_voting_band=_max_band(voting_bands),
        has_appointment_rights=has_appointment,
        has_significant_influence=has_influence,
        n_distinct_natures=len(distinct),
        unmapped=tuple(unmapped),
    )


def classify_kind(kind: str | None) -> str:
    """Coarse PSC category from a per-company API item ``kind`` (or "other")."""
    return KIND_TO_CATEGORY.get(kind or "", "other")


def is_uk_company_number_format(registration_number: object) -> bool:
    """True when a corporate PSC's registration number normalises to a valid CH
    company number (8 digits or a 2-letter prefix + 6 digits).

    Reuses ``validate.normalise_company_number`` - the project's single company-
    number acceptance rule - so this "would it join the register?" check and input
    validation can never diverge. Note that normaliser zero-pads short all-digit
    values, so a short foreign numeric id can read as UK-format; this is a format
    gate, not proof the company exists (see FIELD_DOCS caveat).
    """
    if registration_number is None:
        return False
    return normalise_company_number(registration_number).number is not None
