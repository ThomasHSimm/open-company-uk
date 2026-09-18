import csv
import json
import zipfile
from pathlib import Path

from ukcompany.accounts.extract import connect_store, parse_archive, process_archive
from ukcompany.accounts.inventory import (
    INVENTORY_COLUMNS,
    build_concept_inventory,
    write_concept_inventory,
)


def inventory_filing() -> bytes:
    return b"""
    <html>
      <xbrli:context id="instant"><xbrli:period>
        <xbrli:instant>2023-12-31</xbrli:instant>
      </xbrli:period></xbrli:context>
      <xbrli:context id="duration"><xbrli:period>
        <xbrli:startDate>2023-01-01</xbrli:startDate>
        <xbrli:endDate>2023-12-31</xbrli:endDate>
      </xbrli:period></xbrli:context>
      <xbrli:unit id="gbp"><xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
      <xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
      <xbrli:unit id="count"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
      <ix:nonNumeric name="uk:ReportingPeriodEndDate" contextRef="instant">
        2023-12-31
      </ix:nonNumeric>
      <ix:nonNumeric name="uk:AccountingPolicyDescription" contextRef="duration">
        Revenue is recognised on delivery.
      </ix:nonNumeric>
      <ix:nonFraction name="uk:AverageNumberEmployeesDuringPeriod"
        contextRef="duration" unitRef="count">5</ix:nonFraction>
      <ix:nonFraction name="uk:GrossProfitMargin"
        contextRef="duration" unitRef="count">0.25</ix:nonFraction>
      <ix:nonFraction name="uk:Revenue"
        contextRef="duration" unitRef="eur">10</ix:nonFraction>
      <ix:nonFraction name="one:Collision" contextRef="instant" unitRef="gbp">
        1
      </ix:nonFraction>
      <ix:nonNumeric name="two:Collision" contextRef="instant">one</ix:nonNumeric>
      <ix:nonFraction name="uk:PeriodMetric" contextRef="instant" unitRef="gbp">
        2
      </ix:nonFraction>
      <ix:nonFraction name="uk:PeriodMetric" contextRef="duration" unitRef="gbp">
        3
      </ix:nonFraction>
      <ix:nonFraction name="one:UnitCollision" contextRef="instant" unitRef="gbp">
        4
      </ix:nonFraction>
      <ix:nonFraction name="two:UnitCollision" contextRef="instant" unitRef="count">
        5
      </ix:nonFraction>
      <ix:nonFraction name="uk:MissingUnit" contextRef="instant">6</ix:nonFraction>
      <ix:nonFraction name="uk:NarrativeDescription" contextRef="instant" unitRef="gbp">
        7
      </ix:nonFraction>
      <ix:nonNumeric name="uk:AssetAmount" contextRef="instant">unknown</ix:nonNumeric>
    </html>
    """


def extracted_inventory(tmp_path: Path):
    archive_path = tmp_path / "Accounts_Monthly_Data-January2023.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2301_00123456_20231231.html", inventory_filing())
    connection = connect_store(tmp_path / "store.sqlite")
    process_archive(connection, parse_archive(archive_path), progress_every=0)
    return connection


def test_units_text_and_context_kind_are_stored_without_coercion(tmp_path: Path) -> None:
    connection = extracted_inventory(tmp_path)

    non_numeric = {
        concept: (raw_value, numeric_value)
        for concept, raw_value, numeric_value in connection.execute(
            "SELECT concept, raw_value, numeric_value FROM observations "
            "WHERE concept IN ('ReportingPeriodEndDate', 'AccountingPolicyDescription')"
        )
    }
    units = dict(
        connection.execute(
            "SELECT concept, unit FROM observations WHERE concept IN "
            "('AverageNumberEmployeesDuringPeriod', 'GrossProfitMargin', 'Revenue')"
        )
    )
    currencies = dict(
        connection.execute(
            "SELECT concept, currency FROM observations WHERE concept IN "
            "('AverageNumberEmployeesDuringPeriod', 'GrossProfitMargin', 'Revenue')"
        )
    )
    contexts = {
        row[0]: set(row[1:])
        for row in connection.execute(
            "SELECT concept, MIN(context_kind), MAX(context_kind) FROM observations "
            "WHERE concept IN ('ReportingPeriodEndDate', 'AccountingPolicyDescription') "
            "GROUP BY concept"
        )
    }

    assert non_numeric == {
        "AccountingPolicyDescription": ("Revenue is recognised on delivery.", None),
        "ReportingPeriodEndDate": ("2023-12-31", None),
    }
    assert units == {
        "AverageNumberEmployeesDuringPeriod": "pure",
        "GrossProfitMargin": "pure",
        "Revenue": "EUR",
    }
    assert currencies == {
        "AverageNumberEmployeesDuringPeriod": None,
        "GrossProfitMargin": None,
        "Revenue": "EUR",
    }
    assert contexts == {
        "AccountingPolicyDescription": {"duration"},
        "ReportingPeriodEndDate": {"instant"},
    }
    connection.close()


def test_inventory_counts_csv_and_anomaly_flags(tmp_path: Path) -> None:
    connection = extracted_inventory(tmp_path)
    inventory = build_concept_inventory(connection)
    rows = {row.concept: row for row in inventory.rows}

    assert len(rows) == 11
    assert rows["Collision"].observations == 2
    assert rows["Collision"].companies == 1
    assert rows["Collision"].kind == "mixed"
    assert rows["Collision"].pct_numeric_null == 50.0
    assert rows["UnitCollision"].units == ("GBP", "pure")
    assert rows["PeriodMetric"].context_kind == "mixed"
    assert inventory.audit.non_numeric_coercion_rows == 0
    assert inventory.audit.numeric_unit_gaps == (("MissingUnit", 1),)
    assert inventory.audit.mixed_kinds == ("Collision",)
    assert inventory.audit.incompatible_units == (("UnitCollision", ("GBP", "pure")),)
    assert inventory.audit.mixed_contexts == ("PeriodMetric",)
    assert inventory.audit.name_kind_mismatches == (
        ("AssetAmount", "numeric-like name has non-numeric facts"),
        ("NarrativeDescription", "text-like name has numeric facts"),
    )

    csv_path = tmp_path / "inventory.csv"
    report_path = tmp_path / "inventory.md"
    write_concept_inventory(connection, csv_path, report_path)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert tuple(csv_rows[0]) == INVENTORY_COLUMNS
    assert len(csv_rows) == 11
    assert [int(row["observations"]) for row in csv_rows] == sorted(
        (int(row["observations"]) for row in csv_rows), reverse=True
    )
    collision = next(row for row in csv_rows if row["concept"] == "Collision")
    assert collision["observations"] == "2"
    assert collision["kind"] == "mixed"
    assert json.loads(collision["example_values"]) == ["1", "one"]
    report = report_path.read_text(encoding="utf-8")
    assert "Non-numeric facts with non-null `numeric_value`: **0**" in report
    assert "`MissingUnit`" in report
    assert "Only the nine core concepts are validated" in report
    connection.close()
