"""Tolerant iXBRL fact extraction for Companies House accounts filings."""

from __future__ import annotations

import html
import re
from collections import defaultdict
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

CONTEXT_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?context\b([^>]*)>(.*?)</\s*(?:[\w.-]+:)?context\s*>",
    re.I | re.S,
)
PERIOD_RE = re.compile(
    rb"<\s*(?:[\w.-]+:)?(?:instant|endDate)\b[^>]*>(.*?)</",
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
    rb"<\s*ix:(?:nonFraction|nonNumeric)\b([^>]*)>(.*?)"
    rb"</\s*ix:(?:nonFraction|nonNumeric)\s*>",
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


@dataclass(frozen=True)
class FactObservation:
    concept: str
    period_end: str
    raw_value: str
    scale: int
    numeric_value: str | None
    dimension: str | None
    member: str | None
    currency: str | None
    is_current: bool


@dataclass(frozen=True)
class LegacyFallback:
    """Dimensional-only value the reconnaissance code labelled as a total."""

    concept: str
    period_end: str
    numeric_value: str | None
    raw_value: str


@dataclass
class IntegrityCounts:
    target_facts_seen: int = 0
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
        return self.accounted() == self.target_facts_seen

    def assert_closes(self) -> None:
        if not self.closes():
            raise AssertionError(
                f"fact accounting does not close: seen={self.target_facts_seen}, "
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
    context: ContextPeriod
    raw_value: str
    scale: int
    numeric_value: str | None
    currency: str | None

    def agreement_key(self) -> tuple[str, str | None, str]:
        value = self.numeric_value if self.numeric_value is not None else self.raw_value
        kind = "NUM" if self.numeric_value is not None else "RAW"
        return kind, self.currency, value


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
        period_end = valid_date(text_content(period_match.group(1)))
        if not period_end:
            invalid_periods += 1
            continue
        members = EXPLICIT_MEMBER_RE.findall(body)
        if TYPED_MEMBER_RE.search(body):
            context = ContextPeriod(period_end, ContextKind.TYPED)
        elif len(members) >= 2:
            context = ContextPeriod(period_end, ContextKind.MULTI_MEMBER)
        elif len(members) == 1:
            member_attrs, member_body = members[0]
            dimension = local_name(parse_attrs(member_attrs).get("dimension", "")) or None
            member = local_name(text_content(member_body)) or None
            context = ContextPeriod(
                period_end,
                ContextKind.SINGLE_MEMBER,
                dimension,
                member,
            )
        else:
            context = ContextPeriod(period_end, ContextKind.NON_DIMENSIONAL)
        contexts[context_id] = context
    return contexts, invalid_periods


def extract_units(data: bytes) -> dict[str, str]:
    """Resolve simple unit IDs to local measure names such as GBP or pure."""
    units: dict[str, str] = {}
    for raw_attrs, body in UNIT_RE.findall(data):
        unit_id = parse_attrs(raw_attrs).get("id")
        measure_match = MEASURE_RE.search(body)
        if unit_id and measure_match:
            units[unit_id] = local_name(text_content(measure_match.group(1)))
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
        else:
            integrity.member_value_conflict += len(candidates)
        return
    if first.context.kind == ContextKind.NON_DIMENSIONAL:
        integrity.kept_total += 1
    else:
        integrity.kept_member += 1
    integrity.collapsed_duplicate += len(candidates) - 1
    observations.append(
        FactObservation(
            first.concept,
            first.context.period_end,
            first.raw_value,
            first.scale,
            first.numeric_value,
            first.context.dimension,
            first.context.member,
            first.currency,
            first.context.period_end == current_period,
        )
    )


def extract_filing(data: bytes, company: str, made_up_to_date: str) -> ExtractedFiling:
    """Extract target facts from one iXBRL filing and close fact accounting."""
    contexts, _invalid_context_periods = extract_contexts(data)
    units = extract_units(data)
    integrity = IntegrityCounts()
    tagged_companies: set[str] = set()
    groups: dict[tuple[str, str, str | None, str | None], list[_CandidateFact]] = defaultdict(
        list
    )
    legacy_groups: dict[tuple[str, str], list[tuple[bool, str, str | None]]] = defaultdict(list)
    observed_periods: set[str] = set()

    for raw_attrs, body in IX_FACT_RE.findall(data):
        attrs = parse_attrs(raw_attrs)
        concept = local_name(attrs.get("name", ""))
        raw_value = text_content(body)
        if concept == COMPANY_CONCEPT:
            if raw_value:
                tagged_companies.add(raw_value)
            continue
        if concept not in TARGET_SET:
            continue
        integrity.target_facts_seen += 1
        context = contexts.get(attrs.get("contextref", ""))
        if context is None:
            integrity.bad_period_refs += 1
            continue
        observed_periods.add(context.period_end)
        try:
            scale = int(attrs.get("scale", "0") or 0)
        except ValueError:
            scale = 0
        numeric_value = normalise_number(raw_value, scale, attrs.get("sign", ""))
        legacy_groups[(concept, context.period_end)].append(
            (
                context.kind == ContextKind.NON_DIMENSIONAL,
                raw_value,
                numeric_value,
            )
        )
        if context.kind == ContextKind.MULTI_MEMBER:
            integrity.skipped_multimember += 1
            continue
        if context.kind == ContextKind.TYPED:
            integrity.skipped_typed += 1
            continue
        unit_ref = attrs.get("unitref", "")
        measure = units.get(unit_ref)
        currency = None if concept == EMPLOYEE_CONCEPT else measure
        if concept != EMPLOYEE_CONCEPT:
            if unit_ref and measure is None:
                integrity.unresolved_unit_refs += 1
            elif measure and measure.upper() != "GBP":
                integrity.non_gbp_facts += 1
        candidate = _CandidateFact(
            concept,
            context,
            raw_value,
            scale,
            numeric_value,
            currency,
        )
        key = (concept, context.period_end, context.dimension, context.member)
        groups[key].append(candidate)

    current_period = max(observed_periods, default="")
    observations: list[FactObservation] = []
    for candidates in groups.values():
        _emit_group(candidates, observations, integrity, current_period)
    legacy_fallbacks = []
    for (concept, period_end), candidates in legacy_groups.items():
        if any(non_dimensional for non_dimensional, _raw, _numeric in candidates):
            continue
        values = {
            ("NUM", numeric) if numeric is not None else ("RAW", raw)
            for _non_dimensional, raw, numeric in candidates
        }
        if len(values) == 1:
            _non_dimensional, raw, numeric = candidates[0]
            legacy_fallbacks.append(LegacyFallback(concept, period_end, numeric, raw))
    integrity.assert_closes()
    return ExtractedFiling(
        company,
        made_up_to_date,
        frozenset(tagged_companies),
        tuple(observations),
        tuple(legacy_fallbacks),
        integrity,
    )
