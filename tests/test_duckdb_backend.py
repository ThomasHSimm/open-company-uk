from __future__ import annotations

import builtins
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb
import pytest

from ukcompany.accounts import cli as accounts_cli
from ukcompany.duckdb_backend import connect_duckdb, validate_duckdb_backend
from ukcompany.psc import cli as psc_cli
from ukcompany.psc.loader import load_psc


class _RangeHandler(BaseHTTPRequestHandler):
    payload = b""
    request_ranges: list[str | None] = []

    def _headers(self, status: int, length: int, content_range: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if content_range is not None:
            self.send_header("Content-Range", content_range)
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        self._headers(200, len(self.payload))

    def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler API
        requested = self.headers.get("Range")
        type(self).request_ranges.append(requested)
        if requested and requested.startswith("bytes="):
            start_text, end_text = requested.removeprefix("bytes=").split("-", 1)
            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else len(self.payload) - 1
            else:
                suffix_length = int(end_text)
                start = max(0, len(self.payload) - suffix_length)
                end = len(self.payload) - 1
            end = min(end, len(self.payload) - 1)
            body = self.payload[start : end + 1]
            self._headers(206, len(body), f"bytes {start}-{end}/{len(self.payload)}")
        else:
            body = self.payload
            self._headers(200, len(body))
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def range_http_server(tmp_path: Path):
    pytest.importorskip("fsspec")
    pytest.importorskip("aiohttp")
    parquet_path = tmp_path / "fixture.parquet"
    connection = duckdb.connect()
    try:
        connection.execute("CREATE TABLE fixture(id INTEGER, label VARCHAR)")
        connection.execute("INSERT INTO fixture VALUES (1, 'one'), (2, 'two')")
        connection.execute(f"COPY fixture TO '{parquet_path}' (FORMAT PARQUET)")
    finally:
        connection.close()

    _RangeHandler.payload = parquet_path.read_bytes()
    _RangeHandler.request_ranges = []
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    except PermissionError:
        pytest.skip("sandbox does not allow binding a loopback HTTP fixture")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/fixture.parquet", parquet_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_invalid_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="choose one of: fsspec, native"):
        validate_duckdb_backend("magic")


def test_missing_fsspec_has_actionable_error(tmp_path: Path, monkeypatch) -> None:
    real_import = builtins.__import__

    def without_fsspec(name, *args, **kwargs):
        if name == "fsspec":
            raise ImportError("simulated missing optional package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_fsspec)
    native = connect_duckdb(
        memory_limit_gb=1,
        spill_dir=tmp_path / "native-spill",
        backend="native",
    )
    try:
        assert native.execute("SELECT 1").fetchone() == (1,)
    finally:
        native.close()
    with pytest.raises(RuntimeError, match=r"open-company-uk\[remote\]"):
        connect_duckdb(
            memory_limit_gb=1,
            spill_dir=tmp_path / "spill",
            backend="fsspec",
        )


def test_missing_s3fs_has_actionable_error(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("fsspec")
    real_import = builtins.__import__

    def without_s3fs(name, *args, **kwargs):
        if name == "s3fs":
            raise ImportError("simulated missing optional package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_s3fs)
    with pytest.raises(RuntimeError, match=r"s3fs.*open-company-uk\[remote\]"):
        connect_duckdb(
            memory_limit_gb=1,
            spill_dir=tmp_path / "spill",
            backend="fsspec",
            input_paths=("s3://example-bucket/fixture.parquet",),
        )


def test_unsupported_fsspec_scheme_is_rejected(tmp_path: Path) -> None:
    pytest.importorskip("fsspec")
    with pytest.raises(ValueError, match=r"unsupported scheme\(s\): \['ftp'\]"):
        connect_duckdb(
            memory_limit_gb=1,
            spill_dir=tmp_path / "spill",
            backend="fsspec",
            input_paths=("ftp://example.test/fixture.parquet",),
        )


def test_registered_http_filesystem_reads_ranges_without_httpfs(
    tmp_path: Path, range_http_server
) -> None:
    url, local_path = range_http_server
    local = connect_duckdb(
        memory_limit_gb=1,
        spill_dir=tmp_path / "native-spill",
    )
    remote = connect_duckdb(
        memory_limit_gb=1,
        spill_dir=tmp_path / "fsspec-spill",
        backend="fsspec",
        input_paths=(url,),
    )
    try:
        expected = local.execute(
            f"SELECT * FROM read_parquet('{local_path}') ORDER BY id"
        ).fetchall()
        actual = remote.execute(f"SELECT * FROM read_parquet('{url}') ORDER BY id").fetchall()
        settings = remote.execute(
            "SELECT current_setting('autoinstall_known_extensions'), "
            "current_setting('autoload_known_extensions')"
        ).fetchone()
        httpfs_loaded = remote.execute(
            "SELECT loaded FROM duckdb_extensions() WHERE extension_name = 'httpfs'"
        ).fetchone()[0]
    finally:
        local.close()
        remote.close()

    assert actual == expected == [(1, "one"), (2, "two")]
    assert settings == (False, False)
    assert httpfs_loaded is False
    assert any(value is not None for value in _RangeHandler.request_ranges)


def test_psc_public_entrypoint_accepts_fsspec_backend_locally(tmp_path: Path) -> None:
    pytest.importorskip("fsspec")
    line = {
        "company_number": "00000001",
        "data": {
            "kind": "individual-person-with-significant-control",
            "name_elements": {"forename": "Alex", "surname": "Example"},
            "links": {
                "self": "/company/00000001/persons-with-significant-control/individual/p1"
            },
        },
    }
    source = tmp_path / "psc-snapshot-2026-09-18_1of1.txt"
    source.write_text(json.dumps(line) + "\n", encoding="utf-8")

    report = load_psc(
        source,
        tmp_path / "out",
        "2026-09-18",
        data_governance=False,
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
        duckdb_backend="fsspec",
    )

    assert report["n_lines"] == 1
    assert report["duckdb_settings"]["backend"] == "fsspec"


def test_local_paths_still_work_in_native_mode(tmp_path: Path) -> None:
    connection = connect_duckdb(
        memory_limit_gb=1,
        spill_dir=tmp_path / "spill",
        backend="native",
    )
    try:
        assert connection.execute("SELECT 42").fetchone() == (42,)
    finally:
        connection.close()


def test_accounts_cli_passes_backend_to_public_entrypoint(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_build(parts, output_dir, years, **kwargs):
        captured.update(parts=parts, output_dir=output_dir, years=list(years), **kwargs)
        return {2026: 0}

    monkeypatch.setattr(
        "ukcompany.accounts.public_long.build_public_long_duckdb", fake_build
    )
    args = accounts_cli.build_parser().parse_args(
        [
            "--settings",
            str(tmp_path / "missing.yaml"),
            "build-public-long",
            "--long",
            "https://example.test/accounts.parquet",
            "--output-dir",
            str(tmp_path / "out"),
            "--from-year",
            "2026",
            "--to-year",
            "2026",
            "--duckdb-backend",
            "fsspec",
        ]
    )

    assert accounts_cli.cmd_build_public_long(args) == 0
    assert captured["parts"] == "https://example.test/accounts.parquet"
    assert captured["duckdb_backend"] == "fsspec"
    assert captured["fsspec_options"] == {}


def test_psc_cli_passes_backend_to_loader(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_load(parts, output_dir, snapshot_date, **kwargs):
        captured.update(
            parts=parts,
            output_dir=output_dir,
            snapshot_date=snapshot_date,
            **kwargs,
        )
        return {
            "snapshot_date": snapshot_date,
            "data_governance": False,
            "n_lines": 1,
            "n_bad_lines": 0,
            "categories_sum_to_lines": True,
            "category_counts": {"individual": 1},
            "outputs": {},
        }

    monkeypatch.setattr(psc_cli, "load_psc", fake_load)
    args = psc_cli.build_parser().parse_args(
        [
            "--settings",
            str(tmp_path / "missing.yaml"),
            "load",
            "--parts",
            "https://example.test/psc.txt",
            "--snapshot-date",
            "2026-09-18",
            "--output-dir",
            str(tmp_path / "out"),
            "--no-data-governance",
            "--duckdb-backend",
            "fsspec",
        ]
    )

    assert psc_cli.cmd_load(args) == 0
    assert captured["parts"] == "https://example.test/psc.txt"
    assert captured["duckdb_backend"] == "fsspec"
    assert captured["fsspec_options"] == {}
