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
IX_FACT_RE = re.compile(
    rb"<\s*ix:(nonFraction|nonNumeric)\b([^>]*?)(?:/\s*>|>(.*?)</\s*ix:\1\s*>)",
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


def normalise_number(raw: str, scale: int, sign: str = "") -> str | None:
    """Convert common iXBRL numeric presentations to a scaled decimal string."""
    value = raw.strip()
    if not value or value in {"-", "—", "–"}:
        return None
    negative = value.startswith("(") and value.endswith(")")
    cleaned = value.strip("()").replace(",", "").replace(" ", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if negative:
        number = -number
    if sign.strip() == "-":
        number = -abs(number)
    number *= Decimal(10) ** scale
    return format(number, "f")


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
    )


def _emit_group(
    candidates: list[_CandidateFact],
    observations: list[FactObservation],
    integrity: IntegrityCounts,
    current_period: str,
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
            _observation(candidate, status, current_period) for candidate in candidates
        )
        return
    if first.context.kind == ContextKind.NON_DIMENSIONAL:
        integrity.kept_total += 1
    else:
        integrity.kept_member += 1
    integrity.collapsed_duplicate += len(candidates) - 1
    observations.append(_observation(first, "selected", current_period))


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

    for fact_sequence, (raw_tag, raw_attrs, body) in enumerate(IX_FACT_RE.findall(data)):
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
        numeric_value = (
            normalise_number(raw_value, scale, sign or "")
            if fact_kind == "numeric"
            else None
        )
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
    integrity.assert_closes()
    return ExtractedFiling(
        company,
        made_up_to_date,
        frozenset(tagged_companies),
        tuple(observations),
        tuple(legacy_fallbacks),
        integrity,
    )
