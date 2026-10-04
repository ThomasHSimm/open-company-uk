"""Synthetic parity test for the bulk per-company PSC features (Handoff 07, Tasks 2 & 3).

Builds a tiny synthetic snapshot, loads it in governed mode, builds the feature table, and
asserts every overlapping feature equals what ukcompany.derive.derive_psc produces from the
same records reshaped into the per-company API's shape. This is the unit-scale proof of the
"one definition" claim: both paths call the same psc_natures functions, so they must agree.

All data synthetic: invented names, public-format company numbers only.
"""

import json
from types import SimpleNamespace

import duckdb

from ukcompany.derive import derive_psc
from ukcompany.psc.features import GOVERNED_FEATURE_DROPPED, build_psc_features
from ukcompany.psc.loader import load_psc

SNAPSHOT_DATE = "2026-09-25"
SECRET = "test-only-secret-never-used-for-anything-real"

# Set-valued features whose order is an artefact of record order (which the bulk snapshot
# does not preserve), so parity compares them as sets, not strings.
SET_VALUED = {"psc_corporate_reg_numbers", "active_psc_statement_codes"}
COMPARE_FEATURES = (
    "psc_n_records", "psc_n_ceased", "psc_natures_of_control",
    "psc_max_ownership_band", "psc_max_voting_band", "psc_has_appointment_rights",
    "psc_has_significant_influence", "psc_n_distinct_natures",
    "psc_n_individual", "psc_n_corporate", "psc_n_legal_person", "psc_n_super_secure",
    "psc_corporate_reg_numbers", "psc_n_corporate_uk_format_regno", "psc_unmapped_natures",
    "n_psc_id_verified", "n_psc_id_verification_due", "n_psc_id_statement_filed",
    "active_psc_statement_codes", "psc_information_state",
)


def _individual(company, psc_id, *, forename="Alex", surname="Example", dob_year=1970,
                dob_month=3, natures=None, ceased_on=None, iv=None):
    data = {
        "kind": "individual-person-with-significant-control",
        "name_elements": {"forename": forename, "surname": surname, "title": "Ms"},
        "date_of_birth": {"year": dob_year, "month": dob_month},
        "address": {"address_line_1": "1 Example Street", "postal_code": "SA1 1AA"},
        "natures_of_control": natures if natures is not None else [
            "ownership-of-shares-75-to-100-percent",
            "voting-rights-25-to-50-percent",
        ],
        "notified_on": "2018-01-01",
        "links": {"self": f"/company/{company}/persons-with-significant-control/individual/{psc_id}"},
    }
    if ceased_on is not None:
        data["ceased_on"] = ceased_on
    if iv is not None:
        data["identity_verification_details"] = iv
    return company, data


def _corporate(company, psc_id, reg_number="SC119437"):
    data = {
        "kind": "corporate-entity-person-with-significant-control",
        "name": "Example Holdings Limited",
        "identification": {"registration_number": reg_number, "country_registered": "UK"},
        "natures_of_control": ["ownership-of-shares-50-to-75-percent"],
        "notified_on": "2019-05-01",
        "links": {"self": f"/company/{company}/.../corporate-entity/{psc_id}"},
    }
    return company, data


def _statement(company, psc_id, code="psc-exists-but-not-identified"):
    data = {
        "kind": "persons-with-significant-control-statement",
        "statement": code, "notified_on": "2016-06-30",
        "links": {"self": f"/company/{company}/persons-with-significant-control-statements/{psc_id}"},
    }
    return company, data


def _super_secure(company, psc_id):
    data = {
        "kind": "super-secure-person-with-significant-control",
        "description": "super-secure-persons-with-significant-control", "ceased": False,
        "links": {"self": f"/company/{company}/.../super-secure/{psc_id}"},
    }
    return company, data


def _exemption(company):
    data = {"kind": "exemptions", "exemptions": {}, "links": {"self": f"/company/{company}/exemptions"}}
    return company, data


def _totals(persons, statements, exemptions):
    return None, {
        "kind": "totals#persons-of-significant-control-snapshot",
        "persons_of_significant_control_count": persons,
        "statements_count": statements, "exemptions_count": exemptions,
    }


# PSC kinds the API list endpoint returns (person records), to split a company's records into
# the derive_psc `psc` resource vs the separate `statements` resource.
_PERSON_KINDS = {
    "individual-person-with-significant-control",
    "corporate-entity-person-with-significant-control",
    "legal-person-person-with-significant-control",
    "super-secure-person-with-significant-control",
}


def _build_snapshot(tmp_path):
    specs = [
        _individual("00000001", "p1", forename="Alex", surname="Unique"),  # ownership+voting
        _individual("00000002", "p2", forename="Bo", surname="Ceased",
                    ceased_on="2023-02-10"),  # ceased -> no active natures
        _corporate("00000003", "p3"),   # corporate, UK-format regno
        _statement("00000004", "p4"),   # statement only
        _super_secure("00000005", "p5"),  # super-secure person
        _exemption("00000006"),         # exemption only -> none_reported
        _individual("00000007", "p7", forename="Val", surname="Verified", iv={
            "appointment_verification_statement_due_on": "2026-01-01"}),  # IV block
        _individual("00000008", "p8", forename="Sam", surname="Shared", dob_year=1985, dob_month=6),
        _individual("00000009", "p9", forename="Sam", surname="Shared", dob_year=1985, dob_month=6),
    ]
    # 7 person records (1,2,3,5,7,8,9), 1 statement (4), 1 exemption (6).
    lines = []
    by_company = {}
    for company, data in specs:
        rec = {"data": data}
        if company is not None:
            rec["company_number"] = company
            by_company.setdefault(company, []).append(data)
        lines.append(json.dumps(rec))
    _, totals = _totals(7, 1, 1)
    lines.append(json.dumps({"data": totals}))
    part = tmp_path / f"psc-snapshot-{SNAPSHOT_DATE}_1of1.txt"
    part.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return by_company


def _derive_for_company(items):
    person_items = [d for d in items if d.get("kind") in _PERSON_KINDS]
    statement_items = [d for d in items if d.get("kind") == "persons-with-significant-control-statement"]
    psc = SimpleNamespace(not_found=False, company_number="x", data={"items": person_items})
    statements = SimpleNamespace(not_found=False, company_number="x", data={"items": statement_items})
    return derive_psc(psc, statements)


def test_bulk_features_match_derive_psc_per_company(tmp_path):
    by_company = _build_snapshot(tmp_path)
    load_dir = tmp_path / "load"
    load_psc(
        str(tmp_path / "*.txt"), load_dir, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    out = tmp_path / "features"
    build_psc_features(
        load_dir / "psc_records.parquet", load_dir / "psc_noc.parquet", out, SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    rows = {
        r[0]: r[1]
        for r in [
            (row["company_number"], row)
            for row in duckdb.sql(
                f"SELECT * FROM read_parquet('{out / 'psc_company_features.parquet'}')"
            ).df().to_dict("records")
        ]
    }
    assert set(rows) == set(by_company)  # one row per company in the snapshot

    for company, items in by_company.items():
        expected = _derive_for_company(items)
        got = rows[company]
        for feature in COMPARE_FEATURES:
            exp, val = expected[feature], got[feature]
            # Normalise pandas NaN (NULL varchar read via .df()) to None first; NaN is
            # truthy, so this must happen before any `val or ""`.
            if isinstance(val, float) and val != val:
                val = None
            if feature in SET_VALUED:
                exp_set = set((exp or "").split(",")) - {""}
                val_set = set((val or "").split(",")) - {""}
                assert exp_set == val_set, f"{company}.{feature}: {val_set} != {exp_set}"
            else:
                assert val == exp, f"{company}.{feature}: {val!r} != {exp!r}"


def test_feature_tiers_governance_and_bands(tmp_path):
    _build_snapshot(tmp_path)
    load_dir = tmp_path / "load"
    load_psc(
        str(tmp_path / "*.txt"), load_dir, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    records = load_dir / "psc_records.parquet"
    noc = load_dir / "psc_noc.parquet"

    governed = build_psc_features(
        records, noc, tmp_path / "gov", SNAPSHOT_DATE,
        data_governance=True, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    gov_cols = {c[0] for c in duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{governed['outputs']['psc_company_features']}')"
    ).fetchall()}
    assert not (gov_cols & set(GOVERNED_FEATURE_DROPPED))  # no person-linkage column exists

    private = build_psc_features(
        records, noc, tmp_path / "priv", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    priv_cols = {c[0] for c in duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{private['outputs']['psc_company_features']}')"
    ).fetchall()}
    assert {"companies_per_person_band_ever", "companies_per_person_band_active"} <= priv_cols

    rows = {
        row["company_number"]: row
        for row in duckdb.sql(
            f"SELECT company_number, companies_per_person_band_ever, "
            f"companies_per_person_band_active "
            f"FROM read_parquet('{private['outputs']['psc_company_features']}')"
        ).df().to_dict("records")
    }

    def _none_if_nan(v):
        return None if (v is None or (isinstance(v, float) and v != v)) else v

    # All synthetic individuals are active, so ever and active bands coincide here.
    for scope in ("companies_per_person_band_ever", "companies_per_person_band_active"):
        assert rows["00000001"][scope] == "1"       # unique individual, one company
        assert rows["00000008"][scope] == "2-10"    # Sam Shared controls 00000008 + 00000009
        assert rows["00000009"][scope] == "2-10"
        assert _none_if_nan(rows["00000003"][scope]) is None  # corporate PSC: no band
