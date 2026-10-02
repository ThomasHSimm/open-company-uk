"""Nature-of-control decomposition + the structured PSC features on derive_psc.

All synthetic. Company numbers are the only real identifiers used; no names,
nationality or personal fields appear anywhere here or in the outputs asserted.
"""

from datetime import UTC, datetime
from pathlib import Path

import yaml

from ukcompany.cache import CachedResponse
from ukcompany.derive import derive_psc
from ukcompany.psc_natures import (
    classify_kind,
    decompose_nature,
    is_uk_company_number_format,
    summarise_natures,
)

# The authoritative nature-of-control enumeration, vendored with its commit SHA.
_ENUM_FIXTURE = Path(__file__).parent / "fixtures" / "psc_descriptions_natures.yml"

OBSERVED_AT = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


# --- shared module: decompose_nature -------------------------------------------


def test_decompose_plain_ownership_band():
    p = decompose_nature("ownership-of-shares-25-to-50-percent")
    assert (p.core, p.suffix_family, p.band) == (
        "ownership-of-shares",
        "plain",
        "25-to-50-percent",
    )


def test_decompose_suffix_families():
    assert decompose_nature("voting-rights-50-to-75-percent-as-firm").suffix_family == "as-firm"
    assert decompose_nature("voting-rights-50-to-75-percent-as-trust").suffix_family == "as-trust"
    llp = decompose_nature(
        "right-to-share-surplus-assets-75-to-100-percent-limited-liability-partnership"
    )
    assert llp.suffix_family == "limited-liability-partnership"
    assert llp.core == "right-to-share-surplus-assets"
    assert llp.band == "75-to-100-percent"


def test_decompose_appointment_and_influence():
    assert decompose_nature("right-to-appoint-and-remove-directors").core == (
        "right-to-appoint-and-remove"
    )
    members = decompose_nature(
        "right-to-appoint-and-remove-members-limited-liability-partnership"
    )
    assert members.core == "right-to-appoint-and-remove"
    assert decompose_nature("significant-influence-or-control").core == (
        "significant-influence-or-control"
    )
    assert decompose_nature("significant-influence-or-control-as-firm").core == (
        "significant-influence-or-control"
    )


def test_decompose_roe_more_than_band_captured_but_not_ranked():
    # ROE phrases its threshold as "more-than-25-percent": the band is CAPTURED (not
    # lost), the core is recognised; it is excluded from the max-band ranking separately
    # (see test_summarise_roe_only_ownership_has_no_band).
    p = decompose_nature(
        "ownership-of-shares-more-than-25-percent-registered-overseas-entity"
    )
    assert p.core == "ownership-of-shares"
    assert p.suffix_family == "registered-overseas-entity"
    assert p.band == "more-than-25-percent"


def test_decompose_compound_suffixes_and_nominee():
    p = decompose_nature(
        "ownership-of-shares-more-than-25-percent-as-control-over-trust-registered-overseas-entity"
    )
    assert p.core == "ownership-of-shares"
    assert p.suffix_family == "as-control-over-trust-registered-overseas-entity"
    assert p.band == "more-than-25-percent"

    llp = decompose_nature(
        "right-to-share-surplus-assets-75-to-100-percent-as-firm-limited-liability-partnership"
    )
    assert llp.core == "right-to-share-surplus-assets"
    assert llp.suffix_family == "as-firm-limited-liability-partnership"
    assert llp.band == "75-to-100-percent"

    part = decompose_nature("part-right-to-share-surplus-assets-25-to-50-percent-as-trust")
    assert part.core == "part-right-to-share-surplus-assets"
    assert part.suffix_family == "as-trust"

    nominee = decompose_nature(
        "registered-owner-as-nominee-person-scotland-registered-overseas-entity"
    )
    assert nominee.core == "registered-owner-as-nominee"
    assert nominee.band is None


def test_every_published_nature_code_decomposes_no_unmapped():
    # The whole point of the shared module: nothing in the authoritative enumeration
    # falls through to `unmapped` (which would mean a wrong or lost right).
    codes = sorted(yaml.safe_load(_ENUM_FIXTURE.read_text(encoding="utf-8"))["description"])
    assert len(codes) == 86  # authoritative count, psc_descriptions.yml @ 0d3fb78
    unmapped = [c for c in codes if decompose_nature(c).core is None]
    assert unmapped == [], f"codes with unrecognised core: {unmapped}"


def test_decompose_unknown_core_is_unmapped():
    p = decompose_nature("some-brand-new-right-2027")
    assert p.core is None


# --- shared module: summarise_natures ------------------------------------------


def test_summarise_picks_max_bands_and_flags():
    summary = summarise_natures(
        [
            "ownership-of-shares-25-to-50-percent",
            "ownership-of-shares-75-to-100-percent",  # higher -> wins
            "voting-rights-50-to-75-percent",
            "right-to-appoint-and-remove-directors",
            "significant-influence-or-control",
        ]
    )
    assert summary.max_ownership_band == "75-to-100-percent"
    assert summary.max_voting_band == "50-to-75-percent"
    assert summary.has_appointment_rights is True
    assert summary.has_significant_influence is True
    assert summary.n_distinct_natures == 5
    assert summary.unmapped == ()


def test_summarise_unmapped_collected_distinct_counts_all():
    summary = summarise_natures(
        ["ownership-of-shares-25-to-50-percent", "mystery-code", "mystery-code"]
    )
    assert summary.unmapped == ("mystery-code",)
    assert summary.n_distinct_natures == 2  # mystery-code deduped
    assert summary.max_ownership_band == "25-to-50-percent"


def test_summarise_roe_only_ownership_has_no_band():
    summary = summarise_natures(
        ["ownership-of-shares-more-than-25-percent-registered-overseas-entity"]
    )
    assert summary.max_ownership_band is None  # core mapped, band unmapped
    assert summary.unmapped == ()  # the code itself is recognised


# --- shared module: classify_kind + UK-format ----------------------------------


def test_classify_kind():
    assert classify_kind("individual-person-with-significant-control") == "individual"
    assert classify_kind("corporate-entity-person-with-significant-control") == "corporate"
    assert classify_kind("legal-person-person-with-significant-control") == "legal-person"
    assert classify_kind("super-secure-person-with-significant-control") == "super-secure"
    assert classify_kind("corporate-entity-beneficial-owner") == "corporate"  # ROE variant
    assert classify_kind("something-else") == "other"
    assert classify_kind(None) == "other"


def test_is_uk_company_number_format():
    assert is_uk_company_number_format("12345678") is True
    assert is_uk_company_number_format("SC123456") is True
    assert is_uk_company_number_format("OC301234") is True
    assert is_uk_company_number_format("DE-HRB-12345") is False  # foreign form
    assert is_uk_company_number_format(None) is False
    # Documented caveat: the normaliser zero-pads short all-digit ids, so this reads
    # as UK-format. Asserted to pin the behaviour, not to endorse it as a match.
    assert is_uk_company_number_format("99") is True


# --- derive_psc: structured features end-to-end --------------------------------


def _psc_list(items: list[dict], **top) -> CachedResponse:
    data = {"items": items, "total_results": len(items)}
    data.update(top)
    return CachedResponse(
        company_number="00000077",
        endpoint="psc",
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://psc",
        data=data,
    )


def _statements(items: list[dict]) -> CachedResponse:
    return CachedResponse(
        company_number="00000077",
        endpoint="psc_statements",
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://psc_statements",
        data={"items": items, "total_results": len(items)},
    )


def _not_found(endpoint: str) -> CachedResponse:
    return CachedResponse(
        company_number="00000077",
        endpoint=endpoint,
        status_code=404,
        fetched_at=OBSERVED_AT,
        url=f"fixture://{endpoint}",
        data=None,
    )


def test_derive_psc_structured_features_active_only():
    out = derive_psc(
        _psc_list(
            [
                {
                    "kind": "individual-person-with-significant-control",
                    "natures_of_control": [
                        "ownership-of-shares-25-to-50-percent",
                        "voting-rights-25-to-50-percent",
                    ],
                },
                {
                    "kind": "corporate-entity-person-with-significant-control",
                    "natures_of_control": [
                        "ownership-of-shares-75-to-100-percent",
                        "right-to-appoint-and-remove-directors",
                        "significant-influence-or-control",
                    ],
                    "identification": {
                        "registration_number": "09876543",
                        "country_registered": "England",
                    },
                },
                # ceased record must be ignored entirely:
                {
                    "kind": "individual-person-with-significant-control",
                    "ceased": True,
                    "natures_of_control": ["voting-rights-75-to-100-percent"],
                },
            ]
        ),
        _statements([]),
    )
    assert out["psc_max_ownership_band"] == "75-to-100-percent"
    assert out["psc_max_voting_band"] == "25-to-50-percent"  # ceased 75-100 ignored
    assert out["psc_has_appointment_rights"] is True
    assert out["psc_has_significant_influence"] is True
    # 5 distinct active natures (2 from the individual + 3 from the corporate); the
    # ceased record's voting-75-100 nature is excluded.
    assert out["psc_n_distinct_natures"] == 5
    assert out["psc_n_individual"] == 1  # ceased individual excluded
    assert out["psc_n_corporate"] == 1
    assert out["psc_n_legal_person"] == 0
    assert out["psc_n_super_secure"] == 0
    assert out["psc_corporate_reg_numbers"] == "09876543"
    assert out["psc_n_corporate_uk_format_regno"] == 1
    assert out["psc_unmapped_natures"] is None


def test_derive_psc_corporate_reg_non_uk_not_counted():
    out = derive_psc(
        _psc_list(
            [
                {
                    "kind": "corporate-entity-person-with-significant-control",
                    "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
                    "identification": {
                        "registration_number": "DELAWARE-55-1234",
                        "country_registered": "United States",
                    },
                }
            ]
        ),
        _statements([]),
    )
    assert out["psc_corporate_reg_numbers"] == "DELAWARE-55-1234"  # captured verbatim
    assert out["psc_n_corporate_uk_format_regno"] == 0  # not UK-format
    assert out["psc_n_corporate"] == 1


def test_derive_psc_unmapped_nature_surfaced():
    out = derive_psc(
        _psc_list(
            [
                {
                    "kind": "individual-person-with-significant-control",
                    "natures_of_control": ["ownership-of-shares-25-to-50-percent", "mystery-2027"],
                }
            ]
        ),
        _statements([]),
    )
    assert out["psc_unmapped_natures"] == "mystery-2027"
    assert out["psc_max_ownership_band"] == "25-to-50-percent"


def test_derive_psc_features_zero_on_404():
    out = derive_psc(_not_found("psc"), _not_found("psc_statements"))
    assert out["psc_max_ownership_band"] is None
    assert out["psc_max_voting_band"] is None
    assert out["psc_has_appointment_rights"] is False  # cached 404 = legitimately none
    assert out["psc_has_significant_influence"] is False
    assert out["psc_n_distinct_natures"] == 0
    assert out["psc_n_individual"] == 0
    assert out["psc_n_corporate"] == 0
    assert out["psc_corporate_reg_numbers"] is None
    assert out["psc_n_corporate_uk_format_regno"] == 0


def test_derive_psc_features_none_when_not_fetched():
    out = derive_psc(None, None)
    assert out["psc_max_ownership_band"] is None
    assert out["psc_has_appointment_rights"] is None  # unknown, not False
    assert out["psc_has_significant_influence"] is None
    assert out["psc_n_distinct_natures"] is None
    assert out["psc_n_individual"] is None
    assert out["psc_n_corporate"] is None
    assert out["psc_n_corporate_uk_format_regno"] is None
