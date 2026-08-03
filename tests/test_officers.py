"""Officers endpoint: pagination merge (truncation failure mode) + churn derive.

All synthetic. Invented officer names only - never real people. The fetch tests
drive the real _fetch_officers loop through a fake client so the start_index
pagination is exercised end to end, including a partial final page (the classic
off-by-one).
"""

from datetime import UTC, datetime

from tests.test_client import FakeResponse, make_client
from ukcompany.cache import CachedResponse, RawCache
from ukcompany.derive import derive_all, derive_officers
from ukcompany.fetch import OFFICERS, _fetch_officers

# Fixed observation instant so the 24-month windows are deterministic. 24
# months before this is 2024-08-01.
OBSERVED_AT = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _officer(i: int, appointed_on=None, resigned_on=None) -> dict:
    o = {"name": f"SYNTHETIC OFFICER {i:03d}", "officer_role": "director"}
    if appointed_on is not None:
        o["appointed_on"] = appointed_on
    if resigned_on is not None:
        o["resigned_on"] = resigned_on
    return o


def _officers_cached(items: list[dict]) -> CachedResponse:
    return CachedResponse(
        company_number="00000055",
        endpoint=OFFICERS,
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://officers",
        data={"items": items, "total_results": len(items)},
    )


def _paged_responses(total: int, page_size: int = 100) -> list[FakeResponse]:
    """Split `total` synthetic officers into API pages of page_size."""
    items = [_officer(i) for i in range(total)]
    pages = []
    for start in range(0, total, page_size):
        chunk = items[start : start + page_size]
        pages.append(
            FakeResponse(
                200,
                {
                    "items": chunk,
                    "total_results": total,
                    "items_per_page": page_size,
                    "start_index": start,
                },
            )
        )
    return pages


def test_pagination_merges_all_pages_including_partial_final(tmp_path):
    """Old-PLC-style: 123 officers -> pages of 100 + 23. Nothing truncated."""
    cache = RawCache(tmp_path)
    pages = _paged_responses(123, page_size=100)
    assert len(pages) == 2 and len(pages[1]._payload["items"]) == 23  # partial final page
    client, session, _ = make_client(pages)

    was_fetch, data = _fetch_officers(client, cache, "00000055", max_age_days=7.0)

    assert was_fetch is True
    assert session.calls == 2  # exactly two pages, no needless extra request
    assert data["total_results"] == 123
    assert len(data["items"]) == 123  # merge complete - the truncation failure mode
    names = [o["name"] for o in data["items"]]
    assert len(set(names)) == 123  # no duplication / no gap from an off-by-one
    assert names[0].endswith("000") and names[-1].endswith("122")


def test_merged_officers_written_to_single_cache_entry(tmp_path):
    cache = RawCache(tmp_path)
    client, _, _ = make_client(_paged_responses(123))
    _fetch_officers(client, cache, "00000055", max_age_days=7.0)

    cached = cache.read("00000055", OFFICERS)
    assert cached is not None and cached.status_code == 200
    assert len(cached.data["items"]) == 123  # one envelope, all pages merged


def test_fresh_cache_short_circuits_no_network(tmp_path):
    cache = RawCache(tmp_path)
    cache.write("00000055", OFFICERS, 200, "x", {"items": [_officer(0)], "total_results": 1})
    client, session, _ = make_client([])  # no queued responses: any call would IndexError
    was_fetch, data = _fetch_officers(client, cache, "00000055", max_age_days=7.0)
    assert was_fetch is False and session.calls == 0
    assert len(data["items"]) == 1


def test_officers_404_cached(tmp_path):
    cache = RawCache(tmp_path)
    client, _, _ = make_client([FakeResponse(404)])
    was_fetch, data = _fetch_officers(client, cache, "00000055", max_age_days=7.0)
    assert was_fetch is True and data is None
    cached = cache.read("00000055", OFFICERS)
    assert cached is not None and cached.not_found


def test_loop_stops_on_empty_page_when_total_overstated(tmp_path):
    """Defensive: total_results says 300 but the API stops returning items."""
    cache = RawCache(tmp_path)
    page1 = _paged_responses(100)[0]
    page1._payload["total_results"] = 300  # lie about the total
    empty = FakeResponse(200, {"items": [], "total_results": 300})
    client, session, _ = make_client([page1, empty])
    _, data = _fetch_officers(client, cache, "00000055", max_age_days=7.0)
    assert session.calls == 2  # asked once more, got nothing, stopped (no infinite loop)
    assert len(data["items"]) == 100


def test_churn_counts_against_fixed_fetched_at():
    items = [
        _officer(1, appointed_on="2010-01-01"),  # active, old appointment
        _officer(2, appointed_on="2025-06-01"),  # active, appt within 24m
        _officer(3, appointed_on="2000-01-01", resigned_on="2025-01-01"),  # resign within 24m
        _officer(4, appointed_on="2000-01-01", resigned_on="2019-01-01"),  # resign > 24m ago
        _officer(5, appointed_on="2024-08-01"),  # exactly 24m -> excluded (strictly within)
    ]
    out = derive_officers(_officers_cached(items))
    assert out["n_officers_total"] == 5
    assert out["n_officers_active"] == 3  # 1, 2, 5
    assert out["n_officers_resigned"] == 2  # 3, 4
    assert out["n_appointments_last_24m"] == 1  # only officer 2
    assert out["n_resignations_last_24m"] == 1  # only officer 3
    assert out["officer_churn_24m"] == 2


def test_missing_appointed_on_tolerated():
    items = [
        _officer(1),  # no dates at all
        _officer(2, resigned_on="2025-03-01"),  # resigned, no appointed_on
    ]
    out = derive_officers(_officers_cached(items))
    assert out["n_officers_total"] == 2
    assert out["n_officers_active"] == 1  # officer 1 (no resigned_on)
    assert out["n_officers_resigned"] == 1  # officer 2
    assert out["n_appointments_last_24m"] == 0  # no appointed_on anywhere
    assert out["n_resignations_last_24m"] == 1


def test_empty_officer_list_tolerated():
    out = derive_officers(_officers_cached([]))
    assert out["n_officers_total"] == 0
    assert out["officer_churn_24m"] == 0
    assert out["n_officers_active"] == 0


def test_missing_officers_resource_yields_none():
    out = derive_officers(None)
    assert out["n_officers_total"] is None
    assert out["officer_churn_24m"] is None
    assert out["n_officers_id_verified"] is None
    assert out["n_officers_id_verification_due"] is None


def test_officer_identity_verification_counts():
    items = [
        # ECCTA block present, statement due, not yet identity-verified -> due
        {"name": "A", "identity_verification_details": {
            "appointment_verification_statement_due_on": "2025-11-18"}},
        # block present + identity verified -> verified, not due
        {"name": "B", "identity_verification_details": {
            "appointment_verification_statement_due_on": "2025-11-18",
            "identity_verified_on": "2025-10-01"}},
        # no block -> counted in neither (absence != non-compliance)
        {"name": "C"},
    ]
    out = derive_officers(_officers_cached(items))
    assert out["n_officers_id_verified"] == 2
    assert out["n_officers_id_verification_due"] == 1


def test_derive_all_joins_officers_by_number():
    profile = CachedResponse(
        company_number="00000055",
        endpoint="profile",
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://profile",
        data={"company_name": "SYNTHETIC PLC", "company_status": "active"},
    )
    officers = {"00000055": _officers_cached([_officer(1, appointed_on="2025-06-01")])}
    (rec,) = derive_all([profile], officers_by_number=officers)
    assert rec["company_number"] == "00000055"
    assert rec["n_officers_total"] == 1
    assert rec["n_appointments_last_24m"] == 1
