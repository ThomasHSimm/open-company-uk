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


def _psc_list(items: list[dict], **top) -> CachedResponse:
    data = {"items": items, "total_results": len(items)}
    data.update(top)  # e.g. active_count / ceased_count
    return _cached("psc", data)


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


# --- ceased counting precedence (correctness fix) ------------------------------


def test_ceased_via_ceased_on():
    out = derive_psc(
        _psc_list([{"name": "A"}, {"name": "B", "ceased_on": "2022-01-01"}]),
        _statements([]),
    )
    assert out["psc_n_records"] == 2 and out["psc_n_ceased"] == 1


def test_ceased_via_ceased_boolean():
    # Live items carry a `ceased` boolean rather than ceased_on.
    out = derive_psc(
        _psc_list([{"name": "A", "ceased": False}, {"name": "B", "ceased": True}]),
        _statements([]),
    )
    assert out["psc_n_records"] == 2 and out["psc_n_ceased"] == 1


def test_ceased_boolean_beats_absent_ceased_on():
    # ceased=True with no ceased_on must still count as ceased (boolean wins).
    out = derive_psc(_psc_list([{"name": "A", "ceased": True}]), _statements([]))
    assert out["psc_n_ceased"] == 1


def test_top_level_counts_authoritative_when_list_omits_ceased():
    # List returns only the 1 active PSC; ceased ones are omitted but counted.
    out = derive_psc(
        _psc_list([{"name": "A", "ceased": False}], active_count=1, ceased_count=2),
        _statements([]),
    )
    assert out["psc_n_ceased"] == 2
    assert out["psc_n_records"] == 3  # true total = active + ceased, not len(items)
    assert out["psc_information_state"] == "identified"  # active_count >= 1


def test_top_level_counts_win_on_disagreement_and_warn(caplog):
    # Per-item tally says 1 ceased; top-level says 3. Top-level wins, warning logged.
    items = [{"name": "A"}, {"name": "B", "ceased": True}]
    with caplog.at_level("WARNING"):
        out = derive_psc(_psc_list(items, active_count=2, ceased_count=3), _statements([]))
    assert out["psc_n_ceased"] == 3  # top-level, not the per-item 1
    assert any("ceased count mismatch" in r.message for r in caplog.records)


# --- natures of control (verbatim, active only) --------------------------------


def test_psc_natures_of_control_active_only_sorted_verbatim():
    out = derive_psc(
        _psc_list(
            [
                {"name": "A", "natures_of_control": ["ownership-of-shares-75-to-100-percent"]},
                {"name": "B", "natures_of_control": ["voting-rights-25-to-50-percent"]},
                # ceased record's natures must be ignored:
                {"name": "C", "ceased": True, "natures_of_control": ["right-to-appoint-directors"]},
                # duplicate across active records collapses:
                {"name": "D", "natures_of_control": ["voting-rights-25-to-50-percent"]},
            ]
        ),
        _statements([]),
    )
    assert out["psc_natures_of_control"] == (
        "ownership-of-shares-75-to-100-percent,voting-rights-25-to-50-percent"
    )


def test_psc_natures_none_when_empty():
    out = derive_psc(_psc_list([{"name": "A"}]), _statements([]))
    assert out["psc_natures_of_control"] is None


# --- PSC identity verification (ECCTA) -----------------------------------------


def test_psc_identity_verification_counts():
    out = derive_psc(
        _psc_list(
            [
                # verified block present, statement due, not yet identity-verified -> due
                {"name": "A", "identity_verification_details": {
                    "appointment_verification_statement_due_on": "2025-12-07"}},
                # block present, due date AND identity verified -> verified, not due
                {"name": "B", "identity_verification_details": {
                    "appointment_verification_statement_due_on": "2025-12-07",
                    "identity_verified_on": "2025-11-24"}},
                # statement filed but NOT identity-verified: still counts as due
                # (statement-filing is a separate signal), and as statement_filed
                {"name": "D", "identity_verification_details": {
                    "appointment_verification_statement_due_on": "2025-12-07",
                    "appointment_verification_statement_date": "2025-11-24"}},
                # no block at all -> neither
                {"name": "C"},
            ]
        ),
        _statements([]),
    )
    assert out["n_psc_id_verified"] == 3  # A, B, D carry the block
    assert out["n_psc_id_verification_due"] == 2  # A and D (statement filed does NOT clear due)
    assert out["n_psc_id_statement_filed"] == 1  # only D filed a statement


def test_psc_verification_fields_none_when_not_fetched():
    out = derive_psc(None, None)
    assert out["n_psc_id_verified"] is None
    assert out["n_psc_id_statement_filed"] is None
    assert out["psc_natures_of_control"] is None
    out404 = derive_psc(_not_found("psc"), _not_found("psc_statements"))
    assert out404["n_psc_id_verified"] == 0  # cached 404 = legitimately none
    assert out404["n_psc_id_statement_filed"] == 0
