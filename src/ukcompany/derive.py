"""Derive layer: cached raw JSON -> flat attribute records. Pure functions.

Rules for this module:
  * .get() everything - older records have missing/inconsistent fields, and a
    KeyError on company 340 of 500 is not acceptable.
  * No network access. Input is the cache, full stop.
  * Ages/elapsed times are computed against the response's fetched_at, not
    "now", so a re-derive months later reproduces the original values.
  * Attributes carry everything useful (Tier 2/3 included: SIC, accounts
    category, ...). The flag registry in rules.py restricts itself to Tier 1;
    this table does not.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .cache import CachedResponse

# CH company_status values that mean "no longer a live entity" - these gate
# screenability (exclusions table) rather than acting as risk flags.
EXCLUDED_STATUSES = {"dissolved", "converted-closed", "closed", "removed"}

# Statuses indicating a live insolvency-type process.
INSOLVENT_STATUSES = {
    "liquidation",
    "administration",
    "receivership",
    "voluntary-arrangement",
    "insolvency-proceedings",
}


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def derive_profile(cached: CachedResponse) -> dict[str, Any]:
    """Flatten one cached profile response into an attribute record."""
    observed_at: datetime = cached.fetched_at
    observed_date = observed_at.date()
    base: dict[str, Any] = {
        "company_number": cached.company_number,
        "observed_at": observed_at.isoformat(),
        "found": not cached.not_found,
    }
    if cached.not_found or cached.data is None:
        return base

    d = cached.data
    accounts = d.get("accounts") or {}
    last_accounts = accounts.get("last_accounts") or {}
    next_accounts = accounts.get("next_accounts") or {}
    conf = d.get("confirmation_statement") or {}
    office = d.get("registered_office_address") or {}
    links = d.get("links") or {}
    previous_names = d.get("previous_company_names") or []

    creation = _parse_date(d.get("date_of_creation"))

    base.update(
        {
            "company_name": d.get("company_name"),
            "company_status": d.get("company_status"),
            "company_status_detail": d.get("company_status_detail"),
            "company_type": d.get("type"),
            "subtype": d.get("subtype"),
            "jurisdiction": d.get("jurisdiction"),
            "date_of_creation": d.get("date_of_creation"),
            "age_months": _months_between(creation, observed_date) if creation else None,
            "sic_codes": ",".join(d.get("sic_codes") or []),
            "n_previous_names": len(previous_names),
            # accounts / confirmation statement (Tier 1: CH-computed).
            # Spec (checked 2026-08): accounts.overdue and accounts.next_due are
            # deprecated in favour of accounts.next_accounts.* - prefer the new
            # fields, fall back to the deprecated ones for older cached data.
            "accounts_overdue": _first_not_none(
                next_accounts.get("overdue"), accounts.get("overdue")
            ),
            "accounts_next_due": next_accounts.get("due_on") or accounts.get("next_due"),
            "last_accounts_type": last_accounts.get("type"),
            "last_accounts_period_end": last_accounts.get("period_end_on")
            or last_accounts.get("made_up_to"),
            "confirmation_statement_overdue": conf.get("overdue"),
            "confirmation_statement_next_due": conf.get("next_due"),
            # event indicators (Tier 1). The has_* booleans are deprecated per the
            # spec ("Please use links.charges / links.insolvency") - links are
            # primary, booleans retained as corroborating fallback only.
            "has_charges_link": bool(links.get("charges")),
            "has_charges": d.get("has_charges"),
            "has_insolvency_link": bool(links.get("insolvency")),
            "has_insolvency_history": d.get("has_insolvency_history"),
            "has_been_liquidated": d.get("has_been_liquidated"),
            "registered_office_is_in_dispute": d.get("registered_office_is_in_dispute"),
            "undeliverable_registered_office_address": d.get(
                "undeliverable_registered_office_address"
            ),
            # address context (Tier 2; phase-2 population features join on these)
            "office_postcode": office.get("postal_code"),
            "office_locality": office.get("locality"),
            # screenability gate
            "excluded_status": (d.get("company_status") in EXCLUDED_STATUSES),
        }
    )
    return base


def _first_not_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


# Insolvency case types that describe a SOLVENT winding-up. Members' voluntary
# liquidation is routinely used for retirement/reorganisation and is not an
# adverse event; a blanket "insolvency = high severity" would misclassify it.
SOLVENT_CASE_TYPES = {"members-voluntary-liquidation"}


def derive_insolvency(cached: CachedResponse | None) -> dict[str, Any]:
    """Summarise the insolvency resource (case-level evidence for the rules)."""
    if cached is None or cached.not_found or cached.data is None:
        return {
            "insolvency_n_cases": None,
            "insolvency_case_types": None,
            "insolvency_adverse_case_types": None,
            "insolvency_solvent_case_types": None,
        }
    cases = cached.data.get("cases") or []
    types = sorted({c.get("type", "unknown") for c in cases})
    adverse = [t for t in types if t not in SOLVENT_CASE_TYPES]
    solvent = [t for t in types if t in SOLVENT_CASE_TYPES]
    return {
        "insolvency_n_cases": len(cases),
        "insolvency_case_types": ",".join(types) if types else None,
        "insolvency_adverse_case_types": ",".join(adverse) if adverse else None,
        "insolvency_solvent_case_types": ",".join(solvent) if solvent else None,
    }


def derive_all(
    profiles: list[CachedResponse],
    insolvency_by_number: dict[str, CachedResponse] | None = None,
) -> list[dict[str, Any]]:
    insolvency_by_number = insolvency_by_number or {}
    out = []
    for p in profiles:
        rec = derive_profile(p)
        rec.update(derive_insolvency(insolvency_by_number.get(p.company_number)))
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Field-level data dictionary. Verification tier is a property of the FIELD,
# not the company row (attributes with different evidence levels cannot share
# one per-row tier column), so it lives here and renders to docs/.
# Tiers: 1 = registrar-recorded status/event/compliance field;
#        2 = filed-but-constrained (content chosen by the company within rules);
#        3 = self-declared, weakly constrained.
# ---------------------------------------------------------------------------

FIELD_DOCS: list[dict[str, str | int]] = [
    {
        "field": "company_number",
        "tier": 1,
        "source": "profile:company_number",
        "definition": "Registrar-assigned identifier.",
        "caveats": "",
    },
    {
        "field": "observed_at",
        "tier": 1,
        "source": "cache envelope fetched_at",
        "definition": "Timestamp of the cached API response all values derive from.",
        "caveats": "Distinct from event dates and from any bulk snapshot_date.",
    },
    {
        "field": "company_name",
        "tier": 3,
        "source": "profile:company_name",
        "definition": "Registered name.",
        "caveats": "No constraint on describing activity.",
    },
    {
        "field": "company_status",
        "tier": 1,
        "source": "profile:company_status",
        "definition": "Registrar-recorded status from formal events.",
        "caveats": "",
    },
    {
        "field": "company_status_detail",
        "tier": 1,
        "source": "profile:company_status_detail",
        "definition": "Status detail, e.g. active-proposal-to-strike-off.",
        "caveats": "",
    },
    {
        "field": "company_type",
        "tier": 1,
        "source": "profile:type",
        "definition": "Legal form, assigned at registration.",
        "caveats": "",
    },
    {
        "field": "jurisdiction",
        "tier": 1,
        "source": "profile:jurisdiction",
        "definition": "Registering jurisdiction.",
        "caveats": "",
    },
    {
        "field": "date_of_creation",
        "tier": 1,
        "source": "profile:date_of_creation",
        "definition": "Incorporation date.",
        "caveats": "Shelf companies mean age is not trading history.",
    },
    {
        "field": "age_months",
        "tier": 1,
        "source": "derived",
        "definition": "Whole months from date_of_creation to observed_at.",
        "caveats": "Derived transformation, not a registrar event.",
    },
    {
        "field": "sic_codes",
        "tier": 3,
        "source": "profile:sic_codes",
        "definition": "Self-declared nature-of-business codes.",
        "caveats": "Never verified; often stale; catch-all codes common; measurement error is "
        "non-random (newer/smaller/agent-formed companies noisier).",
    },
    {
        "field": "n_previous_names",
        "tier": 1,
        "source": "profile:previous_company_names",
        "definition": "Count of recorded previous names.",
        "caveats": "",
    },
    {
        "field": "accounts_overdue",
        "tier": 1,
        "source": "profile:accounts.next_accounts.overdue (fallback deprecated accounts.overdue)",
        "definition": "CH-computed overdue flag vs statutory deadline.",
        "caveats": "Correlates with company size/resources, not only distress.",
    },
    {
        "field": "last_accounts_type",
        "tier": 2,
        "source": "profile:accounts.last_accounts.type",
        "definition": "Category of last filed accounts (micro-entity/small/full/dormant/...).",
        "caveats": "Reflects the company's disclosure choice within size thresholds; a size "
        "signal, not a risk signal.",
    },
    {
        "field": "has_charges_link",
        "tier": 1,
        "source": "profile:links.charges",
        "definition": "Charges resource exists for the company.",
        "caveats": "Presence of registered charges is normal for financed businesses.",
    },
    {
        "field": "has_insolvency_link",
        "tier": 1,
        "source": "profile:links.insolvency",
        "definition": "Insolvency resource exists for the company.",
        "caveats": "Case types must be classified before severity: MVL is solvent.",
    },
    {
        "field": "has_charges",
        "tier": 1,
        "source": "profile:has_charges (deprecated)",
        "definition": "Deprecated boolean; retained as fallback for older cached responses.",
        "caveats": "Spec: 'Please use links.charges'.",
    },
    {
        "field": "has_insolvency_history",
        "tier": 1,
        "source": "profile:has_insolvency_history (deprecated)",
        "definition": "Deprecated boolean; fallback only.",
        "caveats": "Spec: 'Please use links.insolvency'.",
    },
    {
        "field": "insolvency_case_types",
        "tier": 1,
        "source": "insolvency:cases[].type",
        "definition": "Distinct case types on the fetched insolvency resource.",
        "caveats": "members-voluntary-liquidation is a solvent winding-up.",
    },
    {
        "field": "registered_office_is_in_dispute",
        "tier": 1,
        "source": "profile:registered_office_is_in_dispute",
        "definition": "Registrar-set dispute flag (ECCTA powers).",
        "caveats": "",
    },
    {
        "field": "undeliverable_registered_office_address",
        "tier": 1,
        "source": "profile:undeliverable_registered_office_address",
        "definition": "Registrar-set undeliverable-address flag.",
        "caveats": "",
    },
    {
        "field": "office_postcode",
        "tier": 2,
        "source": "profile:registered_office_address",
        "definition": "Registered office postcode.",
        "caveats": "Shared/agent addresses are common and legitimate; address-derived features "
        "proxy socioeconomic geography.",
    },
    {
        "field": "excluded_status",
        "tier": 1,
        "source": "derived from company_status",
        "definition": "True when status is dissolved/converted-closed/closed/removed: not "
        "screenable, reported separately.",
        "caveats": "",
    },
]


def generate_data_dictionary_md() -> str:
    lines = [
        "# Data dictionary: derived company attributes",
        "",
        "*Generated from `src/ukcompany/derive.py` - do not edit by hand.*",
        "",
        "Verification tier is a property of each field: 1 = registrar-recorded status/event/",
        "compliance field; 2 = filed-but-constrained; 3 = self-declared, weakly constrained.",
        "Companies House registers most information without verifying it; no field is",
        "described as verified.",
        "",
        "| field | tier | source | definition | caveats |",
        "|---|---|---|---|---|",
    ]
    for f in FIELD_DOCS:
        lines.append(
            f"| {f['field']} | {f['tier']} | {f['source']} | {f['definition']} | {f['caveats']} |"
        )
    lines.append("")
    return "\n".join(lines)
