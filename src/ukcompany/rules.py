"""Indicator rule registry: the documented judgement layer.

Principles (see docs/plan.md; docs/rules.md is GENERATED from this file):
  * Source events are recorded facts; rule definitions, thresholds, severities
    and any aggregation are analytical judgements. This registry is what makes
    those judgements auditable.
  * Indicators are built from registrar-RECORDED statuses, events and
    filing-compliance fields. "Recorded" is deliberate: Companies House
    registers most information without verifying it, so nothing here is
    described as verified.
  * Every indicator is traceable to specified source fields or events and a
    documented transformation; otherwise it does not ship.
  * severity "info" is context and must never count toward any aggregate.
  * Dissolved/closed statuses are exclusions (see derive.EXCLUDED_STATUSES),
    not flags - they gate whether a company is screenable at all.
  * No composite score. Ever, in this module.

Spec notes (checked against the company-profile spec, 2026-08):
  * has_charges, has_insolvency_history, has_been_liquidated are deprecated in
    favour of links.charges / links.insolvency. Links are primary triggers;
    booleans are corroborating fallback for older cached responses.
  * Members' voluntary liquidation is a SOLVENT winding-up: insolvency cases
    are classified by type before any severity is assigned.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .derive import INSOLVENT_STATUSES

Attributes = dict[str, Any]

YOUNG_COMPANY_MONTHS = 24  # judgement call: "young" = under 2 years; context only


@dataclass(frozen=True)
class Rule:
    rule_id: str
    name: str
    severity: str  # "high" | "medium" | "low" | "info"
    tier: int  # verification tier of the underlying field(s); v1 rules are all 1
    definition: str  # human-readable, goes verbatim into docs/rules.md
    caveats: str
    func: Callable[[Attributes], str | None]  # returns evidence string, or None


def _all_known_cases_solvent(a: Attributes) -> bool:
    """True only when case data exists AND every case type is a solvent type."""
    return bool(a.get("insolvency_case_types")) and not a.get("insolvency_adverse_case_types")


def _status_insolvent(a: Attributes) -> str | None:
    status = a.get("company_status")
    if status not in INSOLVENT_STATUSES:
        return None
    # A 'liquidation' status backed only by members' voluntary liquidation cases
    # is a solvent winding-up: SOLVENT_WINDING_UP carries it instead.
    if status == "liquidation" and _all_known_cases_solvent(a):
        return None
    return f"company_status={status}"


def _status_strikeoff(a: Attributes) -> str | None:
    if a.get("company_status_detail") == "active-proposal-to-strike-off":
        return "company_status_detail=active-proposal-to-strike-off"
    return None


def _insolvency_adverse(a: Attributes) -> str | None:
    adverse = a.get("insolvency_adverse_case_types")
    if adverse:
        return f"{a.get('insolvency_n_cases')} case(s), adverse types: {adverse}"
    # Insolvency indicated (link, or deprecated booleans on older cached data)
    # but no case data cached: fires as unclassified rather than staying silent.
    indicated = (
        a.get("has_insolvency_link")
        or a.get("has_insolvency_history")
        or a.get("has_been_liquidated")
    )
    if indicated and not a.get("insolvency_case_types"):
        return "insolvency indicated on profile; cases unclassified (resource not cached)"
    return None


def _solvent_winding_up(a: Attributes) -> str | None:
    if _all_known_cases_solvent(a):
        return f"all cases solvent types: {a.get('insolvency_solvent_case_types')}"
    return None


def _accounts_overdue(a: Attributes) -> str | None:
    if a.get("accounts_overdue") is True:
        return f"accounts overdue (next_due={a.get('accounts_next_due')})"
    return None


def _cs_overdue(a: Attributes) -> str | None:
    if a.get("confirmation_statement_overdue") is True:
        return (
            f"confirmation statement overdue (next_due={a.get('confirmation_statement_next_due')})"
        )
    return None


def _addr_dispute(a: Attributes) -> str | None:
    parts = []
    if a.get("registered_office_is_in_dispute") is True:
        parts.append("registered_office_is_in_dispute")
    if a.get("undeliverable_registered_office_address") is True:
        parts.append("undeliverable_registered_office_address")
    return ", ".join(parts) if parts else None


def _charges(a: Attributes) -> str | None:
    if a.get("has_charges_link"):
        return "charges resource linked from profile"
    if a.get("has_charges") is True:
        return "has_charges=true (deprecated field; older cached response)"
    return None


def _young(a: Attributes) -> str | None:
    age = a.get("age_months")
    if age is not None and age < YOUNG_COMPANY_MONTHS:
        return f"age_months={age}"
    return None


# Verbatim official PSC statement constants (companieshouse/api-enumerations
# psc_descriptions.yml) that mean the beneficial owner is not resolved. Matched
# literally against active_psc_statement_codes - do NOT normalise or "fix"
# spelling here; some official constants are misspelled and normalising breaks
# the match. (These are correctly spelled upstream; the caution stands for the
# wider set.)
#
# The `-partnership` variants are the Scottish Limited Partnership form of the
# same unresolved-owner condition and are kept as DISTINCT constants (the
# register keeps them distinct; live scan 2026-08 found active SLP statements use
# only the -partnership forms). SLPs are historically the highest-risk vehicle
# for concealed ownership, so they must trigger the rule too.
PSC_UNRESOLVED_STATEMENT_CODES = (
    "steps-to-find-psc-not-yet-completed",
    "psc-exists-but-not-identified",
    "psc-details-not-confirmed",
    "steps-to-find-psc-not-yet-completed-partnership",
    "psc-exists-but-not-identified-partnership",
    "psc-details-not-confirmed-partnership",
)


def _psc_unresolved(a: Attributes) -> str | None:
    codes = a.get("active_psc_statement_codes")
    if not codes:
        return None
    present = [c for c in PSC_UNRESOLVED_STATEMENT_CODES if c in codes.split(",")]
    if present:
        return "active PSC statement(s): " + ", ".join(present)
    return None


REGISTRY: list[Rule] = [
    Rule(
        "STATUS_INSOLVENT",
        "Live insolvency-type status",
        "high",
        1,
        f"`company_status` is one of {sorted(INSOLVENT_STATUSES)}, except where the status is "
        "`liquidation` and all cached insolvency cases are solvent types (see "
        "SOLVENT_WINDING_UP).",
        "Registrar-recorded status from formal proceedings.",
        _status_insolvent,
    ),
    Rule(
        "STATUS_STRIKEOFF",
        "Active proposal to strike off",
        "high",
        1,
        "`company_status_detail` = `active-proposal-to-strike-off`.",
        "Often triggered by non-filing; can be discontinued. Still a strong current-state signal.",
        _status_strikeoff,
    ),
    Rule(
        "INSOLVENCY_ADVERSE",
        "Adverse insolvency case(s) on record",
        "high",
        1,
        "Insolvency resource (linked from the profile via `links.insolvency`, fetched and "
        "cached) contains at least one case whose type is not a solvent winding-up; or "
        "insolvency is indicated on the profile but no case data is cached (fires as "
        "'unclassified').",
        "Case types listed in evidence. Members' voluntary liquidation is classified as solvent "
        "and never triggers this rule. The `has_insolvency_history`/`has_been_liquidated` "
        "booleans are deprecated per the spec and used only as fallback indicators for older "
        "cached responses.",
        _insolvency_adverse,
    ),
    Rule(
        "SOLVENT_WINDING_UP",
        "Solvent winding-up (e.g. members' voluntary liquidation)",
        "info",
        1,
        "All cached insolvency cases are solvent types (members-voluntary-liquidation).",
        "Routine for retirement/reorganisation - context, not an adverse event. Never counts "
        "toward totals.",
        _solvent_winding_up,
    ),
    Rule(
        "ACCOUNTS_OVERDUE",
        "Accounts overdue",
        "medium",
        1,
        "`accounts.next_accounts.overdue` = true (falling back to the deprecated "
        "`accounts.overdue` for older cached responses). Computed by Companies House against "
        "the statutory deadline.",
        "Correlates with company size/admin resources, not only distress.",
        _accounts_overdue,
    ),
    Rule(
        "CS_OVERDUE",
        "Confirmation statement overdue",
        "medium",
        1,
        "`confirmation_statement.overdue` = true.",
        "As ACCOUNTS_OVERDUE.",
        _cs_overdue,
    ),
    Rule(
        "ADDR_DISPUTE",
        "Registered office disputed or undeliverable",
        "medium",
        1,
        "`registered_office_is_in_dispute` = true or `undeliverable_registered_office_address` "
        "= true.",
        "Registrar-set flags (ECCTA powers). Evidence names which flag fired.",
        _addr_dispute,
    ),
    Rule(
        "CHARGES_OUTSTANDING",
        "Charges registered",
        "info",
        1,
        "`links.charges` present on the profile (the deprecated `has_charges` boolean is a "
        "fallback for older cached responses).",
        "Normal for financed businesses - context, not risk. Never counts toward totals.",
        _charges,
    ),
    Rule(
        "YOUNG_COMPANY",
        "Company under 24 months old",
        "info",
        1,
        f"Age at observation date < {YOUNG_COMPANY_MONTHS} months, derived from "
        "`date_of_creation` and the response's fetch timestamp.",
        "Derived transformation, not a registrar event. Context only; penalises legitimate "
        "startups if misused. Never counts toward totals.",
        _young,
    ),
    Rule(
        "PSC_UNRESOLVED",
        "Beneficial ownership unresolved",
        "low",
        1,
        "`active_psc_statement_codes` contains any of `steps-to-find-psc-not-yet-completed`, "
        "`psc-exists-but-not-identified` or `psc-details-not-confirmed`, or their "
        "`-partnership` variants (the Scottish Limited Partnership form of the same condition) "
        "- verbatim official statement constants from the persons-with-significant-control-"
        "statements resource; ceased statements are excluded.",
        "PSC identification is mid-rollout under ECCTA; an unresolved statement is a "
        "transparency gap, not proof of wrongdoing. Statement constants are matched literally - "
        "official spellings (incl. any upstream misspellings) are never normalised. Evidence "
        "names which statement(s) fired. SLP `-partnership` statements are included because "
        "SLPs are a high-risk concealed-ownership vehicle.",
        _psc_unresolved,
    ),
]


def generate_rules_md() -> str:
    """docs/rules.md is generated from this registry so docs cannot drift."""
    lines = [
        "# Indicator rules",
        "",
        "*Generated from `src/ukcompany/rules.py` - do not edit by hand.*",
        "",
        "Indicators are built from registrar-recorded statuses, events and filing-compliance",
        "fields (Companies House registers most information without verifying it). Source events",
        "are recorded facts; rule definitions, thresholds, severities and any aggregation are",
        "documented analytical judgements. Every indicator is traceable to specified source",
        "fields or events and a documented transformation. `info` rules are context and are",
        "excluded from every aggregate count. Dissolved/converted/closed companies are handled",
        "as exclusions (not screenable), not as flags.",
        "",
        "| rule_id | severity | tier | definition | caveats |",
        "|---|---|---|---|---|",
    ]
    for r in REGISTRY:
        lines.append(f"| {r.rule_id} | {r.severity} | {r.tier} | {r.definition} | {r.caveats} |")
    lines.append("")
    return "\n".join(lines)
