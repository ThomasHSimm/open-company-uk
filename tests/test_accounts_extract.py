import json
import zipfile
from pathlib import Path

import polars as pl

from ukcompany.accounts.core import TARGET_CONCEPTS
from ukcompany.accounts.extract import (
    OBSERVATION_SCHEMA_VERSION,
    archive_recorded_complete,
    connect_store,
    discover_archives,
    export_archive_parquet,
    export_completed_archives,
    manifest_integrity,
    manifest_rows,
    parse_archive,
    process_archive,
)


def minimal_filing(value: str = "100", company_tag: str = "00123456") -> bytes:
    return f"""
    <html><xbrli:context id="c"><xbrli:period><xbrli:instant>2023-12-31</xbrli:instant>
    </xbrli:period></xbrli:context><xbrli:unit id="gbp">
    <xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="uk:Equity" contextRef="c" unitRef="gbp">{value}</ix:nonFraction>
    <ix:nonNumeric name="uk:UKCompaniesHouseRegisteredNumber" contextRef="c">
    {company_tag}</ix:nonNumeric></html>
    """.encode()


def make_archive(path: Path, filings: int = 2) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(filings):
            archive.writestr(
                f"Prod1_2301_00123456_20231231_{index}.html".replace(
                    f"_{index}.html", ".html" if index == 0 else ".xml"
                ),
                minimal_filing(),
            )


def test_archive_discovery_accepts_any_year_and_surrounding_whitespace(tmp_path: Path) -> None:
    paths = [
        tmp_path / " Accounts_Monthly_Data-January2018.zip ",
        tmp_path / "Accounts_Monthly_Data-February2025.zip",
    ]
    for path in paths:
        path.touch()

    archives = discover_archives(tmp_path)

    assert [(item.year, item.month) for item in archives] == [(2018, 1), (2025, 2)]
    assert parse_archive(paths[0]).name.startswith(" ")


def test_resumable_archive_manifest_xml_skip_and_company_mismatch(tmp_path: Path) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-January2023.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "Prod1_2301_00123456_20231231.html", minimal_filing(company_tag="00999999")
        )
        archive.writestr("Prod1_2301_00123456_20231231.xml", b"<xbrl/>")
        archive.writestr("README.txt", b"metadata")
    connection = connect_store(tmp_path / "store.sqlite")
    spec = parse_archive(archive_path)

    first = process_archive(connection, spec, progress_every=0)
    second = process_archive(connection, spec, progress_every=0)

    assert first is not None and first.filings_processed == 1
    assert first.xml_skipped == 1
    assert first.filename_exceptions == 1
    assert first.company_mismatches == 1
    assert second is None
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
    row = connection.execute("SELECT company, currency FROM observations").fetchone()
    assert row == ("00123456", "GBP")
    assert manifest_integrity(connection).closes()
    manifest = manifest_rows(connection)[0]
    assert manifest["complete"] == 1
    assert json.loads(str(manifest["integrity_json"]))["facts_seen"] == 2
    connection.close()


def test_monthly_export_filters_one_archive_batches_and_standalone_rewrites(
    tmp_path: Path,
) -> None:
    connection = connect_store(tmp_path / "store.sqlite")
    specs = []
    for month in ("January", "February"):
        archive_path = tmp_path / f"Accounts_Monthly_Data-{month}2023.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(
                "Prod1_2301_00123456_20231231.html",
                minimal_filing(value="100" if month == "January" else "200"),
            )
        spec = parse_archive(archive_path)
        process_archive(connection, spec, progress_every=0)
        specs.append(spec)

    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    stale_parts = tmp_path / "monthly" / ".accounts-long-2023-01-parts"
    stale_parts.mkdir(parents=True)
    (stale_parts / "part-00000.parquet").write_bytes(b"interrupted")
    january = export_archive_parquet(
        connection,
        specs[0].name,
        tmp_path / "monthly",
        batch_size=1,
    )
    frame = pl.read_parquet(january)

    assert january.name == "accounts-long-2023-01.parquet"
    assert not stale_parts.exists()
    assert frame["source_archive"].unique().to_list() == [specs[0].name]
    assert frame.height == 2
    equity = frame.filter(pl.col("concept") == "Equity").row(0, named=True)
    assert equity["unit"] == "GBP"
    assert equity["context_kind"] == "instant"
    assert any("WHERE source_archive =" in statement for statement in statements)
    january.unlink()
    outputs = export_completed_archives(connection, tmp_path / "monthly", start=(2023, 1))
    assert [path.name for path in outputs] == [
        "accounts-long-2023-01.parquet",
        "accounts-long-2023-02.parquet",
    ]
    assert january.exists()
    connection.close()


def test_partial_archive_is_reprocessed_idempotently(tmp_path: Path) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-March2020.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2003_00123456_20201231.html", minimal_filing("1"))
        archive.writestr("Prod2_2003_00654321_20201231.html", minimal_filing("2", "00654321"))
    connection = connect_store(tmp_path / "store.sqlite")
    spec = parse_archive(archive_path)

    process_archive(connection, spec, limit=1, progress_every=0)
    partial = manifest_rows(connection)[0]
    process_archive(connection, spec, progress_every=0)

    assert partial["complete"] == 0
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 4
    assert manifest_rows(connection)[0]["complete"] == 1
    assert manifest_integrity(connection).filings_processed == 2
    connection.close()


def test_expanding_scope_replaces_narrow_archive_rows_without_duplicates(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-April2020.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2004_00123456_20201231.html", minimal_filing())
    connection = connect_store(tmp_path / "store.sqlite")
    spec = parse_archive(archive_path)

    process_archive(connection, spec, scope=TARGET_CONCEPTS, progress_every=0)
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert not archive_recorded_complete(connection, spec.name)
    assert export_completed_archives(connection, tmp_path / "narrow-export") == []

    process_archive(connection, spec, scope="all", progress_every=0)

    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
    assert archive_recorded_complete(connection, spec.name)
    assert manifest_rows(connection)[0]["scope_json"] == '"all"'
    connection.close()


def test_pre_stage1_manifest_is_never_treated_as_complete(tmp_path: Path) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-June2020.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2006_00123456_20201231.html", minimal_filing())
    connection = connect_store(tmp_path / "store.sqlite")
    spec = parse_archive(archive_path)
    process_archive(connection, spec, scope=TARGET_CONCEPTS, progress_every=0)
    connection.execute(
        "UPDATE processed_archives SET scope_json = NULL, kinds = NULL WHERE archive_name = ?",
        (spec.name,),
    )
    connection.execute(
        "UPDATE observations SET fact_sequence = -1 WHERE source_archive = ?",
        (spec.name,),
    )
    connection.commit()

    assert not archive_recorded_complete(connection, spec.name, scope=TARGET_CONCEPTS)
    process_archive(connection, spec, scope=TARGET_CONCEPTS, progress_every=0)

    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    assert connection.execute("SELECT fact_sequence FROM observations").fetchone()[0] == 0
    connection.close()


def test_prior_observation_schema_is_reextracted_not_exported(tmp_path: Path) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-July2020.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2007_00123456_20201231.html", minimal_filing())
    connection = connect_store(tmp_path / "store.sqlite")
    spec = parse_archive(archive_path)
    process_archive(connection, spec, progress_every=0)
    connection.execute(
        "UPDATE processed_archives SET fact_schema_version = 1 WHERE archive_name = ?",
        (spec.name,),
    )
    connection.commit()

    assert not archive_recorded_complete(connection, spec.name)
    assert export_completed_archives(connection, tmp_path / "stale-export") == []
    result = process_archive(connection, spec, progress_every=0)

    assert result is not None
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
    assert (
        manifest_rows(connection)[0]["fact_schema_version"]
        == OBSERVATION_SCHEMA_VERSION
    )
    connection.close()


def test_conflicts_are_all_persisted_with_status_and_stable_sequence(tmp_path: Path) -> None:
    archive_path = tmp_path / "Accounts_Monthly_Data-May2020.zip"
    filing = minimal_filing().replace(
        b"</html>",
        b'<ix:nonFraction name="uk:Equity" contextRef="c" unitRef="gbp">'
        b"120</ix:nonFraction></html>",
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Prod1_2005_00123456_20201231.html", filing)
    connection = connect_store(tmp_path / "store.sqlite")

    process_archive(connection, parse_archive(archive_path), progress_every=0)

    rows = connection.execute(
        "SELECT numeric_value, status, fact_sequence FROM observations "
        "WHERE concept = 'Equity' ORDER BY fact_sequence"
    ).fetchall()
    assert rows == [
        ("100", "conflict_nondimensional", 0),
        ("120", "conflict_nondimensional", 2),
    ]
    assert manifest_integrity(connection).ambiguous_nondimensional == 2
    assert manifest_integrity(connection).closes()
    connection.close()
