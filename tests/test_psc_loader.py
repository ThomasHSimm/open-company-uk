import json
from pathlib import Path

from ukcompany.psc.loader import GOVERNANCE_DROPPED_COLUMNS, load_psc

SNAPSHOT_DATE = "2026-09-18"
SECRET = "test-only-secret-never-used-for-anything-real"


def _write_part(tmp_path: Path, number: int, lines: list[str]) -> Path:
    path = tmp_path / f"psc-snapshot-{SNAPSHOT_DATE}_{number}of1.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def individual(
    company: str,
    psc_id: str,
    *,
    forename: str = "Alex",
    middle_name: str | None = "N",
    surname: str = "Example",
    dob_year: int = 1970,
    dob_month: int = 3,
    notified_on: str = "2018-01-01",
    ceased_on: str | None = None,
    postcode: str = "SA1 1AA",
) -> str:
    name_elements = {"forename": forename, "surname": surname, "title": "Ms"}
    if middle_name is not None:
        name_elements["middle_name"] = middle_name
    data = {
        "kind": "individual-person-with-significant-control",
        "name_elements": name_elements,
        "date_of_birth": {"year": dob_year, "month": dob_month},
        "nationality": "Wittish",
        "country_of_residence": "Wales",
        "address": {"address_line_1": "1 Example Street", "postal_code": postcode},
        "natures_of_control": [
            "ownership-of-shares-75-to-100-percent",
            "ownership-of-shares-75-to-100-percent-as-trust",
        ],
        "notified_on": notified_on,
        "links": {
            "self": f"/company/{company}/persons-with-significant-control/individual/{psc_id}"
        },
    }
    if ceased_on is not None:
        data["ceased_on"] = ceased_on
    return json.dumps({"company_number": company, "data": data})


def corporate(company: str, psc_id: str, reg_number: str = "SC119437") -> str:
    data = {
        "kind": "corporate-entity-person-with-significant-control",
        "name": "Example Holdings Limited",
        "identification": {
            "country_registered": "United Kingdom",
            "legal_authority": "United Kingdom",
            "legal_form": "Private Company Limited By Shares",
            "place_registered": "United Kingdom",
            "registration_number": reg_number,
        },
        "natures_of_control": ["ownership-of-shares-50-to-75-percent"],
        "notified_on": "2019-05-01",
        "links": {
            "self": f"/company/{company}/persons-with-significant-control/corporate-entity/{psc_id}"
        },
    }
    return json.dumps({"company_number": company, "data": data})


def statement(company: str, psc_id: str, code: str = "psc-exists-but-not-identified") -> str:
    data = {
        "kind": "persons-with-significant-control-statement",
        "statement": code,
        "notified_on": "2016-06-30",
        "links": {
            "self": f"/company/{company}/persons-with-significant-control-statements/{psc_id}"
        },
    }
    return json.dumps({"company_number": company, "data": data})


def super_secure(company: str, psc_id: str) -> str:
    data = {
        "kind": "super-secure-person-with-significant-control",
        "description": "super-secure-persons-with-significant-control",
        "ceased": False,
        "links": {"self": f"/company/{company}/persons-with-significant-control/super-secure/{psc_id}"},
    }
    return json.dumps({"company_number": company, "data": data})


def exemption(company: str) -> str:
    data = {
        "kind": "exemptions",
        "exemptions": {
            "psc_exempt_as_shares_admitted_on_market": {
                "exemption_type": "psc-exempt-as-shares-admitted-on-market",
                "items": [{"exempt_from": "2026-03-01"}],
            }
        },
        "links": {"self": f"/company/{company}/exemptions"},
    }
    return json.dumps({"company_number": company, "data": data})


def totals_line() -> str:
    data = {
        "kind": "totals#persons-of-significant-control-snapshot",
        "persons_of_significant_control_count": 6,
        "statements_count": 1,
        "exemptions_count": 1,
        "generated_at": f"{SNAPSHOT_DATE}T06:00:00Z",
    }
    return json.dumps({"data": data})


def test_load_covers_every_kind_and_accounting_invariant(tmp_path):
    lines = [
        individual("00000001", "psc001"),
        individual("00000002", "psc002", ceased_on="2023-02-10"),
        corporate("00000003", "psc003"),
        statement("00000004", "psc004"),
        super_secure("00000005", "psc005"),
        exemption("00000006"),
        totals_line(),
        "NOT VALID JSON AT ALL",
    ]
    _write_part(tmp_path, 1, lines)
    output_dir = tmp_path / "out"

    report = load_psc(
        str(tmp_path / "*.txt"),
        output_dir,
        SNAPSHOT_DATE,
        data_governance=False,
        memory_limit_gb=1,
        spill_dir=str(tmp_path / "spill"),
    )

    assert report["n_lines"] == len(lines)
    assert report["n_bad_lines"] == 1
    assert report["categories_sum_to_lines"] is True
    assert report["category_counts"] == {
        "individual": 2,
        "corporate": 1,
        "statement": 1,
        "super_secure": 1,
        "exemption": 1,
        "totals": 1,
        "unknown": 1,
    }
    assert report["unknown_kinds"] == {}  # the one unknown row is malformed, kind is NULL
    assert report["psc_totals_line"]["persons_of_significant_control_count"] == 6
    assert Path(report["outputs"]["psc_totals"]).exists()
    # Each individual() fixture carries 2 natures_of_control entries, corporate() carries 1.
    assert report["n_noc_assertions"] == 2 + 2 + 1


def test_middle_name_key_is_present_and_fill_rate_reported(tmp_path):
    _write_part(
        tmp_path, 1,
        [individual("00000001", "psc001", middle_name="N"), individual("00000002", "psc002", middle_name=None)],
    )
    report = load_psc(
        str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["middle_name_fill_individuals"] == {
        "key_name": "middle_name", "present": 1, "total": 2,
    }


def test_impossible_dates_are_flagged_not_fixed(tmp_path):
    lines = [
        # ceased before notified
        individual("00000001", "a", notified_on="2020-01-01", ceased_on="2019-01-01"),
        # pre-regime notified_on
        individual("00000002", "b", notified_on="2010-01-01"),
        # under 16 at notification (born 2020, notified 2021 -> age ~1 by naive year math)
        individual("00000003", "c", dob_year=2020, dob_month=1, notified_on="2021-06-01"),
    ]
    _write_part(tmp_path, 1, lines)
    report = load_psc(
        str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    flags = report["date_flags"]
    assert flags["f_ceased_before_notified"] == 1
    assert flags["f_pre_regime"] == 1
    assert flags["f_age_under_16_at_notified"] == 1
    # not fixed: the raw and cast values are still whatever was filed
    import duckdb

    con = duckdb.connect(":memory:")
    rows = con.sql(
        f"SELECT company_number, notified_on_raw, ceased_on_raw FROM "
        f"read_parquet('{tmp_path / 'out' / 'psc_records.parquet'}') "
        f"WHERE company_number = '00000001'"
    ).fetchall()
    assert rows == [("00000001", "2020-01-01", "2019-01-01")]


def test_company_number_mismatch_is_counted(tmp_path):
    data = {
        "kind": "individual-person-with-significant-control",
        "name_elements": {"forename": "Alex", "surname": "Example"},
        "notified_on": "2020-01-01",
        "links": {
            "self": "/company/00000099/persons-with-significant-control/individual/x"
        },
    }
    line = json.dumps({"company_number": "00000001", "data": data})  # top-level != links
    _write_part(tmp_path, 1, [line])
    report = load_psc(
        str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["company_number_mismatches"] == 1


def test_noc_suffix_families_and_base_rights(tmp_path):
    data = {
        "kind": "individual-person-with-significant-control",
        "name_elements": {"forename": "Alex", "surname": "Example"},
        "notified_on": "2020-01-01",
        "natures_of_control": [
            "ownership-of-shares-75-to-100-percent",
            "ownership-of-shares-75-to-100-percent-as-trust",
            "voting-rights-25-to-50-percent-as-firm",
        ],
        "links": {"self": "/company/00000001/persons-with-significant-control/individual/x"},
    }
    _write_part(tmp_path, 1, [json.dumps({"company_number": "00000001", "data": data})])
    output_dir = tmp_path / "out"
    load_psc(
        str(tmp_path / "*.txt"), output_dir, SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    import duckdb

    con = duckdb.connect(":memory:")
    rows = con.sql(
        f"SELECT right_raw, base_right, suffix_family FROM "
        f"read_parquet('{output_dir / 'psc_noc.parquet'}') ORDER BY right_raw"
    ).fetchall()
    assert rows == [
        ("ownership-of-shares-75-to-100-percent", "ownership-of-shares-75-to-100-percent", "plain"),
        (
            "ownership-of-shares-75-to-100-percent-as-trust",
            "ownership-of-shares-75-to-100-percent",
            "as-trust",
        ),
        (
            "voting-rights-25-to-50-percent-as-firm",
            "voting-rights-25-to-50-percent",
            "as-firm",
        ),
    ]


def test_data_governance_true_requires_a_secret(tmp_path):
    _write_part(tmp_path, 1, [individual("00000001", "a")])
    try:
        load_psc(
            str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
            data_governance=True, person_key_secret=None,
            memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "person_key_secret" in str(exc)


def test_data_governance_true_drops_every_listed_field_everywhere(tmp_path):
    lines = [
        # dob_year deliberately not a multiple of 5, so birth_band_5y (1985) differs from
        # the raw dob_year (1988) -- otherwise a leak of the raw year would be
        # indistinguishable from the intended banded value.
        individual("00000001", "a", forename="Alex", surname="Example", dob_year=1988, dob_month=7),
        individual("00000002", "b", ceased_on="2023-01-01"),
        corporate("00000003", "c"),
    ]
    _write_part(tmp_path, 1, lines)
    output_dir = tmp_path / "out"

    report = load_psc(
        str(tmp_path / "*.txt"), output_dir, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["data_governance"] is True

    import duckdb

    con = duckdb.connect(":memory:")
    records_path = output_dir / "psc_records.parquet"
    columns = {
        row[0] for row in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{records_path}')").fetchall()
    }
    assert columns.isdisjoint(set(GOVERNANCE_DROPPED_COLUMNS))

    # The forename "Alex" must not survive anywhere: not in a governed column, and not
    # smuggled through as a string value in some other column (e.g. a mis-scoped `raw`).
    # to_json(t) on the table alias serialises the whole row (every column) to one JSON
    # string per row; string_agg then lets a single substring search cover the entire table.
    all_text = con.sql(
        f"SELECT string_agg(to_json(t), '|') FROM read_parquet('{records_path}') AS t"
    ).fetchone()[0]
    assert "Alex" not in (all_text or "")
    assert "Example" not in (all_text or "")
    assert "1988" not in (all_text or "")

    # birth_band_5y and postcode_district replace the dropped fields with safe derivatives.
    row = con.sql(
        f"SELECT birth_band_5y, postcode_district, person_key FROM read_parquet('{records_path}') "
        f"WHERE company_number = '00000001'"
    ).fetchone()
    assert row[0] == 1985
    assert row[1] == "SA1"
    assert row[2] is not None and len(row[2]) == 64  # sha256 hex digest length


def test_bad_line_reasons_split_invalid_json_vs_missing_kind(tmp_path):
    lines = [
        individual("00000001", "a"),
        "NOT VALID JSON AT ALL",  # invalid_json
        json.dumps({"company_number": "00000002", "data": {}}),  # valid JSON, no kind
        json.dumps({"company_number": "00000003"}),  # valid JSON, no data at all
    ]
    _write_part(tmp_path, 1, lines)
    report = load_psc(
        str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["n_bad_lines"] == 3
    assert report["bad_line_reasons"] == {"invalid_json": 1, "missing_kind": 2}
    assert (
        report["bad_line_reasons"]["invalid_json"] + report["bad_line_reasons"]["missing_kind"]
        == report["n_bad_lines"]
    )


def test_postcode_district_only_from_valid_uk_format(tmp_path):
    lines = [
        individual("00000001", "a", postcode="SA1 1AA"),  # valid
        individual("00000002", "b", postcode="EH47 1AA"),  # valid, 4-char outward
        individual("00000003", "c", postcode="NOT A POSTCODE"),  # invalid format
        individual("00000004", "d", postcode="90210"),  # invalid format (US zip)
    ]
    _write_part(tmp_path, 1, lines)
    output_dir = tmp_path / "out"
    report = load_psc(
        str(tmp_path / "*.txt"), output_dir, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["postcode_format"] == {"present": 4, "valid_uk_format": 2, "invalid_format": 2}

    import duckdb

    con = duckdb.connect(":memory:")
    rows = dict(
        con.sql(
            f"SELECT company_number, postcode_district FROM "
            f"read_parquet('{output_dir / 'psc_records.parquet'}') ORDER BY company_number"
        ).fetchall()
    )
    assert rows == {
        "00000001": "SA1",
        "00000002": "EH47",
        "00000003": None,
        "00000004": None,
    }


def test_person_key_strict_requires_middle_name(tmp_path):
    lines = [
        individual("00000001", "a", forename="Alex", surname="Example", middle_name="N"),
        individual("00000002", "b", forename="Sam", surname="Example", middle_name=None),
    ]
    _write_part(tmp_path, 1, lines)
    output_dir = tmp_path / "out"
    report = load_psc(
        str(tmp_path / "*.txt"), output_dir, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["person_key_fill_individuals"] == {
        "person_key_eligible": 2,
        "person_key_strict_eligible": 1,
        "total": 2,
    }

    import duckdb

    con = duckdb.connect(":memory:")
    rows = {
        row[0]: (row[1], row[2])
        for row in con.sql(
            f"SELECT company_number, "
            f"  (person_key IS NOT NULL) AS has_key, "
            f"  (person_key_strict IS NOT NULL) AS has_strict_key "
            f"FROM read_parquet('{output_dir / 'psc_records.parquet'}') ORDER BY company_number"
        ).fetchall()
    }
    assert rows["00000001"] == (True, True)
    assert rows["00000002"] == (True, False)


def test_consistency_check_matches_report_stats(tmp_path):
    lines = [individual("00000001", "a"), corporate("00000002", "b")]
    _write_part(tmp_path, 1, lines)
    report = load_psc(
        str(tmp_path / "*.txt"), tmp_path / "out", SNAPSHOT_DATE,
        data_governance=False, memory_limit_gb=1, spill_dir=str(tmp_path / "spill"),
    )
    assert report["consistency_check"]["passed"] is True
    assert report["consistency_check"]["psc_noc_row_count_expected"] == report["n_noc_assertions"]


def test_person_key_is_deterministic_and_secret_dependent(tmp_path):
    _write_part(tmp_path, 1, [individual("00000001", "a", forename="Alex", surname="Example")])
    output_dir_1 = tmp_path / "out1"
    output_dir_2 = tmp_path / "out2"
    load_psc(
        str(tmp_path / "*.txt"), output_dir_1, SNAPSHOT_DATE,
        data_governance=True, person_key_secret=SECRET,
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill1"),
    )
    load_psc(
        str(tmp_path / "*.txt"), output_dir_2, SNAPSHOT_DATE,
        data_governance=True, person_key_secret="a-different-secret",
        memory_limit_gb=1, spill_dir=str(tmp_path / "spill2"),
    )
    import duckdb

    con = duckdb.connect(":memory:")
    key1 = con.sql(
        f"SELECT person_key FROM read_parquet('{output_dir_1 / 'psc_records.parquet'}')"
    ).fetchone()[0]
    key2 = con.sql(
        f"SELECT person_key FROM read_parquet('{output_dir_2 / 'psc_records.parquet'}')"
    ).fetchone()[0]
    assert key1 != key2
