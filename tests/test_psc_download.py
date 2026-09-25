import hashlib
import json

import pytest

from ukcompany.psc.download import (
    PSC_LANDING_PAGE_URL,
    PscDownloadError,
    PscPart,
    discover_parts,
    download_snapshot,
)
from ukcompany.psc.manifest import create_manifest


def _landing_html(date: str, total: int = 2) -> str:
    links = "".join(
        f'<a href="/{date}/psc-snapshot-{date}_{k}of{total}.zip">part {k}</a>\n'
        for k in range(1, total + 1)
    )
    return f"<html><body>{links}</body></html>"


def test_discover_parts_finds_complete_set_and_fails_loudly():
    html = _landing_html("2026-09-18")
    parts = discover_parts(html, "https://example.test/en_pscdata.html")

    assert [part.number for part in parts] == [1, 2]
    assert all(part.total == 2 and part.date == "2026-09-18" for part in parts)
    assert parts[1].url == "https://example.test/2026-09-18/psc-snapshot-2026-09-18_2of2.zip"

    with pytest.raises(PscDownloadError, match="contains no"):
        discover_parts("<html><a href='unrelated.zip'>x</a></html>")
    with pytest.raises(PscDownloadError, match="incomplete"):
        discover_parts("<a href='psc-snapshot-2026-09-18_1of2.zip'>only one</a>")


def test_discover_parts_rejects_inconsistent_totals():
    html = (
        "<a href='psc-snapshot-2026-09-18_1of2.zip'>a</a>"
        "<a href='psc-snapshot-2026-09-18_2of3.zip'>b</a>"
    )
    with pytest.raises(PscDownloadError, match="inconsistent"):
        discover_parts(html)


def test_discover_parts_picks_requested_date_or_latest():
    html = _landing_html("2026-09-17", total=1) + _landing_html("2026-09-18", total=1)
    latest = discover_parts(html)
    assert latest[0].date == "2026-09-18"
    specific = discover_parts(html, date="2026-09-17")
    assert specific[0].date == "2026-09-17"
    with pytest.raises(PscDownloadError, match="not found"):
        discover_parts(html, date="2026-01-01")


class _Response:
    def __init__(self, *, text="", content=b"", status=200):
        self.text = text
        self.content = content
        self.status_code = status
        self.headers = {"Content-Length": str(len(content))} if content else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        yield self.content


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses.pop(0)


def test_download_snapshot_discovers_and_keeps_all_zips(tmp_path):
    html = _landing_html("2026-09-18")
    contents = [b"zip-bytes-part-1", b"zip-bytes-part-2"]
    session = _Session([_Response(text=html), *[_Response(content=c) for c in contents]])

    downloaded = download_snapshot(tmp_path, session=session)

    assert downloaded.date == "2026-09-18"
    assert [path.read_bytes() for path in downloaded.paths] == contents
    assert session.urls[0] == PSC_LANDING_PAGE_URL
    # Zips are the archive: still on disk after the call, nothing extracted or deleted.
    for path in downloaded.paths:
        assert path.exists()
        assert path.suffix == ".zip"


def test_manifest_records_hashes_size_and_date(tmp_path):
    path1 = tmp_path / "psc-snapshot-2026-09-18_1of2.zip"
    path2 = tmp_path / "psc-snapshot-2026-09-18_2of2.zip"
    path1.write_bytes(b"aaa")
    path2.write_bytes(b"bbbbb")
    parts = [
        PscPart("2026-09-18", 1, 2, path1.name, "https://example.test/1.zip"),
        PscPart("2026-09-18", 2, 2, path2.name, "https://example.test/2.zip"),
    ]
    output = tmp_path / "manifest.json"

    manifest = create_manifest("2026-09-18", [path1, path2], parts, output)

    assert manifest["snapshot_date"] == "2026-09-18"
    assert manifest["total_zipped_bytes"] == 3 + 5
    assert manifest["files"][0]["size"] == 3
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"aaa").hexdigest()
    assert manifest["files"][1]["sha256"] == hashlib.sha256(b"bbbbb").hexdigest()
    assert json.loads(output.read_text(encoding="utf-8")) == manifest
