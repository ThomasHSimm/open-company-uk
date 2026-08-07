"""Evaluate the unchanged derive-and-score pipeline against external labels."""

from __future__ import annotations

from dataclasses import dataclass, field

from ukcompany.cache import RawCache
from ukcompany.derive import derive_all
from ukcompany.fetch import INSOLVENCY, OFFICERS, PROFILE, PSC, PSC_STATEMENTS
from ukcompany.score import score_company
from ukcompany.validate import normalise_company_number

from .control import ControlPlan
from .labels import Label

ADVERSE_RULES = {"INSOLVENCY_ADVERSE", "STATUS_INSOLVENT"}
NORMAL_CURRENT_STATUSES = {"active"}
OUTCOMES = (
    "flagged_adverse",
    "excluded",
    "missed_404",
    "missed_status_moved",
    "missed_genuine",
    "not_fetched",
)


@dataclass(frozen=True)
class Outcome:
    company_number: str
    case_type: str
    raw_case_type: str
    outcome: str
    company_status: str | None = None
    rule_ids: tuple[str, ...] = ()


@dataclass
class EvaluationResult:
    outcomes: list[Outcome] = field(default_factory=list)
    solvent_winding_up_errors: list[Outcome] = field(default_factory=list)
    control_total: int = 0
    control_high_severity: list[str] = field(default_factory=list)
    control_unusable: int = 0
    # Per age band: [total assessed, number firing a high-severity flag]. Age is
    # a reported covariate, not a stratification match.
    control_by_band: dict[str, list[int]] = field(default_factory=dict)
    control_plan: ControlPlan | None = None

    def counts(self, case_type: str | None = None) -> dict[str, int]:
        rows = self.outcomes
        if case_type is not None:
            rows = [row for row in rows if row.case_type == case_type]
        return {name: sum(row.outcome == name for row in rows) for name in OUTCOMES}

    def case_types(self) -> list[str]:
        return sorted({row.case_type for row in self.outcomes})

    def recall(self, case_type: str | None = None) -> float | None:
        counts = self.counts(case_type)
        denominator = counts["flagged_adverse"] + counts["missed_genuine"]
        return counts["flagged_adverse"] / denominator if denominator else None


def _cached_record(cache: RawCache, number: str):
    profile = cache.read(number, PROFILE)
    if profile is None:
        return None, ()
    records = derive_all(
        [profile],
        {number: value} if (value := cache.read(number, INSOLVENCY)) is not None else {},
        {number: value} if (value := cache.read(number, OFFICERS)) is not None else {},
        {number: value} if (value := cache.read(number, PSC)) is not None else {},
        {number: value} if (value := cache.read(number, PSC_STATEMENTS)) is not None else {},
    )
    record = records[0]
    return record, tuple(flag["rule_id"] for flag in score_company(record))


def evaluate(
    labels: dict[str, Label],
    cache: RawCache,
    control: ControlPlan | None = None,
    positive_numbers: set[str] | None = None,
) -> EvaluationResult:
    """Evaluate cached records only. This function contains no fetching path.

    ``control`` is a drawn (or reloaded) stratified :class:`ControlPlan`. The
    high-severity flag-rate computation is unchanged; only the source of the
    control numbers changed (drawn from the snapshot, not supplied ad hoc).
    """
    result = EvaluationResult()
    cohort = labels.keys() if positive_numbers is None else positive_numbers
    for number in cohort:
        label = labels[number]
        record, rule_ids = _cached_record(cache, number)
        if record is None:
            outcome = "not_fetched"
            status = None
        elif not record.get("found"):
            outcome = "missed_404"
            status = None
        elif record.get("excluded_status"):
            # Match score_all(): dissolved/closed records are partitioned out
            # before rules are applied and must never receive validation credit.
            outcome = "excluded"
            status = record.get("company_status")
        else:
            status = record.get("company_status")
            if ADVERSE_RULES.intersection(rule_ids):
                outcome = "flagged_adverse"
            elif status in NORMAL_CURRENT_STATUSES:
                outcome = "missed_status_moved"
            else:
                outcome = "missed_genuine"
        row = Outcome(number, label.case_type, label.raw_case_type, outcome, status, rule_ids)
        result.outcomes.append(row)
        if outcome != "excluded" and "SOLVENT_WINDING_UP" in rule_ids:
            result.solvent_winding_up_errors.append(row)

    result.control_plan = control
    seen: set[str] = set()
    for member in control.members if control is not None else []:
        normalised = normalise_company_number(member.company_number)
        if not normalised.valid:
            result.control_unusable += 1
            continue
        assert normalised.number is not None
        if normalised.number in seen:
            continue
        seen.add(normalised.number)
        result.control_total += 1
        band = result.control_by_band.setdefault(member.age_band, [0, 0])
        band[0] += 1
        record, rule_ids = _cached_record(cache, normalised.number)
        if record is None or not record.get("found") or record.get("excluded_status"):
            continue
        flags = score_company(record)
        if any(flag["severity"] == "high" for flag in flags):
            result.control_high_severity.append(normalised.number)
            band[1] += 1
    return result
