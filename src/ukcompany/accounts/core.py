"""Tolerant iXBRL fact extraction for Companies House accounts filings."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum

TARGET_CONCEPTS = (
    "Equity",
    "NetCurrentAssetsLiabilities",
    "CurrentAssets",
    "Creditors",
    "CashBankOnHand",
    "Debtors",
    "PropertyPlantEquipment",
    "TotalAssetsLessCurrentLiabilities",
    "AverageNumberEmployeesDuringPeriod",
)
TARGET_SET = frozenset(TARGET_CONCEPTS)
EMPLOYEE_CONCEPT = "AverageNumberEmployeesDuringPeriod"
COMPANY_CONCEPT = "UKCompaniesHouseRegisteredNumber"

# A numeric fact filed as a bare dash means nil, not "no value" — downstream pivot and
# restatement computations treat it as 0 rather than excluding it (see
# docs/accounts-wide-rebuild-verification.md). Covers the plain hyphen and the two dash
# characters filing software commonly substitutes for it. Extraction (Stage 1) is
# unaffected: `numeric_value` stays `None` for these facts in the LONG archive exactly as
# read; this constant is only consumed downstream, at pivot/restatement time.
NIL_RAW_VALUES = ("-", "–", "—")

CONTEXT_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?context\b([^>]*)>(.*?)</\s*(?:[\w.-]+:)?context\s*>",
    re.I | re.S,
)
PERIOD_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?(instant|endDate)\b[^>]*>(.*?)</",
    re.I | re.S,
)
EXPLICIT_MEMBER_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?explicitMember\b([^>]*)>(.*?)</",
    re.I | re.S,
)
TYPED_MEMBER_RE = re.compile(rb"<\s*(?:[\w.-]+:)?typedMember\b", re.I)
UNIT_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?unit\b([^>]*)>(.*?)</\s*(?:[\w.-]+:)?unit\s*>",
    re.I | re.S,
)
MEASURE_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?measure\b[^>]*>(.*?)</",
    re.I | re.S,
)
# Matches the inline-XBRL namespace declaration regardless of which prefix a filing binds
# it to — `xmlns:ix="..."`, `xmlns:xbrli="..."`, or the bare default-namespace form
# `xmlns="..."` with no prefix at all. This is the namespace URI itself, not a local-name
# guess, so it can't collide with an unrelated element (e.g. an HTML5 <header> tag) the way
# a bare "header" wildcard would. Quote-agnostic like ATTR_RE below (`(['"])...\1`) — early
# CH filing software (2013-14 vintage observed live) wrote `xmlns:ix='...'` with single
# quotes; a double-quote-only pattern here silently misses it, exactly the kind of blind
# spot this whole audit exists to catch — found via a real false-negative on a 2014 filing.
IX_NAMESPACE_RE = re.compile(
    rb"""xmlns(?::[\w.-]+)?\s*=\s*(['"])http://www\.xbrl\.org/\d{4}/inlineXBRL\1""",
    re.I,
)
# Prior versions of this regex hardcoded the literal `ix:` prefix, so any filing that bound
# the inline-XBRL namespace to a different prefix — or to the default namespace with no
# prefix at all — silently extracted zero facts. Fixed the same way CONTEXT_RE/UNIT_RE/etc.
# below already handle prefixes: an optional, wildcard `(?:[\w.-]+:)?` local-name match,
# applied independently to the opening and closing tag (a document using mismatched
# prefixes at open/close is already malformed XML; matching each independently is a
# reasonable relaxation of the old exact-`ix:`-on-both-ends requirement, not a new gap).
IX_FACT_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?(nonFraction|nonNumeric)\b([^>]*?)"
    rb"(?:/\s*>|>(.*?)</\s*(?:[\w.-]+:)?\1\s*>)",
    re.I | re.S,
)
ATTR_RE = re.compile(rb"([:\w.-]+)\s*=\s*(['\"])(.*?)\2", re.S)
TAG_RE = re.compile(rb"<[^>]+>")


class ContextKind(StrEnum):
    NON_DIMENSIONAL = "non-dimensional"
    SINGLE_MEMBER = "single-member"
    MULTI_MEMBER = "multi-member"
    TYPED = "typed"


@dataclass(frozen=True)
class ContextPeriod:
    period_end: str
    kind: ContextKind
    dimension: str | None = None
    member: str | None = None
    context_kind: str = "instant"


@dataclass(frozen=True)
class FactObservation:
    concept: str
    fact_kind: str
    fact_sequence: int
    status: str
    period_end: str
    context_kind: str
    raw_value: str
    scale: int
    sign: str | None
    numeric_value: str | None
    dimension: str | None
    member: str | None
    unit: str | None
    currency: str | None
    is_current: bool
    # Provenance (Phase C, accounts-parser v2): which extractor produced this row. Defaults
    # to "ours" so the one existing call site (_observation, for iXBRL filings) needs no
    # change; xml_adapter.py's plain-XML path is the only caller that ever passes
    # "ixbrlparse" explicitly.
    parser: str = "ours"


@dataclass(frozen=True)
class LegacyFallback:
    """Dimensional-only value the reconnaissance code labelled as a total."""

    concept: str
    period_end: str
    numeric_value: str | None
    raw_value: str
    scale: int
    sign: str | None
    currency: str | None


@dataclass
class IntegrityCounts:
    facts_seen: int = 0
    kept_total: int = 0
    kept_member: int = 0
    collapsed_duplicate: int = 0
    ambiguous_nondimensional: int = 0
    member_value_conflict: int = 0
    skipped_multimember: int = 0
    skipped_typed: int = 0
    bad_period_refs: int = 0
    non_gbp_facts: int = 0
    unresolved_unit_refs: int = 0
    # A filing that declares the inline-XBRL namespace (any prefix, or the default
    # namespace) but for which IX_FACT_RE finds zero nonFraction/nonNumeric elements at
    # all. Deliberately excluded from accounted()/closes(): it is a filing-level flag (0 or
    # 1), not a fact-level count, and facts_seen is legitimately 0 for it too — including it
    # in the invariant would just make that case look "accounted for" instead of flagged.
    # This must never be read as "clean, no relevant facts" — it means extraction found
    # nothing at all despite genuine ix markup, which is exactly the prefix bug's signature.
    zero_fact_ixbrl_filings: int = 0
    # A numeric (nonFraction) fact whose `format` attribute names a Transformation Registry
    # family this module doesn't implement (nether the dot-decimal nor comma-decimal nor
    # nil-like families normalise_number recognises). Deliberately excluded from
    # accounted()/closes() for the same reason as zero_fact_ixbrl_filings above: it is an
    # ADDITIONAL diagnostic on a fact that is still classified normally (kept_total,
    # kept_member, etc.) via the usual grouping logic — it just carries numeric_value=None
    # rather than a guessed value, per the "never guess at an unrecognised format" rule.
    unrecognised_numeric_format: int = 0

    def accounted(self) -> int:
        return (
            self.kept_total
            + self.kept_member
            + self.collapsed_duplicate
            + self.ambiguous_nondimensional
            + self.member_value_conflict
            + self.skipped_multimember
            + self.skipped_typed
            + self.bad_period_refs
        )

    def closes(self) -> bool:
        return self.accounted() == self.facts_seen

    def assert_closes(self) -> None:
        if not self.closes():
            raise AssertionError(
                f"fact accounting does not close: seen={self.facts_seen}, "
                f"accounted={self.accounted()}"
            )

    def __iadd__(self, other: IntegrityCounts) -> IntegrityCounts:
        for field in fields(self):
            setattr(self, field.name, getattr(self, field.name) + getattr(other, field.name))
        return self

    def as_dict(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass(frozen=True)
class ExtractedFiling:
    company: str
    made_up_to_date: str
    tagged_companies: frozenset[str]
    observations: tuple[FactObservation, ...]
    legacy_fallbacks: tuple[LegacyFallback, ...]
    integrity: IntegrityCounts


@dataclass(frozen=True)
class _CandidateFact:
    concept: str
    fact_kind: str
    fact_sequence: int
    context: ContextPeriod
    raw_value: str
    scale: int
    sign: str | None
    numeric_value: str | None
    unit: str | None
    currency: str | None

    def agreement_key(self) -> tuple[str, str | None, str]:
        value = self.numeric_value if self.numeric_value is not None else self.raw_value
        kind = "NUM" if self.numeric_value is not None else "RAW"
        return kind, self.unit, value


def local_name(qname: str) -> str:
    """Return a QName's namespace-independent local name."""
    return qname.rsplit(":", 1)[-1].rsplit("}", 1)[-1]


def parse_attrs(raw: bytes) -> dict[str, str]:
    return {
        key.decode("utf-8", "replace").lower(): value.decode("utf-8", "replace")
        for key, _quote, value in ATTR_RE.findall(raw)
    }


def text_content(raw: bytes) -> str:
    value = TAG_RE.sub(b"", raw).decode("utf-8", "replace")
    return html.unescape(value).replace("\u00a0", " ").strip()


def valid_date(value: str) -> str | None:
    candidate = value.strip()[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def extract_contexts(data: bytes) -> tuple[dict[str, ContextPeriod], int]:
    """Resolve contexts to periods and supported dimensional classifications."""
    contexts: dict[str, ContextPeriod] = {}
    invalid_periods = 0
    for raw_attrs, body in CONTEXT_RE.findall(data):
        context_id = parse_attrs(raw_attrs).get("id")
        period_match = PERIOD_RE.search(body)
        if not context_id or not period_match:
            continue
        period_end = valid_date(text_content(period_match.group(2)))
        if not period_end:
            invalid_periods += 1
            continue
        context_kind = (
            "instant" if period_match.group(1).lower() == b"instant" else "duration"
        )
        members = EXPLICIT_MEMBER_RE.findall(body)
        if TYPED_MEMBER_RE.search(body):
            context = ContextPeriod(
                period_end, ContextKind.TYPED, context_kind=context_kind
            )
        elif len(members) >= 2:
            context = ContextPeriod(
                period_end, ContextKind.MULTI_MEMBER, context_kind=context_kind
            )
        elif len(members) == 1:
            member_attrs, member_body = members[0]
            dimension = local_name(parse_attrs(member_attrs).get("dimension", "")) or None
            member = local_name(text_content(member_body)) or None
            context = ContextPeriod(
                period_end,
                ContextKind.SINGLE_MEMBER,
                dimension,
                member,
                context_kind,
            )
        else:
            context = ContextPeriod(
                period_end, ContextKind.NON_DIMENSIONAL, context_kind=context_kind
            )
        contexts[context_id] = context
    return contexts, invalid_periods


def extract_units(data: bytes) -> dict[str, str]:
    """Resolve unit IDs; compound units stay non-currency strings."""
    units: dict[str, str] = {}
    for raw_attrs, body in UNIT_RE.findall(data):
        unit_id = parse_attrs(raw_attrs).get("id")
        measures = [local_name(text_content(match)) for match in MEASURE_RE.findall(body)]
        if unit_id and measures:
            units[unit_id] = "/".join(measures)
    return units


# Transformation Registry format families this module can interpret on a numeric fact.
# Local names only (namespace prefix stripped, lowercased) — real filings bind these under
# "ixt:" or "ixt2:" depending on vintage, and this codebase treats prefixes as never
# load-bearing (see IX_FACT_RE's own history). numdotdecimal/numcommadot/numspacedot are the
# "dot is the decimal point" family, already handled correctly by unconditionally stripping
# "," and " " as digit-group separators. numdotcomma/numcomma/numspacecomma/numcommadecimal
# are the "comma is the decimal point" family — silently misread by a power of ten under the
# old unconditional-comma-strip logic, confirmed live against real markup
# (docs/accounts-parser-check.md §2: "1.234,56" / "1 234,56" both misread as ~100x too
# large). zerodash/numdash/fixedzero/nocontent/fixedempty are nil-like: their raw text is
# already almost always a literal dash handled by the NIL_RAW_VALUES check above, but
# recognising the format explicitly means a nil-like fact is never miscounted as
# "unrecognised" just because some filing renders it with different displayed text.
_DOT_DECIMAL_FORMATS = frozenset({"numdotdecimal", "numcommadot", "numspacedot"})
_COMMA_DECIMAL_FORMATS = frozenset(
    {"numdotcomma", "numcomma", "numspacecomma", "numcommadecimal"}
)
_NIL_LIKE_NUMERIC_FORMATS = frozenset(
    {"zerodash", "numdash", "fixedzero", "nocontent", "fixedempty"}
)
_KNOWN_NUMERIC_FORMATS = _DOT_DECIMAL_FORMATS | _COMMA_DECIMAL_FORMATS | _NIL_LIKE_NUMERIC_FORMATS


def normalise_format_name(local: str) -> str:
    """Strip punctuation-only variation between Transformation Registry naming
    conventions. Confirmed live in the real archive: `ixt2:num-dot-decimal` (hyphenated,
    528+12 occurrences) is the exact same format as `numdotdecimal` (357M+73M occurrences,
    the same registry family, no hyphens) — the original format-recognition code matched
    local names literally and treated the hyphenated spelling as unrecognised, silently
    nulling out numeric facts that had parsed correctly before the comma-decimal fix was
    even written. Only hyphens and underscores are stripped (not spaces — a real space
    inside a format name isn't a known convention and would be worth investigating, not
    silently swallowing)."""
    return local.replace("-", "").replace("_", "")


def normalise_number(
    raw: str, scale: int, sign: str = "", format_name: str | None = None
) -> tuple[str | None, bool]:
    """Convert common iXBRL numeric presentations to a scaled decimal string.

    Returns (numeric_value, format_recognised). format_recognised is False only when
    format_name is given and matches none of the families above — the value is still
    None in that case ("never guess" at an unknown format's semantics), but the caller
    must count it separately rather than let it look like an ordinary parse failure.
    format_name, if given, must already be the local name (prefix stripped, lowercased).
    """
    value = raw.strip()
    if not value or value in NIL_RAW_VALUES:
        return None, True
    if format_name is not None and format_name not in _KNOWN_NUMERIC_FORMATS:
        return None, False
    if format_name in _NIL_LIKE_NUMERIC_FORMATS:
        return None, True
    negative = value.startswith("(") and value.endswith(")")
    cleaned = value.strip("()")
    if format_name in _COMMA_DECIMAL_FORMATS:
        if format_name == "numdotcomma":
            cleaned = cleaned.replace(".", "")
        elif format_name == "numspacecomma":
            cleaned = cleaned.replace(" ", "")
        # numcomma / numcommadecimal define no digit-group separator at all — only the
        # decimal comma itself needs converting.
        cleaned = cleaned.replace(",", ".")
    else:
        # No format attribute, or the dot-decimal family: "," and " " are both digit-group
        # separators here, exactly the original unconditional-stripping behaviour.
        cleaned = cleaned.replace(",", "").replace(" ", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None, True
    if negative:
        number = -number
    if sign.strip() == "-":
        number = -abs(number)
    number *= Decimal(10) ** scale
    return format(number, "f"), True


def normalise_scope(scope: str | Collection[str]) -> frozenset[str] | None:
    """Return None for all concepts, otherwise a validated local-name set."""
    if isinstance(scope, str):
        if scope.strip().lower() == "all":
            return None
        values = [item.strip() for item in scope.split(",")]
    else:
        values = [str(item).strip() for item in scope]
    concepts = frozenset(item for item in values if item)
    if not concepts:
        raise ValueError("concept scope must be 'all' or a non-empty concept list")
    return concepts


def _is_currency_measure(measure: str | None) -> bool:
    return bool(measure and re.fullmatch(r"[A-Z]{3}", measure.upper()))


def _observation(
    candidate: _CandidateFact,
    status: str,
    current_period: str,
    parser: str = "ours",
) -> FactObservation:
    return FactObservation(
        candidate.concept,
        candidate.fact_kind,
        candidate.fact_sequence,
        status,
        candidate.context.period_end,
        candidate.context.context_kind,
        candidate.raw_value,
        candidate.scale,
        candidate.sign,
        candidate.numeric_value,
        candidate.context.dimension,
        candidate.context.member,
        candidate.unit,
        candidate.currency,
        candidate.context.period_end == current_period,
        parser,
    )


def _emit_group(
    candidates: list[_CandidateFact],
    observations: list[FactObservation],
    integrity: IntegrityCounts,
    current_period: str,
    parser: str = "ours",
) -> None:
    first = candidates[0]
    if len({candidate.agreement_key() for candidate in candidates}) != 1:
        if first.context.kind == ContextKind.NON_DIMENSIONAL:
            integrity.ambiguous_nondimensional += len(candidates)
            status = "conflict_nondimensional"
        else:
            integrity.member_value_conflict += len(candidates)
            status = "conflict_member"
        observations.extend(
            _observation(candidate, status, current_period, parser) for candidate in candidates
        )
        return
    if first.context.kind == ContextKind.NON_DIMENSIONAL:
        integrity.kept_total += 1
    else:
        integrity.kept_member += 1
    integrity.collapsed_duplicate += len(candidates) - 1
    observations.append(_observation(first, "selected", current_period, parser))


def _resolve_legacy_fallbacks(
    legacy_groups: dict[
        tuple[str, str], list[tuple[bool, str, str | None, int, str | None, str | None]]
    ],
) -> list[LegacyFallback]:
    """Shared between the iXBRL path (extract_filing) and the XML path
    (xml_adapter.extract_filing_xml) — audit-only, dimensional-value fallback for a target
    concept that never had a genuine non-dimensional total tagged."""
    legacy_fallbacks = []
    for (concept, period_end), candidates in legacy_groups.items():
        if any(item[0] for item in candidates):
            continue
        values = {
            ("NUM", numeric) if numeric is not None else ("RAW", raw)
            for _non_dimensional, raw, numeric, _scale, _sign, _currency in candidates
        }
        if len(values) == 1:
            _non_dimensional, raw, numeric, scale, sign, currency = candidates[0]
            legacy_fallbacks.append(
                LegacyFallback(concept, period_end, numeric, raw, scale, sign, currency)
            )
    return legacy_fallbacks


def extract_filing(
    data: bytes,
    company: str,
    made_up_to_date: str,
    *,
    scope: str | Collection[str] = "all",
    kinds: str = "all",
) -> ExtractedFiling:
    """Extract in-scope facts from one iXBRL filing and close fact accounting."""
    concepts = normalise_scope(scope)
    if kinds not in {"all", "numeric-only"}:
        raise ValueError("kinds must be 'all' or 'numeric-only'")
    contexts, _invalid_context_periods = extract_contexts(data)
    units = extract_units(data)
    integrity = IntegrityCounts()
    tagged_companies: set[str] = set()
    groups: dict[
        tuple[str, str, str, str | None, str | None], list[_CandidateFact]
    ] = defaultdict(list)
    legacy_groups: dict[
        tuple[str, str], list[tuple[bool, str, str | None, int, str | None, str | None]]
    ] = defaultdict(list)
    observed_periods: set[str] = set()

    raw_matches = IX_FACT_RE.findall(data)
    if not raw_matches and IX_NAMESPACE_RE.search(data):
        integrity.zero_fact_ixbrl_filings = 1

    for fact_sequence, (raw_tag, raw_attrs, body) in enumerate(raw_matches):
        attrs = parse_attrs(raw_attrs)
        concept = local_name(attrs.get("name", ""))
        raw_value = text_content(body)
        if concept == COMPANY_CONCEPT:
            if raw_value:
                tagged_companies.add(raw_value)
        fact_kind = "numeric" if raw_tag.lower() == b"nonfraction" else "non-numeric"
        if not concept or (concepts is not None and concept not in concepts):
            continue
        if kinds == "numeric-only" and fact_kind != "numeric":
            continue
        integrity.facts_seen += 1
        context = contexts.get(attrs.get("contextref", ""))
        if context is None:
            integrity.bad_period_refs += 1
            continue
        observed_periods.add(context.period_end)
        try:
            scale = int(attrs.get("scale", "0") or 0)
        except ValueError:
            scale = 0
        sign = attrs.get("sign") or None
        if fact_kind == "numeric":
            raw_format = attrs.get("format")
            format_name = (
                normalise_format_name(local_name(raw_format).lower()) if raw_format else None
            )
            numeric_value, format_recognised = normalise_number(
                raw_value, scale, sign or "", format_name
            )
            if not format_recognised:
                integrity.unrecognised_numeric_format += 1
        else:
            numeric_value = None
        unit_ref = attrs.get("unitref", "")
        measure = units.get(unit_ref)
        currency = measure.upper() if _is_currency_measure(measure) else None
        resolved_unit = currency or measure
        if concept in TARGET_SET:
            legacy_groups[(concept, context.period_end)].append(
                (
                    context.kind == ContextKind.NON_DIMENSIONAL,
                    raw_value,
                    numeric_value,
                    scale,
                    sign,
                    currency,
                )
            )
        if fact_kind == "numeric":
            if not unit_ref or measure is None:
                integrity.unresolved_unit_refs += 1
            elif currency and currency != "GBP":
                integrity.non_gbp_facts += 1
        if context.kind == ContextKind.MULTI_MEMBER:
            integrity.skipped_multimember += 1
            continue
        if context.kind == ContextKind.TYPED:
            integrity.skipped_typed += 1
            continue
        candidate = _CandidateFact(
            concept,
            fact_kind,
            fact_sequence,
            context,
            raw_value,
            scale,
            sign,
            numeric_value,
            resolved_unit,
            currency,
        )
        key = (
            concept,
            context.period_end,
            context.context_kind,
            context.dimension,
            context.member,
        )
        groups[key].append(candidate)

    current_period = max(observed_periods, default="")
    observations: list[FactObservation] = []
    for candidates in groups.values():
        _emit_group(candidates, observations, integrity, current_period)
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
