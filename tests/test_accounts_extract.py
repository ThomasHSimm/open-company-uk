import json
import zipfile
from pathlib import Path

from ukcompany.accounts.extract import (
    connect_store,
    discover_archives,
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
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
    row = connection.execute("SELECT company, currency FROM observations").fetchone()
    assert row == ("00123456", "GBP")
    assert manifest_integrity(connection).closes()
    manifest = manifest_rows(connection)[0]
    assert manifest["complete"] == 1
    assert json.loads(str(manifest["integrity_json"]))["target_facts_seen"] == 1
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
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
    assert manifest_rows(connection)[0]["complete"] == 1
    assert manifest_integrity(connection).filings_processed == 2
    connection.close()
