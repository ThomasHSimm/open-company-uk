"""ixbrlparse-based extraction for plain-XML Companies House filings (Phase C of the
accounts-parser v2 fix).

core.py's regex-based extract_filing only recognises inline XBRL (iXBRL — HTML-hosted,
`<ix:nonFraction>`/`<ix:nonNumeric>` elements). A plain XBRL instance document (a `.xml`
member — ~301,141 filings archive-wide, 0.84% of the archive, mostly 2013-2014 vintage) has
no inline markup for core.py's regexes to match at all; every one of these was previously
skipped outright (extract.py's `xml_skipped` counter). This module routes exactly those
members through `ixbrlparse` instead, converting its output into the SAME `FactObservation`
schema core.py produces, so downstream code (storage, WIDE pivot, comparisons) never needs
to know which parser produced a given row — except via the `parser` provenance field this
module always sets to "ixbrlparse" (core.py's own extract_filing defaults it to "ours").

Isolated in its own module rather than folded into core.py because it is the only part of
this package with an external dependency (`ixbrlparse`); core.py stays stdlib-only.

Two things confirmed by reading ixbrlparse's own source before writing this (not assumed):

1. Scale and sign are ALREADY APPLIED. `ixbrlparse.components._base.ixbrlFormat.parse_value`
   (which every format transform class either uses directly or calls via `super()`)
   multiplies by `10 ** scale` and negates for a "-" sign internally, returning the final
   resolved number — unlike core.py's own `FactObservation`, where `numeric_value` is
   likewise the fully-resolved value but `scale`/`sign` are ALSO kept as separate audit
   fields recording the original attributes. This module follows the same convention:
   `numeric_value` comes straight from `fact.value` (already resolved — never re-scaled here,
   which would silently double-apply it), while `scale`/`sign` are read off `fact.format`
   purely for provenance, matching core.py's own raw_value/scale/sign/numeric_value shape.

2. `ixbrlContext.segments` is a flat list built from BeautifulSoup's `findChildren()` over
   the `<segment>` element — which walks ALL descendants, not just direct children. For a
   typedMember context this means TWO entries appear for one dimension: the `typedMember`
   tag itself (carrying the `dimension` attribute and, because `.text` concatenates
   descendant text, also the typed value) AND a second entry for its own child domain
   element (same value, no `dimension` attribute). Confirmed on real filings
   (`Prod224_2266_09144549_20230731.html`, `Prod224_0050_09827898_20171031.html`) — the
   second entry must be ignored, or a genuinely single typed dimension would misclassify as
   two, or worse, get treated as an extra explicit member. `_classify_segments` below filters
   to `explicitMember`/`typedMember` tags only and checks for typedMember's PRESENCE, not
   its count, mirroring core.py's own `extract_contexts` priority (typed beats multi-member
   beats single-member).
"""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation

from .core import (
    COMPANY_CONCEPT,
    TARGET_SET,
    ContextKind,
    ContextPeriod,
    ExtractedFiling,
    IntegrityCounts,
    _CandidateFact,
    _emit_group,
    _resolve_legacy_fallbacks,
    local_name,
    normalise_scope,
)

PARSER_NAME = "ixbrlparse"


def _classify_segments(
    segments: list[dict] | None,
) -> tuple[ContextKind, str | None, str | None]:
    segments = segments or []
    if any(segment.get("tag") == "typedMember" for segment in segments):
        return ContextKind.TYPED, None, None
    explicit = [segment for segment in segments if segment.get("tag") == "explicitMember"]
    if len(explicit) >= 2:
        return ContextKind.MULTI_MEMBER, None, None
    if len(explicit) == 1:
        dimension = local_name(explicit[0].get("dimension") or "") or None
        member = local_name(explicit[0].get("value") or "") or None
        return ContextKind.SINGLE_MEMBER, dimension, member
    return ContextKind.NON_DIMENSIONAL, None, None


def _numeric_value_str(value: object) -> str | None:
    """ixbrlparse's fact.value is always a Python float (even for whole numbers — its own
    base parse_value does `float(value.replace(...))`), so str(value) always carries a
    trailing ".0" ("2630.0"). core.py's own numeric_value never does ("2630"), since it
    starts from Decimal(raw_text) with no fractional part to begin with. Collapsing an
    exact-integer float back to its integral form keeps the two parsers' output
    representationally consistent in the combined LONG dataset."""
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    integral = decimal_value.to_integral_value()
    if decimal_value == integral:
        decimal_value = integral
    return format(decimal_value, "f")


def _is_currency(measure: str | None) -> bool:
    return bool(measure) and len(measure) == 3 and measure.isalpha() and measure.isupper()


def extract_filing_xml(
    data: bytes,
    company: str,
    made_up_to_date: str,
    *,
    scope: str = "all",
    kinds: str = "all",
) -> ExtractedFiling:
    """Same signature and return shape as core.extract_filing, for a plain-XBRL `.xml`
    member instead of an iXBRL `.html`/`.htm` one."""
    from ixbrlparse import IXBRL
    from ixbrlparse.core import IXBRLParseError

    concepts = normalise_scope(scope)
    if kinds not in {"all", "numeric-only"}:
        raise ValueError("kinds must be 'all' or 'numeric-only'")

    try:
        result = IXBRL(io.StringIO(data.decode("utf-8", errors="replace")))
    except IXBRLParseError as exc:
        # Re-raised as ValueError so extract.py's process_archive can catch every parser's
        # failures the same way (OSError, RuntimeError, ValueError, zipfile.BadZipFile)
        # without needing to import an ixbrlparse-specific exception type itself — the
        # dependency stays encapsulated in this module alone.
        raise ValueError(f"ixbrlparse failed: {exc}") from exc
    integrity = IntegrityCounts()
    tagged_companies: set[str] = set()
    groups: dict[tuple[str, str, str, str | None, str | None], list[_CandidateFact]] = {}
    legacy_groups: dict[
        tuple[str, str], list[tuple[bool, str, str | None, int, str | None, str | None]]
    ] = {}
    observed_periods: set[str] = set()

    all_facts = [(True, fact) for fact in result.numeric] + [
        (False, fact) for fact in result.nonnumeric
    ]
    for fact_sequence, (is_numeric, fact) in enumerate(all_facts):
        concept = local_name(fact.name or "")
        fact_kind = "numeric" if is_numeric else "non-numeric"
        raw_value = "" if fact.text is None else str(fact.text)
        if concept == COMPANY_CONCEPT and raw_value:
            tagged_companies.add(raw_value)
        if not concept or (concepts is not None and concept not in concepts):
            continue
        if kinds == "numeric-only" and fact_kind != "numeric":
            continue
        integrity.facts_seen += 1

        ctx = fact.context
        instant = getattr(ctx, "instant", None)
        enddate = getattr(ctx, "enddate", None)
        if ctx is None or (instant is None and enddate is None):
            integrity.bad_period_refs += 1
            continue
        period_end = str(instant or enddate)
        observed_periods.add(period_end)
        context_kind = "instant" if instant is not None else "duration"
        member_kind, dimension, member = _classify_segments(getattr(ctx, "segments", None))

        fmt = getattr(fact, "format", None)
        scale = int(getattr(fmt, "scale", 0) or 0) if fmt is not None else 0
        # ixbrlFormat defaults sign to "" (not None) when the attribute is absent — collapse
        # to None to match core.py's own `attrs.get("sign") or None` convention.
        sign = (getattr(fmt, "sign", None) or None) if fmt is not None else None
        numeric_value = _numeric_value_str(fact.value) if is_numeric else None

        unit: str | None = None
        currency: str | None = None
        if is_numeric:
            raw_unit = getattr(fact, "unit", None)
            unit_local = local_name(raw_unit) if raw_unit else None
            if unit_local and _is_currency(unit_local):
                currency = unit_local
            unit = currency or unit_local
            if not raw_unit:
                integrity.unresolved_unit_refs += 1
            elif currency and currency != "GBP":
                integrity.non_gbp_facts += 1

        if concept in TARGET_SET:
            legacy_groups.setdefault((concept, period_end), []).append(
                (
                    member_kind == ContextKind.NON_DIMENSIONAL,
                    raw_value,
                    numeric_value,
                    scale,
                    sign,
                    currency,
                )
            )

        if member_kind == ContextKind.MULTI_MEMBER:
            integrity.skipped_multimember += 1
            continue
        if member_kind == ContextKind.TYPED:
            integrity.skipped_typed += 1
            continue

        context = ContextPeriod(period_end, member_kind, dimension, member, context_kind)
        candidate = _CandidateFact(
            concept,
            fact_kind,
            fact_sequence,
            context,
            raw_value,
            scale,
            sign,
            numeric_value,
            unit,
            currency,
        )
        key = (concept, period_end, context_kind, dimension, member)
        groups.setdefault(key, []).append(candidate)

    current_period = max(observed_periods, default="")
    observations = []
    for candidates in groups.values():
        _emit_group(candidates, observations, integrity, current_period, PARSER_NAME)
    legacy_fallbacks = _resolve_legacy_fallbacks(legacy_groups)
    integrity.assert_closes()
    return ExtractedFiling(
        company,
        made_up_to_date,
        frozenset(tagged_companies),
        tuple(observations),
        tuple(legacy_fallbacks),
        integrity,
    )
