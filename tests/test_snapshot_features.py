"""Synthetic tests for the snapshot per-company features (Handoff 08, Tasks 2 & 3).

Builds a tiny synthetic BasicCompanyData zip, runs the feature build, and checks the values,
the governed/ungoverned tiers, and parity with derive_profile. All data synthetic: invented
names, public-format company numbers only.
"""

import csv
import io
import zipfile
from datetime import date, datetime
from types import SimpleNamespace

import duckdb

from ukcompany.derive import _months_between, derive_profile
from ukcompany.snapshot.features import GOVERNED_FEATURE_DROPPED, build_snapshot_features
from ukcompany.validation.labels import sic_section_from_code

SNAPSHOT_DATE = "2026-08-01"

# Every column the feature build references (clean names; the real file's leading-whitespace
# headers are handled by the resolver, which we exercise separately via the real data).
_FIELDS = [
    "CompanyName", "CompanyNumber", "RegAddress.AddressLine1", "RegAddress.PostCode",
    "CompanyCategory", "CompanyStatus", "IncorporationDate", "Accounts.NextDueDate",
    "Accounts.AccountCategory", "ConfStmtNextDueDate", "Mortgages.NumMortCharges",
    "Mortgages.NumMortOutstanding", "Mortgages.NumMortPartSatisfied",
    "Mortgages.NumMortSatisfied", "SICCode.SicText_1", "SICCode.SicText_2",
    "SICCode.SicText_3", "SICCode.SicText_4",
] + [f"PreviousName_{i}.CompanyName" for i in range(1, 11)]

_ROWS = [
    {"CompanyNumber": "00000001", "CompanyStatus": "Active",
     "CompanyCategory": "Private Limited Company", "IncorporationDate": "15/01/2020",
     "RegAddress.PostCode": "AB1 2CD", "RegAddress.AddressLine1": "1 High Street",
     "Accounts.AccountCategory": "MICRO ENTITY", "Accounts.NextDueDate": "01/01/2027",
     "ConfStmtNextDueDate": "01/01/2027", "Mortgages.NumMortCharges": "2",
     "Mortgages.NumMortOutstanding": "1", "Mortgages.NumMortPartSatisfied": "0",
     "Mortgages.NumMortSatisfied": "1",
     "SICCode.SicText_1": "62012 - Business and domestic software development",
     "PreviousName_1.CompanyName": "OLD NAME LTD"},
    {"CompanyNumber": "00000002", "CompanyStatus": "Active",
     "CompanyCategory": "Private Limited Company", "IncorporationDate": "01/01/2010",
     "RegAddress.PostCode": "AB1 2CD", "RegAddress.AddressLine1": "1 High Street",
     "Accounts.AccountCategory": "DORMANT", "Accounts.NextDueDate": "01/01/2020",
     "ConfStmtNextDueDate": "01/01/2020", "SICCode.SicText_1": "99999 - Dormant Company"},
    {"CompanyNumber": "00000003", "CompanyStatus": "Active",
     "CompanyCategory": "Private Limited Company", "IncorporationDate": "01/06/2023",
     "RegAddress.PostCode": "XY9 9ZZ", "RegAddress.AddressLine1": "9 Other Road",
     "Accounts.AccountCategory": "MICRO ENTITY", "Accounts.NextDueDate": "01/01/2027",
     "SICCode.SicText_1": "74990 - Non-trading company"},
    {"CompanyNumber": "00000004", "CompanyStatus": "Active",
     "CompanyCategory": "Private Limited Company", "IncorporationDate": "01/01/2000",
     "RegAddress.PostCode": "ZZ1 1ZZ", "RegAddress.AddressLine1": "4 Old Lane",
     "Accounts.AccountCategory": "NO ACCOUNTS FILED",
     "SICCode.SicText_1": "82990 - Business support service activities n.e.c."},
    {"CompanyNumber": "00000005", "CompanyStatus": "Active",
     "CompanyCategory": "Private Limited Company", "IncorporationDate": "01/07/2026",
     "RegAddress.PostCode": "ZZ2 2ZZ", "RegAddress.AddressLine1": "5 New Way",
     "Accounts.AccountCategory": "NO ACCOUNTS FILED",
     "SICCode.SicText_1": "62020 - Information technology consultancy activities"},
]


def _write_snapshot(tmp_path):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_FIELDS)
    writer.writeheader()
    for row in _ROWS:
        writer.writerow({field: row.get(field, "") for field in _FIELDS})
    zip_path = tmp_path / "BasicCompanyData-2099-01-01-part1_1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("BasicCompanyData-2099-01-01-part1_1.csv", buffer.getvalue())
    return str(tmp_path / "BasicCompanyData-*.zip")


def _rows_by_company(parquet_path):
    return {
        r["company_number"]: r
        for r in duckdb.sql(f"SELECT * FROM read_parquet('{parquet_path}')").df()
        .to_dict("records")
    }


def test_snapshot_feature_values(tmp_path):
    parts_glob = _write_snapshot(tmp_path)
    report = build_snapshot_features(
        parts_glob, tmp_path / "ungov", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["n_companies"] == 5
    rows = _rows_by_company(report["outputs"]["snapshot_company_features"])

    snap = date(2026, 8, 1)
    r1 = rows["00000001"]
    assert r1["age_months"] == _months_between(date(2020, 1, 15), snap)  # shared function
    assert r1["sic_sections"] == sic_section_from_code("62012")           # shared function
    assert r1["n_sic_codes"] == 1
    assert not r1["flag_dormant_sic"] and not r1["flag_non_trading_sic"]
    assert not r1["flag_nec_sic"]
    assert r1["n_previous_names"] == 1
    assert (r1["n_charges"], r1["n_charges_outstanding"], r1["n_charges_satisfied"]) == (2, 1, 1)
    assert not r1["accounts_overdue"] and not r1["confirmation_statement_overdue"]
    assert not r1["accounts_never_filed"]
    assert r1["n_companies_same_postcode"] == 2   # shares AB1 2CD with 00000002
    assert r1["n_companies_same_address"] == 2

    assert rows["00000002"]["flag_dormant_sic"]
    assert rows["00000002"]["accounts_overdue"]
    assert rows["00000002"]["confirmation_statement_overdue"]
    assert rows["00000003"]["flag_non_trading_sic"]
    assert rows["00000004"]["flag_nec_sic"]
    assert rows["00000004"]["accounts_never_filed"]         # NO ACCOUNTS FILED + incorp 2000
    assert not rows["00000005"]["accounts_never_filed"]     # incorporated < 21 months ago


def test_snapshot_feature_tiers(tmp_path):
    parts_glob = _write_snapshot(tmp_path)
    gov = build_snapshot_features(
        parts_glob, tmp_path / "gov", SNAPSHOT_DATE,
        data_governance=True, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    gov_cols = {c[0] for c in duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{gov['outputs']['snapshot_company_features']}')"
    ).fetchall()}
    assert not (gov_cols & set(GOVERNED_FEATURE_DROPPED))   # no exact-address column
    assert "n_companies_same_postcode" in gov_cols          # postcode concentration kept

    ungov = build_snapshot_features(
        parts_glob, tmp_path / "ungov", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    ungov_cols = {c[0] for c in duckdb.sql(
        f"DESCRIBE SELECT * FROM read_parquet('{ungov['outputs']['snapshot_company_features']}')"
    ).fetchall()}
    assert "n_companies_same_address" in ungov_cols


def test_snapshot_features_match_derive_profile(tmp_path):
    parts_glob = _write_snapshot(tmp_path)
    report = build_snapshot_features(
        parts_glob, tmp_path / "ungov", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    rows = _rows_by_company(report["outputs"]["snapshot_company_features"])
    bulk = rows["00000001"]

    # Reshape the same company into an API profile and run the reference path. fetched_at is
    # set to the snapshot date so age is compared on equal footing.
    api_profile = SimpleNamespace(
        company_number="00000001", not_found=False,
        fetched_at=datetime(2026, 8, 1),
        data={
            "company_name": "EXAMPLE LTD", "company_status": "active", "type": "ltd",
            "date_of_creation": "2020-01-15", "sic_codes": ["62012"],
            "previous_company_names": [{"name": "OLD NAME LTD"}],
            "accounts": {"next_accounts": {"due_on": "2027-01-01", "overdue": False}},
            "confirmation_statement": {"next_due": "2027-01-01", "overdue": False},
            "registered_office_address": {"postal_code": "AB1 2CD"},
            "has_charges": True, "links": {"charges": "/company/00000001/charges"},
        },
    )
    api = derive_profile(api_profile)

    assert str(bulk["date_of_creation"])[:10] == api["date_of_creation"]
    assert bulk["age_months"] == api["age_months"]
    assert bulk["n_previous_names"] == api["n_previous_names"]
    # sic sections from the same shared function / same codes
    assert bulk["sic_sections"] == sic_section_from_code(api["sic_codes"])
    assert (bulk["n_charges"] > 0) == bool(api["has_charges"])
    assert bool(bulk["accounts_overdue"]) == bool(api["accounts_overdue"])
    assert bool(bulk["confirmation_statement_overdue"]) == bool(
        api["confirmation_statement_overdue"])
