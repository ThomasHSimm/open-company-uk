import csv

from ukcompany.cache import RawCache
from ukcompany.validation.evaluate import evaluate
from ukcompany.validation.labels import Label, load_labels
from ukcompany.validation.report import render_report


def _write_labels(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["company_number", "case_type", "is_bulk"])
        writer.writeheader()
        writer.writerows(rows)


def test_load_labels_filters_normalises_and_reports_unusable(tmp_path):
    path = tmp_path / "labels.csv"
    _write_labels(
        path,
        [
            {"company_number": "46914", "case_type": "Compulsory liquidation", "is_bulk": ""},
            {"company_number": "OC411823", "case_type": "Administration", "is_bulk": "NA"},
            {
                "company_number": "123",
                "case_type": "Creditors voluntary liquidation",
                "is_bulk": "Y",
            },
            {"company_number": "7654321", "case_type": "Administration to CVL", "is_bulk": ""},
            {"company_number": "IP23540R", "case_type": "Administration", "is_bulk": ""},
        ],
    )

    loaded = load_labels(path)

    assert set(loaded.labels) == {"00046914", "OC411823"}
    assert loaded.labels["00046914"].case_type == "compulsory_liquidation"
    assert loaded.labels["00046914"].raw_case_type == "Compulsory liquidation"
    assert loaded.dropped_bulk == 1
    assert loaded.dropped_administration_to_cvl == 1
    assert len(loaded.unusable) == 1
    assert loaded.unusable[0].raw == "IP23540R"
    assert loaded.unusable[0].number is None
    assert loaded.input_rows == 5


def test_field_shifted_rows_are_quarantined_not_labelled(tmp_path):
    path = tmp_path / "labels.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "company_number",
                "case_type",
                "is_bulk",
                "sic07_2_digit",
                "month_registered",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                # Clean row: valid YYYY-MM month -> retained.
                {
                    "company_number": "46914",
                    "case_type": "Compulsory liquidation",
                    "is_bulk": "",
                    "sic07_2_digit": "62",
                    "month_registered": "2016-05",
                },
                # Field-shifted row: a case_type string sits in month_registered.
                {
                    "company_number": "7654321",
                    "case_type": "Administration",
                    "is_bulk": "",
                    "sic07_2_digit": "London",
                    "month_registered": "In Administration",
                },
            ]
        )

    loaded = load_labels(path)

    assert set(loaded.labels) == {"00046914"}
    assert loaded.labels["00046914"].month_registered == "2016-05"
    assert loaded.labels["00046914"].sic_section == "J"
    assert loaded.unusable_shifted == 1
    assert loaded.shifted_samples == ["In Administration"]


def _profile(number, status="active", **extra):
    return {
        "company_number": number,
        "company_name": f"SYNTHETIC {number}",
        "company_status": status,
        **extra,
    }


def test_evaluate_outcome_buckets_and_conditional_recall(tmp_path):
    cache = RawCache(tmp_path / "raw")
    cache.write(
        "00000001",
        "profile",
        200,
        "fixture://flagged",
        _profile("00000001", "liquidation"),
    )
    cache.write("00000002", "profile", 404, "fixture://404", None)
    cache.write("00000003", "profile", 200, "fixture://moved", _profile("00000003"))
    cache.write("00000004", "profile", 200, "fixture://miss", _profile("00000004", "unknown"))
    cache.write("00000006", "profile", 200, "fixture://excluded", _profile("00000006", "dissolved"))
    labels = {
        number: Label("compulsory_liquidation", "Compulsory liquidation")
        for number in ["00000001", "00000002", "00000003", "00000004", "00000005", "00000006"]
    }

    result = evaluate(labels, cache)

    assert result.counts() == {
        "flagged_adverse": 1,
        "excluded": 1,
        "missed_404": 1,
        "missed_status_moved": 1,
        "missed_genuine": 1,
        "not_fetched": 1,
    }
    assert result.recall() == 0.5


def test_evaluate_is_scoped_to_explicit_positive_cohort(tmp_path):
    cache = RawCache(tmp_path / "raw")
    for number in ("00000001", "00000002"):
        cache.write(number, "profile", 200, "fixture://flagged", _profile(number, "liquidation"))
    labels = {
        number: Label("compulsory_liquidation", "Compulsory liquidation")
        for number in ("00000001", "00000002")
    }

    result = evaluate(labels, cache, positive_numbers={"00000001"})

    assert len(result.outcomes) == 1
    assert result.outcomes[0].company_number == "00000001"


def test_solvent_winding_up_on_adverse_label_is_loud_error(tmp_path):
    cache = RawCache(tmp_path / "raw")
    number = "00000006"
    cache.write(number, "profile", 200, "fixture://mvl", _profile(number, "liquidation"))
    cache.write(
        number,
        "insolvency",
        200,
        "fixture://mvl-cases",
        {"cases": [{"type": "members-voluntary-liquidation"}]},
    )
    labels = {number: Label("compulsory_liquidation", "Compulsory liquidation")}

    result = evaluate(labels, cache)
    report = render_report(
        result,
        type(
            "Labels",
            (),
            {
                "input_rows": 1,
                "labels": labels,
                "dropped_bulk": 0,
                "dropped_administration_to_cvl": 0,
                "unusable": [],
                "duplicate_rows": 0,
                "unusable_shifted": 0,
            },
        )(),
    )

    assert [row.company_number for row in result.solvent_winding_up_errors] == [number]
    assert "**ERROR:" in report
    assert number in report
