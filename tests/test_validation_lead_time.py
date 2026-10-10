import csv
import json

import polars as pl

from ukcompany.validation.lead_time import build_case_cohort, run_lead_time_analysis


def _write_labels(path):
    fields = [
        "company_number",
        "company_name",
        "register_location",
        "case_type",
        "month_registered",
        "sic07_2_digit",
        "is_bulk",
    ]
    rows = [
        ("00000001", "A", "England", "Creditors Voluntary Liquidation", "2020-07", "62", ""),
        ("00000001", "A", "England", "In Administration", "2020-08", "62", ""),
        ("00000002", "B", "England", "Compulsory Liquidation", "2020-07", "41", ""),
        ("00000003", "C", "England", "Moratorium", "2020-07", "70", ""),
        ("00000004", "D", "England", "Creditors Voluntary Liquidation", "2014-12", "62", ""),
        ("00000005", "E", "England", "In Administration", "2020-07", "62", "Y"),
        ("00000006", "F", "England", "Administration to CVL", "2020-07", "62", ""),
        ("IP12345R", "G", "England", "In Administration", "2020-07", "62", ""),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def _write_accounts(wide_path, provenance_path):
    wide = pl.DataFrame(
        [
            {
                "company": "00000001",
                "period_end": "2018-12-31",
                "Equity": 100.0,
                "CurrentAssets": 80.0,
                "creditors_within_one_year": 40.0,
                "NetCurrentAssetsLiabilities": -10.0,
                "CashBankOnHand": 25.0,
                "AverageNumberEmployeesDuringPeriod": 12.0,
                "employees_unit_anomaly": 1,
                "row_available_yyyymm": 202002,
            },
            {
                "company": "00000001",
                "period_end": "2017-12-31",
                "Equity": 75.0,
                "CurrentAssets": None,
                "creditors_within_one_year": None,
                "NetCurrentAssetsLiabilities": None,
                "CashBankOnHand": None,
                "AverageNumberEmployeesDuringPeriod": None,
                "employees_unit_anomaly": None,
                "row_available_yyyymm": 201905,
            },
            {
                "company": "00000002",
                "period_end": "2018-06-30",
                "Equity": None,
                "CurrentAssets": None,
                "creditors_within_one_year": None,
                "NetCurrentAssetsLiabilities": None,
                "CashBankOnHand": 5.0,
                "AverageNumberEmployeesDuringPeriod": None,
                "employees_unit_anomaly": None,
                "row_available_yyyymm": 201908,
            },
        ]
    )
    provenance = pl.DataFrame(
        [
            ("00000001", "2018-12-31", "Equity", 2019, 6),
            ("00000001", "2018-12-31", "CurrentAssets", 2019, 7),
            ("00000001", "2018-12-31", "creditors_within_one_year", 2019, 7),
            ("00000001", "2018-12-31", "NetCurrentAssetsLiabilities", 2019, 7),
            ("00000001", "2018-12-31", "CashBankOnHand", 2020, 2),
            ("00000001", "2018-12-31", "AverageNumberEmployeesDuringPeriod", 2019, 7),
            ("00000001", "2017-12-31", "Equity", 2019, 5),
            ("00000002", "2018-06-30", "CashBankOnHand", 2019, 8),
        ],
        schema=["company", "period_end", "wide_column", "source_year", "source_month"],
        orient="row",
    ).with_columns(
        pl.lit("fixture.xml").alias("source_member"),
        pl.col("period_end").alias("made_up_to_date"),
    )
    wide.write_parquet(wide_path)
    provenance.write_parquet(provenance_path)


def _summary(report, lead, convention):
    return next(
        row
        for row in report["cutoff_summary"]
        if row["lead_months"] == lead and row["convention"] == convention
    )


def test_case_cohort_reuses_loader_dispositions_and_ignores_current_register(tmp_path):
    labels = tmp_path / "labels.csv"
    _write_labels(labels)

    cohort = build_case_cohort(labels)

    assert cohort.frame["company_number"].to_list() == ["00000001", "00000002"]
    assert cohort.flow == {
        "input_rows": 8,
        "dropped_bulk": 1,
        "dropped_administration_to_cvl": 1,
        "unusable_company_number": 1,
        "unusable_month": 0,
        "duplicate_rows": 1,
        "retained_unique_companies_events": 4,
        "unsupported_retained_event_type": 1,
        "supported_unique_companies_events": 3,
        "event_before_2015_01": 1,
        "event_after_2024_04": 0,
        "candidate_unique_companies_events": 2,
        "candidate_by_case_type": {
            "compulsory_liquidation": 1,
            "creditors_voluntary_liquidation": 1,
        },
    }


def test_cell_provenance_excludes_later_fills_without_row_availability(tmp_path):
    labels = tmp_path / "labels.csv"
    wide = tmp_path / "wide.parquet"
    provenance = tmp_path / "provenance.parquet"
    _write_labels(labels)
    _write_accounts(wide, provenance)

    report = run_lead_time_analysis(
        labels,
        wide,
        provenance,
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )
    primary = _summary(report, 12, "registration_month")

    assert report["specification"]["uses_row_available_yyyymm"] is False
    assert primary["candidates"] == 2
    assert primary["any_accounts"] == 1
    assert primary["equity_observed"] == 1
    assert primary["cash_observed"] == 0
    assert primary["d_equity_observed"] == 1


def test_missing_is_distinct_from_observed_false_and_one_cycle_lag(tmp_path):
    labels = tmp_path / "labels.csv"
    wide = tmp_path / "wide.parquet"
    provenance = tmp_path / "provenance.parquet"
    _write_labels(labels)
    _write_accounts(wide, provenance)

    report = run_lead_time_analysis(
        labels,
        wide,
        provenance,
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )
    primary = _summary(report, 12, "registration_month")
    lagged = _summary(report, 12, "one_cycle_lag")

    assert primary["negative_equity_observed"] == 1
    assert primary["negative_equity_true"] == 0
    assert primary["net_current_liabilities_observed"] == 1
    assert primary["net_current_liabilities_true"] == 1
    assert primary["employees_unit_anomaly_observed"] == 1
    assert primary["employees_unit_anomaly_true"] == 1
    assert lagged["equity_observed"] == 1
    assert lagged["net_current_assets_observed"] == 0
    assert lagged["employees_unit_anomaly_observed"] == 0


def test_output_is_aggregate_only(tmp_path):
    labels = tmp_path / "labels.csv"
    wide = tmp_path / "wide.parquet"
    provenance = tmp_path / "provenance.parquet"
    _write_labels(labels)
    _write_accounts(wide, provenance)

    report = run_lead_time_analysis(
        labels,
        wide,
        provenance,
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
    )

    encoded = json.dumps(report)
    assert report["aggregate_only"] is True
    assert "00000001" not in encoded
    assert "00000002" not in encoded
