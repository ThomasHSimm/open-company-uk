import hashlib
import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from ukcompany.snapshot.download import (
    LANDING_PAGE_URL,
    SnapshotDownloadError,
    SnapshotPart,
    discover_parts,
    download_snapshot,
)
from ukcompany.snapshot.loader import COLUMNS, MISSING_POLARS, SnapshotLoader
from ukcompany.snapshot.manifest import create_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "snapshot"


def _zip_bytes(csv_path: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(csv_path.name, csv_path.read_bytes())
    return output.getvalue()


def _write_archives(tmp_path):
    paths = []
    parts = []
    for number in (1, 2):
        filename = f"BasicCompanyData-2026-08-01-part{number}_2.zip"
        path = tmp_path / filename
        path.write_bytes(_zip_bytes(FIXTURES / f"part{number}.csv"))
        paths.append(path)
        parts.append(
            SnapshotPart("2026-08", number, 2, filename, f"https://example.test/{filename}")
        )
    return paths, parts


def test_loader_is_lazy_full_width_and_preserves_company_numbers(tmp_path):
    paths, _ = _write_archives(tmp_path)
    loader = SnapshotLoader(paths)

    frame = loader.scan()
    assert frame.__class__.__name__ == "LazyFrame"
    assert loader.columns() == [
        "CompanyName",
        "CompanyNumber",
        "CompanyStatus",
        "CompanyCategory",
        "IncorporationDate",
        "SICCode.SicText_1",
        "RegAddress.PostCode",
        "Extra.Source.Column",
    ]
    assert str(frame.collect_schema()[COLUMNS["company_number"]]) == "String"
    assert frame.select("CompanyNumber").collect().to_series().to_list() == [
        "00000006",
        "SC000123",
        "01234567",
    ]
    assert loader.head(2).height == 2


def test_discovery_finds_complete_dynamic_part_set_and_fails_loudly():
    html = (FIXTURES / "landing.html").read_text(encoding="utf-8")
    parts = discover_parts(html, "https://example.test/en_output.html")

    assert [part.number for part in parts] == [1, 2]
    assert all(part.total == 2 and part.month == "2026-08" for part in parts)
    assert parts[1].url == "https://example.test/BasicCompanyData-2026-08-01-part2_2.zip"
    with pytest.raises(SnapshotDownloadError, match="contains no"):
        discover_parts("<html><a href='unrelated.zip'>x</a></html>")
    with pytest.raises(SnapshotDownloadError, match="incomplete"):
        discover_parts("<a href='BasicCompanyData-2026-08-01-part1_2.zip'>only one</a>")


class _Response:
    def __init__(self, *, text="", content=b"", status=200):
        self.text = text
        self.content = content
        self.status_code = status
        self.headers = {"Content-Length": str(len(content))} if content else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise SnapshotDownloadError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        yield self.content


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses.pop(0)


def test_download_discovers_and_caches_all_parts(tmp_path):
    html = (FIXTURES / "landing.html").read_text(encoding="utf-8")
    archives = [_zip_bytes(FIXTURES / f"part{number}.csv") for number in (1, 2)]
    session = _Session([_Response(text=html), *[_Response(content=data) for data in archives]])

    downloaded = download_snapshot(tmp_path, session=session)

    assert downloaded.month == "2026-08"
    assert [path.read_bytes() for path in downloaded.paths] == archives
    assert session.urls[0] == LANDING_PAGE_URL


def test_manifest_records_sources_hashes_and_lazy_row_count(tmp_path):
    paths, parts = _write_archives(tmp_path)
    output = tmp_path / "manifest.json"

    manifest = create_manifest("2026-08", paths, parts, output)

    assert manifest["snapshot_month"] == "2026-08"
    assert manifest["total_rows"] == 3
    assert manifest["landing_page_url"] == LANDING_PAGE_URL
    assert manifest["files"][0]["source_url"] == parts[0].url
    assert manifest["files"][0]["sha256"] == hashlib.sha256(paths[0].read_bytes()).hexdigest()
    assert json.loads(output.read_text(encoding="utf-8")) == manifest


def test_missing_polars_has_actionable_install_message(monkeypatch, tmp_path):
    csv_path = tmp_path / "part.csv"
    csv_path.write_text("CompanyNumber\n00000006\n", encoding="utf-8")
    real_import = importlib.import_module

    def missing(name, package=None):
        if name == "polars":
            raise ImportError("simulated")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", missing)
    with pytest.raises(ImportError, match=r"open-company-uk\[snapshot\]") as error:
        SnapshotLoader(csv_path).scan()
    assert str(error.value) == MISSING_POLARS
