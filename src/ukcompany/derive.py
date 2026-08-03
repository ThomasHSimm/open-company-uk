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
    annotations = d.get("corporate_annotation") or []
    ard = accounts.get("accounting_reference_date") or {}

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
            # registrar-published messages about the company (rare; Tier 1)
            "n_corporate_annotations": len(annotations),
            "corporate_annotation_types": ",".join(
                sorted({a.get("type", "unknown") for a in annotations}) if annotations else []
            )
            or None,
            # CH not the primary data source (FCA etc.) - completeness caveat
            "partial_data_available": d.get("partial_data_available"),
            # when a converted/closed/dissolved/removed company ceased
            "date_of_cessation": d.get("date_of_cessation"),
            # accounting reference date + next period end: captured now so the
            # phase-1.2 deadline reconstruction has them in historical cache
            "ard_day": ard.get("day"),
            "ard_month": ard.get("month"),
            "next_accounts_period_end": next_accounts.get("period_end_on"),
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


_OFFICER_KEYS = (
    "n_officers_total",
    "n_officers_active",
    "n_officers_resigned",
    "n_appointments_last_24m",
    "n_resignations_last_24m",
    "officer_churn_24m",
)


def derive_officers(cached: CachedResponse | None) -> dict[str, Any]:
    """Officer counts and 24-month churn from the merged officers resource.

    The 24-month windows are measured against the response's fetched_at (as
    age_months is), never "now", so a re-derive months later reproduces the
    original values. appointed_on / resigned_on are tolerated absent (older
    records, and appointment records mid-ECCTA identity-verification rollout).
    """
    if cached is None or cached.not_found or cached.data is None:
        return dict.fromkeys(_OFFICER_KEYS, None)

    observed_date = cached.fetched_at.date()
    items = cached.data.get("items") or []
    n_active = n_resigned = n_appt_24m = n_resign_24m = 0
    for o in items:
        resigned_on = _parse_date(o.get("resigned_on"))
        if resigned_on is None:
            n_active += 1
        else:
            n_resigned += 1
            if 0 <= _months_between(resigned_on, observed_date) < 24:
                n_resign_24m += 1
        appointed_on = _parse_date(o.get("appointed_on"))
        if appointed_on is not None and 0 <= _months_between(appointed_on, observed_date) < 24:
            n_appt_24m += 1
    return {
        "n_officers_total": len(items),
        "n_officers_active": n_active,
        "n_officers_resigned": n_resigned,
        "n_appointments_last_24m": n_appt_24m,
        "n_resignations_last_24m": n_resign_24m,
        "officer_churn_24m": n_appt_24m + n_resign_24m,
    }


def derive_psc(
    psc: CachedResponse | None, statements: CachedResponse | None
) -> dict[str, Any]:
    """PSC list + statements as SEPARATE fields - deliberately not one enum.

    psc_fetch_status is PIPELINE state (did we fetch the PSC list), never a
    company signal: a company's beneficial-ownership posture lives in
    psc_information_state and active_psc_statement_codes, not here. A cached 404
    is "not_found" (a completed fetch of a legitimately-absent resource), which
    is distinct from "not_fetched" (the pipeline never asked).

    Statement codes are preserved VERBATIM - official spelling and all. Several
    of the registry's statement constants are misspelled upstream
    (companieshouse/api-enumerations psc_descriptions.yml); normalising them
    here would silently break the rule that matches on those literals.
    """
    # Pipeline/fetch state, read from the PSC list endpoint only.
    if psc is None:
        fetch_status = "not_fetched"
    elif psc.not_found:
        fetch_status = "not_found"
    else:
        fetch_status = "ok"

    # PSC list records. None (not a count) when the list was never fetched, so a
    # missing fetch is not mistaken for "zero PSCs".
    if psc is None or psc.not_found or psc.data is None:
        n_records = 0 if (psc is not None and psc.not_found) else None
        n_ceased = 0 if (psc is not None and psc.not_found) else None
        n_active_records = n_records
    else:
        records = psc.data.get("items") or []
        n_records = len(records)
        n_ceased = sum(1 for r in records if r.get("ceased_on"))
        n_active_records = n_records - n_ceased

    # Active statement codes: verbatim `statement` values with no ceased_on.
    active_codes: list[str] = []
    if statements is not None and not statements.not_found and statements.data is not None:
        for s in statements.data.get("items") or []:
            if s.get("ceased_on"):
                continue
            code = s.get("statement")
            if code is not None:
                active_codes.append(code)

    # Derived state. "unknown" only when a resource was never fetched; a cached
    # 404 is a completed fetch of a legitimately-absent resource, not
    # incompleteness.
    if psc is None or statements is None:
        info_state = "unknown"
    elif n_active_records:
        info_state = "identified"
    elif active_codes:
        info_state = "statement_only"
    else:
        info_state = "none_reported"

    return {
        "psc_fetch_status": fetch_status,
        "psc_n_records": n_records,
        "psc_n_ceased": n_ceased,
        "active_psc_statement_codes": ",".join(active_codes) if active_codes else None,
        "psc_information_state": info_state,
    }


def derive_all(
    profiles: list[CachedResponse],
    insolvency_by_number: dict[str, CachedResponse] | None = None,
    officers_by_number: dict[str, CachedResponse] | None = None,
    psc_by_number: dict[str, CachedResponse] | None = None,
    psc_statements_by_number: dict[str, CachedResponse] | None = None,
) -> list[dict[str, Any]]:
    insolvency_by_number = insolvency_by_number or {}
    officers_by_number = officers_by_number or {}
    psc_by_number = psc_by_number or {}
    psc_statements_by_number = psc_statements_by_number or {}
    out = []
    for p in profiles:
        rec = derive_profile(p)
        rec.update(derive_insolvency(insolvency_by_number.get(p.company_number)))
        rec.update(derive_officers(officers_by_number.get(p.company_number)))
        rec.update(
            derive_psc(
                psc_by_number.get(p.company_number),
                psc_statements_by_number.get(p.company_number),
            )
        )
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
    {
        "field": "n_corporate_annotations",
        "tier": 1,
        "source": "profile:corporate_annotation[]",
        "definition": "Count of registrar-published corporate annotations (messages by "
        "Companies House about the company or its information).",
        "caveats": "Rare; types in corporate_annotation_types. Semantically adjacent to the "
        "address-dispute flags - review when present.",
    },
    {
        "field": "partial_data_available",
        "tier": 1,
        "source": "profile:partial_data_available",
        "definition": "Set when Companies House is not the primary data source for this "
        "company (e.g. FCA, Department for the Economy).",
        "caveats": "Completeness caveat: other indicators are weaker where this is set.",
    },
    {
        "field": "date_of_cessation",
        "tier": 1,
        "source": "profile:date_of_cessation",
        "definition": "Date the company was converted/closed, dissolved or removed (see "
        "company_status for which).",
        "caveats": "",
    },
    {
        "field": "ard_day / ard_month",
        "tier": 1,
        "source": "profile:accounts.accounting_reference_date",
        "definition": "Accounting reference date (day, month).",
        "caveats": "Captured now as the anchor for phase-1.2 deadline reconstruction.",
    },
    {
        "field": "next_accounts_period_end",
        "tier": 1,
        "source": "profile:accounts.next_accounts.period_end_on",
        "definition": "Last day of the next accounting period to be filed.",
        "caveats": "Captured for phase-1.2 deadline reconstruction.",
    },
    {
        "field": "n_officers_total",
        "tier": 2,
        "source": "officers:items[] (paginated, merged)",
        "definition": "Total officer appointments on record (active + resigned).",
        "caveats": "Officer identities historically unverified; ECCTA identity verification is "
        "mid-rollout (2025-2026), so this is filed-but-constrained, not verified. Count of "
        "appointments, not distinct persons.",
    },
    {
        "field": "n_officers_active",
        "tier": 2,
        "source": "officers:items[] with no resigned_on",
        "definition": "Appointments with no resignation date recorded.",
        "caveats": "Missing resigned_on is read as active; older records omit dates.",
    },
    {
        "field": "n_officers_resigned",
        "tier": 2,
        "source": "officers:items[] with resigned_on",
        "definition": "Appointments carrying a resignation date.",
        "caveats": "Depends on resigned_on being filed; tolerated absent.",
    },
    {
        "field": "n_appointments_last_24m",
        "tier": 2,
        "source": "derived from officers:items[].appointed_on",
        "definition": "Appointments dated within 24 months before observed_at.",
        "caveats": "Windowed against the response fetched_at, not now. appointed_on tolerated "
        "absent (not counted).",
    },
    {
        "field": "n_resignations_last_24m",
        "tier": 2,
        "source": "derived from officers:items[].resigned_on",
        "definition": "Resignations dated within 24 months before observed_at.",
        "caveats": "Windowed against the response fetched_at, not now.",
    },
    {
        "field": "officer_churn_24m",
        "tier": 2,
        "source": "derived",
        "definition": "n_appointments_last_24m + n_resignations_last_24m.",
        "caveats": "A movement count, not a risk signal; high churn is normal for some legitimate "
        "structures. Attribute only - no rule keys off it in this phase.",
    },
    {
        "field": "psc_fetch_status",
        "tier": 1,
        "source": "pipeline state (PSC list endpoint fetch outcome)",
        "definition": "ok / not_found / not_fetched for the persons-with-significant-control "
        "list resource.",
        "caveats": "PIPELINE STATE, never a company signal: it records whether we fetched the "
        "resource, not anything about the company. Never appears as flag evidence. The company's "
        "PSC posture is psc_information_state + active_psc_statement_codes.",
    },
    {
        "field": "psc_n_records",
        "tier": 1,
        "source": "psc:items[]",
        "definition": "Count of PSC records on the list resource (active + ceased).",
        "caveats": "None (not 0) when the list was not fetched, so a missing fetch is not read as "
        "'no PSCs'. 0 on a cached 404 (legitimately none filed).",
    },
    {
        "field": "psc_n_ceased",
        "tier": 1,
        "source": "psc:items[] with ceased_on",
        "definition": "PSC records carrying a ceased_on date.",
        "caveats": "Ceased PSCs are historical; active beneficial ownership is n_records - "
        "n_ceased.",
    },
    {
        "field": "active_psc_statement_codes",
        "tier": 1,
        "source": "psc_statements:items[].statement where ceased_on absent",
        "definition": "Comma-joined verbatim statement constants for statements with no "
        "ceased_on (e.g. steps-to-find-psc-not-yet-completed).",
        "caveats": "VERBATIM official values from psc_descriptions.yml, incl. upstream "
        "misspellings - never normalised, because rules match these literals. Ceased statements "
        "excluded.",
    },
    {
        "field": "psc_information_state",
        "tier": 1,
        "source": "derived from psc + psc_statements",
        "definition": "identified (>=1 active PSC record) / statement_only (no records, >=1 "
        "active statement) / none_reported (neither) / unknown (a resource not fetched).",
        "caveats": "Derived transformation over both PSC resources. 'unknown' is fetch "
        "incompleteness, distinct from 'none_reported'.",
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
