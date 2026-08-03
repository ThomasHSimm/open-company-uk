"""PSC list + statements as separate fields, and the PSC_UNRESOLVED rule.

All synthetic. The verbatim-statement-code contract is load-bearing: the rule
matches official constants literally, so these tests assert the codes survive
derive unchanged and that psc_fetch_status (pipeline state) never leaks into
flag evidence.
"""

from datetime import UTC, datetime

from ukcompany.cache import CachedResponse
from ukcompany.derive import derive_psc
from ukcompany.rules import PSC_UNRESOLVED_STATEMENT_CODES
from ukcompany.score import score_company

OBSERVED_AT = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _cached(endpoint: str, data: dict | None, status_code: int = 200) -> CachedResponse:
    return CachedResponse(
        company_number="00000077",
        endpoint=endpoint,
        status_code=status_code,
        fetched_at=OBSERVED_AT,
        url=f"fixture://{endpoint}",
        data=data,
    )


def _psc_list(items: list[dict]) -> CachedResponse:
    return _cached("psc", {"items": items, "total_results": len(items)})


def _statements(items: list[dict]) -> CachedResponse:
    return _cached("psc_statements", {"items": items, "total_results": len(items)})


def _not_found(endpoint: str) -> CachedResponse:
    return _cached(endpoint, None, status_code=404)


# --- (a) identified PSC --------------------------------------------------------


def test_identified_psc():
    psc = _psc_list([{"name": "SYNTHETIC OWNER A", "kind": "individual-person-with-significant-control"}])
    stmts = _statements([])
    out = derive_psc(psc, stmts)
    assert out["psc_fetch_status"] == "ok"
    assert out["psc_n_records"] == 1
    assert out["psc_n_ceased"] == 0
    assert out["psc_information_state"] == "identified"
    assert out["active_psc_statement_codes"] is None
    # No unresolved statement -> rule silent.
    assert _psc_flags(out) == []


# --- (b) statement-only, steps-not-yet-completed -------------------------------


def test_statement_only_steps_not_yet_completed_fires_rule():
    psc = _psc_list([])  # no PSC records
    stmts = _statements([{"statement": "steps-to-find-psc-not-yet-completed"}])
    out = derive_psc(psc, stmts)
    assert out["psc_information_state"] == "statement_only"
    assert out["active_psc_statement_codes"] == "steps-to-find-psc-not-yet-completed"
    flags = _psc_flags(out)
    assert [f["rule_id"] for f in flags] == ["PSC_UNRESOLVED"]
    assert flags[0]["severity"] == "low"
    assert "steps-to-find-psc-not-yet-completed" in flags[0]["evidence"]


# --- (c) 404 on both endpoints -------------------------------------------------


def test_both_endpoints_404():
    out = derive_psc(_not_found("psc"), _not_found("psc_statements"))
    assert out["psc_fetch_status"] == "not_found"
    assert out["psc_n_records"] == 0  # cached 404: legitimately none, not unknown
    assert out["active_psc_statement_codes"] is None
    assert out["psc_information_state"] == "none_reported"
    assert _psc_flags(out) == []


def test_not_fetched_is_unknown_not_none_reported():
    out = derive_psc(None, None)
    assert out["psc_fetch_status"] == "not_fetched"
    assert out["psc_n_records"] is None  # never fetched != zero PSCs
    assert out["psc_information_state"] == "unknown"
    assert _psc_flags(out) == []


# --- (d) ceased statement ignored ----------------------------------------------


def test_ceased_statement_ignored():
    psc = _psc_list([])
    stmts = _statements(
        [
            {"statement": "steps-to-find-psc-not-yet-completed", "ceased_on": "2024-01-01"},
            {"statement": "psc-exists-but-not-identified", "ceased_on": "2023-05-05"},
        ]
    )
    out = derive_psc(psc, stmts)
    assert out["active_psc_statement_codes"] is None  # both ceased -> excluded
    assert out["psc_information_state"] == "none_reported"
    assert _psc_flags(out) == []


def test_ceased_psc_record_counted_but_not_active():
    psc = _psc_list(
        [
            {"name": "ACTIVE OWNER"},
            {"name": "FORMER OWNER", "ceased_on": "2022-06-01"},
        ]
    )
    out = derive_psc(psc, _statements([]))
    assert out["psc_n_records"] == 2
    assert out["psc_n_ceased"] == 1
    assert out["psc_information_state"] == "identified"  # 1 active record


# --- verbatim contract + evidence hygiene --------------------------------------


def test_statement_codes_preserved_verbatim_not_normalised():
    # A deliberately odd/misspelled-looking constant must pass through untouched.
    weird = "no-individual-or-entity-with-signficant-control"  # upstream misspelling
    out = derive_psc(_psc_list([]), _statements([{"statement": weird}]))
    assert out["active_psc_statement_codes"] == weird  # byte-for-byte, no "fix"


def test_trigger_codes_are_the_documented_constants():
    # The three base constants plus their Scottish Limited Partnership variants,
    # verbatim per companieshouse/api-enumerations psc_descriptions.yml.
    assert PSC_UNRESOLVED_STATEMENT_CODES == (
        "steps-to-find-psc-not-yet-completed",
        "psc-exists-but-not-identified",
        "psc-details-not-confirmed",
        "steps-to-find-psc-not-yet-completed-partnership",
        "psc-exists-but-not-identified-partnership",
        "psc-details-not-confirmed-partnership",
    )


def test_partnership_variant_fires_rule():
    # Scottish Limited Partnership statement-only company (the common live case).
    out = derive_psc(
        _psc_list([]),
        _statements([{"statement": "psc-exists-but-not-identified-partnership"}]),
    )
    assert out["psc_information_state"] == "statement_only"
    assert out["active_psc_statement_codes"] == "psc-exists-but-not-identified-partnership"
    flags = _psc_flags(out)
    assert [f["rule_id"] for f in flags] == ["PSC_UNRESOLVED"]
    assert "psc-exists-but-not-identified-partnership" in flags[0]["evidence"]


def test_psc_fetch_status_never_appears_in_flag_evidence():
    # Whatever the pipeline state, it must not surface as evidence anywhere.
    for psc, stmts in [
        (_psc_list([]), _statements([{"statement": "psc-details-not-confirmed"}])),
        (_not_found("psc"), _not_found("psc_statements")),
        (None, None),
    ]:
        out = derive_psc(psc, stmts)
        for f in _psc_flags(out):
            assert "psc_fetch_status" not in f["evidence"]
            assert out["psc_fetch_status"] not in f["evidence"]


def _psc_flags(attrs: dict) -> list[dict]:
    """score_company over an attribute record, keeping only PSC flags."""
    attrs = {"company_number": "00000077", "observed_at": OBSERVED_AT.isoformat(), **attrs}
    return [f for f in score_company(attrs) if f["rule_id"] == "PSC_UNRESOLVED"]
