from ukcompany.derive import derive_all, derive_profile
from ukcompany.rules import REGISTRY, generate_rules_md
from ukcompany.score import score_all, score_company, summarise


def flag_ids(flags):
    return {f["rule_id"] for f in flags}


def test_derive_clean_profile(profile_clean):
    a = derive_profile(profile_clean)
    assert a["found"] and a["company_status"] == "active"
    assert a["accounts_overdue"] is False  # read from non-deprecated next_accounts.overdue
    assert a["age_months"] == (2026 - 2011) * 12 + (8 - 5)
    assert a["excluded_status"] is False
    assert a["sic_codes"] == "47110"


def test_derive_minimal_old_record_no_keyerrors(profile_minimal):
    a = derive_profile(profile_minimal)
    assert a["found"]
    assert a["age_months"] is None  # no date_of_creation
    assert a["accounts_overdue"] is None
    assert a["excluded_status"] is False


def test_clean_company_no_noninfo_flags(profile_clean):
    a = derive_profile(profile_clean)
    flags = score_company(a)
    assert all(f["severity"] == "info" for f in flags)
    assert flags == []  # clean fixture: no charges, not young


def test_liquidation_fires_expected_rules(profile_liquidation, insolvency_case):
    records = derive_all([profile_liquidation], {"07654321": insolvency_case})
    flags = score_company(records[0])
    ids = flag_ids(flags)
    assert {"STATUS_INSOLVENT", "INSOLVENCY_ADVERSE", "ACCOUNTS_OVERDUE", "CS_OVERDUE"} <= ids
    # charges present but info severity (deprecated-boolean fallback path here)
    charge_flags = [f for f in flags if f["rule_id"] == "CHARGES_OUTSTANDING"]
    assert charge_flags and charge_flags[0]["severity"] == "info"
    # insolvency flag carries case-level evidence, not just a boolean
    ins = next(f for f in flags if f["rule_id"] == "INSOLVENCY_ADVERSE")
    assert "creditors-voluntary-liquidation" in ins["evidence"]
    assert "SOLVENT_WINDING_UP" not in ids


def test_mvl_is_solvent_context_not_adverse():
    from tests.conftest import load_insolvency, load_profile

    profile = load_profile("profile_mvl.json")
    cases = load_insolvency("insolvency_mvl.json", "04444444")
    records = derive_all([profile], {"04444444": cases})
    flags = score_company(records[0])
    ids = flag_ids(flags)
    # Members' voluntary liquidation: solvent winding-up. No high-severity rules.
    assert "STATUS_INSOLVENT" not in ids
    assert "INSOLVENCY_ADVERSE" not in ids
    assert "SOLVENT_WINDING_UP" in ids
    assert all(f["severity"] == "info" for f in flags)


def test_insolvency_indicated_but_uncached_fires_unclassified(profile_liquidation):
    # No insolvency resource in cache: rule fires as unclassified, not silent.
    records = derive_all([profile_liquidation])
    flags = score_company(records[0])
    ins = next(f for f in flags if f["rule_id"] == "INSOLVENCY_ADVERSE")
    assert "unclassified" in ins["evidence"]


def test_strikeoff_and_young(profile_strikeoff):
    a = derive_profile(profile_strikeoff)
    flags = score_company(a)
    ids = flag_ids(flags)
    assert "STATUS_STRIKEOFF" in ids
    assert "YOUNG_COMPANY" in ids  # incorporated 2024-11, observed 2026-08 -> 21 months
    young = next(f for f in flags if f["rule_id"] == "YOUNG_COMPANY")
    assert young["severity"] == "info"


def test_dissolved_is_excluded_not_scored(profile_dissolved, profile_clean):
    records = derive_all([profile_dissolved, profile_clean])
    result = score_all(records)
    assert [e["company_number"] for e in result["excluded"]] == ["02222222"]
    assert all(f["company_number"] != "02222222" for f in result["flags"])


def test_summary_excludes_info_from_flagged_count(profile_strikeoff):
    records = derive_all([profile_strikeoff])
    result = score_all(records)
    text = summarise(result, n_input=1)
    # strikeoff (high) + young (info): company counts as flagged because of the high
    assert "companies with >=1 non-info flag: 1" in text


def test_registry_metadata_complete():
    ids = [r.rule_id for r in REGISTRY]
    assert len(ids) == len(set(ids))
    for r in REGISTRY:
        assert r.severity in {"high", "medium", "low", "info"}
        assert r.tier == 1  # v1 promise: Tier-1 fields only
        assert r.definition and r.caveats


def test_rules_md_generated_from_registry():
    md = generate_rules_md()
    for r in REGISTRY:
        assert r.rule_id in md
    assert "do not edit by hand" in md
    assert "verified" not in md.split("without verifying")[1]  # no 'verified' claims


def test_data_dictionary_generated():
    from ukcompany.derive import FIELD_DOCS, generate_data_dictionary_md

    md = generate_data_dictionary_md()
    for f in FIELD_DOCS:
        assert str(f["field"]) in md
    assert "do not edit by hand" in md
