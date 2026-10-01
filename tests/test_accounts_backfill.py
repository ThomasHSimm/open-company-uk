import threading
import zipfile
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import ukcompany.accounts.backfill as backfill
from ukcompany.accounts.backfill import (
    FetchResult,
    FetchStatus,
    MonthStatus,
    archive_name,
    fetch_archive,
    run_backfill,
)
from ukcompany.accounts.extract import archive_recorded_complete, connect_store, export_manifest


def minimal_filing(company: str = "00123456") -> bytes:
    return f"""
    <html><xbrli:context id="c"><xbrli:period><xbrli:instant>2022-12-31</xbrli:instant>
    </xbrli:period></xbrli:context><xbrli:unit id="gbp">
    <xbrli:measure>iso4217:GBP</xbrli:measure></xbrli:unit>
    <ix:nonFraction name="uk:Equity" contextRef="c" unitRef="gbp">100</ix:nonFraction>
    <ix:nonNumeric name="uk:UKCompaniesHouseRegisteredNumber" contextRef="c">
    {company}</ix:nonNumeric></html>
    """.encode()


def make_archive(path: Path, *, filings: int = 1) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(filings):
            company = f"{index + 123456:08d}"
            archive.writestr(
                f"Prod1_2201_{company}_20221231.html",
                minimal_filing(company),
            )


class QuietFileHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass


@contextmanager
def serve_directory(directory: Path):
    handler = partial(QuietFileHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_full_range_downloads_extracts_deletes_and_reports_coverage(tmp_path: Path) -> None:
    source = tmp_path / "source"
    downloads = tmp_path / "downloads"
    source.mkdir()
    for month in (1, 2):
        make_archive(source / archive_name(2022, month))
    connection = connect_store(tmp_path / "store.sqlite")
    report = tmp_path / "coverage.md"

    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 2),
            downloads=downloads,
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
            report_output=report,
        )

    assert [outcome.status for outcome in summary.outcomes] == [
        MonthStatus.COMPLETED_DELETED,
        MonthStatus.COMPLETED_DELETED,
    ]
    assert not list(downloads.glob("*.zip"))
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 4
    assert sorted(path.name for path in (tmp_path / "monthly").glob("*.parquet")) == [
        "accounts-long-2022-01.parquet",
        "accounts-long-2022-02.parquet",
    ]
    assert archive_recorded_complete(connection, archive_name(2022, 1))
    assert archive_recorded_complete(connection, archive_name(2022, 2))
    text = report.read_text()
    assert "Present and manifest-complete: 2" in text
    assert "Effective covered span: `2022-01` through `2022-02`" in text
    connection.close()


def test_disposable_store_never_accumulates_observations_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    downloads = tmp_path / "downloads"
    source.mkdir()
    for month in (1, 2):
        make_archive(source / archive_name(2022, month))
    connection = connect_store(tmp_path / "store.sqlite")
    scratch_dir = tmp_path / "scratch"

    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 2),
            downloads=downloads,
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
            disposable_store=True,
            scratch_dir=scratch_dir,
        )

    assert [outcome.status for outcome in summary.outcomes] == [
        MonthStatus.COMPLETED_DELETED,
        MonthStatus.COMPLETED_DELETED,
    ]
    # The manifest connection never accumulates observations under disposable mode.
    assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    assert sorted(path.name for path in (tmp_path / "monthly").glob("*.parquet")) == [
        "accounts-long-2022-01.parquet",
        "accounts-long-2022-02.parquet",
    ]
    assert archive_recorded_complete(connection, archive_name(2022, 1))
    assert archive_recorded_complete(connection, archive_name(2022, 2))
    # Scratch stores are cleaned up after each month.
    assert not list(scratch_dir.glob("*.sqlite*"))

    def unexpected_fetch(*_args: object, **_kwargs: object):
        raise AssertionError("completed month was downloaded again")

    monkeypatch.setattr(backfill, "fetch_archive", unexpected_fetch)
    second = run_backfill(
        connection,
        (2022, 1),
        (2022, 2),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
        base_url="http://127.0.0.1:1",
        historic_base_url=None,
        retries=0,
        disposable_store=True,
        scratch_dir=scratch_dir,
    )

    assert all(outcome.status == MonthStatus.SKIPPED_COMPLETE for outcome in second.outcomes)
    connection.close()


def test_exported_manifest_alone_skips_already_complete_months(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate 2: a manifest exported out of a store (e.g. before the store is deleted) must,
    on its own, make `run_backfill` skip already-complete months rather than re-download."""
    source = tmp_path / "source"
    downloads = tmp_path / "downloads"
    source.mkdir()
    make_archive(source / archive_name(2022, 1))
    working_connection = connect_store(tmp_path / "working.sqlite")
    with serve_directory(source) as base_url:
        run_backfill(
            working_connection,
            (2022, 1),
            (2022, 1),
            downloads=downloads,
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
            disposable_store=True,
            scratch_dir=tmp_path / "scratch",
        )
    assert archive_recorded_complete(working_connection, archive_name(2022, 1))

    # Export to an independent manifest file and drop the original connection entirely,
    # simulating the working store being deleted.
    manifest_connection = connect_store(tmp_path / "exported-manifest.sqlite")
    copied = export_manifest(working_connection, manifest_connection)
    working_connection.close()
    assert copied == 1
    assert manifest_connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0

    def unexpected_fetch(*_args: object, **_kwargs: object):
        raise AssertionError("already-complete month was re-downloaded")

    monkeypatch.setattr(backfill, "fetch_archive", unexpected_fetch)
    summary = run_backfill(
        manifest_connection,
        (2022, 1),
        (2022, 1),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
        base_url="http://127.0.0.1:1",
        historic_base_url=None,
        retries=0,
        disposable_store=True,
        scratch_dir=tmp_path / "scratch",
    )

    assert summary.outcomes[0].status == MonthStatus.SKIPPED_COMPLETE
    manifest_connection.close()


def test_keep_zips_retains_downloaded_archive(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name)
    connection = connect_store(tmp_path / "store.sqlite")

    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path / "downloads",
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            keep_zips=True,
            retries=0,
        )

    assert summary.outcomes[0].status == MonthStatus.COMPLETED_KEPT
    assert (tmp_path / "downloads" / name).exists()
    connection.close()


def test_limited_run_is_partial_and_never_deletes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name, filings=2)
    connection = connect_store(tmp_path / "store.sqlite")

    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path / "downloads",
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            limit_per_zip=1,
            retries=0,
        )

    assert summary.outcomes[0].status == MonthStatus.PARTIAL_KEPT
    assert not summary.outcomes[0].manifest_complete
    assert (tmp_path / "downloads" / name).exists()
    connection.close()


def test_manually_staged_archive_is_extracted_but_never_deleted(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    name = archive_name(2022, 1)
    make_archive(downloads / name)
    connection = connect_store(tmp_path / "store.sqlite")

    summary = run_backfill(
        connection,
        (2022, 1),
        (2022, 1),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
        base_url="http://127.0.0.1:1",
        historic_base_url=None,
        retries=0,
    )

    assert summary.outcomes[0].status == MonthStatus.COMPLETED_KEPT
    assert (downloads / name).exists()
    assert archive_recorded_complete(connection, name)
    connection.close()


def test_short_download_is_failed_and_404_is_absent(tmp_path: Path) -> None:
    valid = tmp_path / "valid.zip"
    make_archive(valid)
    payload = valid.read_bytes()[:100]

    class ShortAndMissingHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if "January2022" in self.path:
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload) + 50))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(404)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), ShortAndMissingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = connect_store(tmp_path / "store.sqlite")
    downloads = tmp_path / "downloads"
    report = tmp_path / "coverage.md"
    try:
        host, port = server.server_address
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 2),
            downloads=downloads,
            output_dir=tmp_path / "monthly",
            base_url=f"http://{host}:{port}",
            historic_base_url=None,
            retries=0,
            report_output=report,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert [outcome.status for outcome in summary.outcomes] == [
        MonthStatus.FAILED,
        MonthStatus.ABSENT,
    ]
    assert not list(downloads.iterdir())
    assert "## Absent months" in report.read_text()
    assert "`2022-01`" in report.read_text()
    assert "`2022-02`" in report.read_text()
    connection.close()


def test_fetch_archive_falls_back_to_historic_url_on_404(tmp_path: Path) -> None:
    """Gate 1: a 404 on the root path must try `historic_base_url` before giving up."""
    root_dir = tmp_path / "root"
    historic_dir = tmp_path / "historic"
    root_dir.mkdir()
    historic_dir.mkdir()
    name = archive_name(2016, 1)
    make_archive(historic_dir / name)  # only present at the historic location

    with serve_directory(root_dir) as root_url, serve_directory(historic_dir) as historic_url:
        result = fetch_archive(
            1,
            2016,
            downloads=tmp_path / "downloads",
            base_url=root_url,
            historic_base_url=historic_url,
            retries=0,
        )

    assert result.status == FetchStatus.DOWNLOADED
    assert result.downloaded_this_run


def test_fetch_archive_reports_absent_only_after_both_paths_404(tmp_path: Path) -> None:
    """Gate 1: a month absent from BOTH candidate locations is ABSENT, not FAILED — and a
    wrong-path 404 must never masquerade as the month being genuinely missing."""
    root_dir = tmp_path / "root"
    historic_dir = tmp_path / "historic"
    root_dir.mkdir()
    historic_dir.mkdir()  # neither directory has the archive

    with serve_directory(root_dir) as root_url, serve_directory(historic_dir) as historic_url:
        result = fetch_archive(
            1,
            1999,
            downloads=tmp_path / "downloads",
            base_url=root_url,
            historic_base_url=historic_url,
            retries=0,
        )

    assert result.status == FetchStatus.ABSENT
    assert not (tmp_path / "downloads").exists() or not list((tmp_path / "downloads").iterdir())


def test_completed_month_skips_fetch_and_startup_removes_stale_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    name = archive_name(2022, 1)
    make_archive(downloads / name)
    connection = connect_store(tmp_path / "store.sqlite")
    run_backfill(
        connection,
        (2022, 1),
        (2022, 1),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
        base_url="http://127.0.0.1:1",
        historic_base_url=None,
        keep_zips=True,
        retries=0,
    )
    stale = downloads / f".{archive_name(2022, 2)}.part"
    stale.write_bytes(b"partial")

    def unexpected_fetch(*_args: object, **_kwargs: object):
        raise AssertionError("completed month was downloaded again")

    monkeypatch.setattr(backfill, "fetch_archive", unexpected_fetch)
    summary = run_backfill(
        connection,
        (2022, 1),
        (2022, 1),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
        base_url="http://127.0.0.1:1",
        historic_base_url=None,
    )

    assert summary.outcomes[0].status == MonthStatus.SKIPPED_COMPLETE
    assert not stale.exists()
    connection.close()


def test_failed_extraction_keeps_downloaded_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name)
    connection = connect_store(tmp_path / "store.sqlite")

    def fail_extract(*_args: object, **_kwargs: object) -> None:
        raise ValueError("synthetic extraction failure")

    monkeypatch.setattr(backfill, "process_archive", fail_extract)
    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path / "downloads",
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
        )

    assert summary.outcomes[0].status == MonthStatus.FAILED
    assert (tmp_path / "downloads" / name).exists()
    connection.close()


def test_accounting_nonclosure_aborts_and_keeps_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name)
    connection = connect_store(tmp_path / "store.sqlite")
    report = tmp_path / "coverage.md"

    def fail_accounting(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fact accounting does not close")

    monkeypatch.setattr(backfill, "process_archive", fail_accounting)
    with serve_directory(source) as base_url:
        with pytest.raises(AssertionError, match="does not close"):
            run_backfill(
                connection,
                (2022, 1),
                (2022, 1),
                downloads=tmp_path / "downloads",
                output_dir=tmp_path / "monthly",
                base_url=base_url,
                historic_base_url=None,
                retries=0,
                report_output=report,
            )

    assert (tmp_path / "downloads" / name).exists()
    assert "fact accounting does not close" in report.read_text()
    connection.close()


def test_abort_in_second_month_leaves_first_month_parquet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for month in (1, 2):
        make_archive(source / archive_name(2022, month))
    connection = connect_store(tmp_path / "store.sqlite")
    real_process = backfill.process_archive

    def stop_on_february(connection, archive, **kwargs):
        if archive.month == 2:
            raise AssertionError("stop after first month")
        return real_process(connection, archive, **kwargs)

    monkeypatch.setattr(backfill, "process_archive", stop_on_february)
    with serve_directory(source) as base_url:
        with pytest.raises(AssertionError, match="after first month"):
            run_backfill(
                connection,
                (2022, 1),
                (2022, 2),
                downloads=tmp_path / "downloads",
                output_dir=tmp_path / "monthly",
                base_url=base_url,
                historic_base_url=None,
                retries=0,
            )

    assert (tmp_path / "monthly" / "accounts-long-2022-01.parquet").exists()
    assert not (tmp_path / "downloads" / archive_name(2022, 1)).exists()
    assert (tmp_path / "downloads" / archive_name(2022, 2)).exists()
    connection.close()


def test_incomplete_manifest_never_allows_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name)
    connection = connect_store(tmp_path / "store.sqlite")

    def no_manifest(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(backfill, "process_archive", no_manifest)
    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path / "downloads",
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
        )

    assert summary.outcomes[0].status == MonthStatus.FAILED
    assert "complete manifest" in str(summary.outcomes[0].error)
    assert (tmp_path / "downloads" / name).exists()
    connection.close()


def test_failed_monthly_export_keeps_downloaded_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    name = archive_name(2022, 1)
    make_archive(source / name)
    connection = connect_store(tmp_path / "store.sqlite")

    def fail_export(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic monthly export failure")

    monkeypatch.setattr(backfill, "export_archive_parquet", fail_export)
    with serve_directory(source) as base_url:
        summary = run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path / "downloads",
            output_dir=tmp_path / "monthly",
            base_url=base_url,
            historic_base_url=None,
            retries=0,
        )

    assert summary.outcomes[0].status == MonthStatus.FAILED
    assert summary.outcomes[0].manifest_complete
    assert "monthly export failed" in str(summary.outcomes[0].error)
    assert (tmp_path / "downloads" / name).exists()
    connection.close()


def test_absent_and_failed_months_are_retried_on_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = connect_store(tmp_path / "store.sqlite")
    downloads = tmp_path / "downloads"
    calls: dict[tuple[int, int], int] = {}

    def changing_fetch(month: int, year: int, **_kwargs: object) -> FetchResult:
        key = year, month
        calls[key] = calls.get(key, 0) + 1
        path = downloads / archive_name(year, month)
        if calls[key] == 1:
            status = FetchStatus.ABSENT if month == 1 else FetchStatus.FAILED
            return FetchResult(status, path, error="first attempt")
        downloads.mkdir(parents=True, exist_ok=True)
        make_archive(path)
        return FetchResult(
            FetchStatus.DOWNLOADED,
            path,
            bytes_received=path.stat().st_size,
            downloaded_this_run=True,
        )

    monkeypatch.setattr(backfill, "fetch_archive", changing_fetch)
    first = run_backfill(
        connection,
        (2022, 1),
        (2022, 2),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
    )
    second = run_backfill(
        connection,
        (2022, 1),
        (2022, 2),
        downloads=downloads,
        output_dir=tmp_path / "monthly",
    )

    assert first.has_gaps
    assert not second.has_gaps
    assert calls == {(2022, 1): 2, (2022, 2): 2}
    assert all(outcome.status == MonthStatus.COMPLETED_DELETED for outcome in second.outcomes)
    connection.close()


def test_fetch_retries_transient_http_error_then_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    make_archive(source)
    payload = source.read_bytes()

    class FakeResponse:
        def __init__(self, status: int, body: bytes = b"") -> None:
            self.status_code = status
            self.body = body
            self.headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise backfill.requests.HTTPError(f"HTTP {self.status_code}")

        def iter_content(self, chunk_size: int):
            for offset in range(0, len(self.body), chunk_size):
                yield self.body[offset : offset + chunk_size]

    class FakeSession:
        def __init__(self) -> None:
            self.responses = [FakeResponse(503), FakeResponse(200, payload)]
            self.calls = 0

        def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
            response = self.responses[self.calls]
            self.calls += 1
            return response

    session = FakeSession()
    sleeps: list[float] = []
    result = fetch_archive(
        1,
        2022,
        downloads=tmp_path / "downloads",
        retries=1,
        backoff=0.25,
        chunk_size=17,
        sleep=sleeps.append,
        session=session,  # type: ignore[arg-type]
    )

    assert result.status == FetchStatus.DOWNLOADED
    assert result.downloaded_this_run
    assert result.bytes_received == len(payload)
    assert session.calls == 2
    assert sleeps == [0.25]


def test_fetch_archive_rejects_bad_arguments(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        fetch_archive(1, 2022, downloads=tmp_path, chunk_size=0)
    connection = connect_store(tmp_path / "store.sqlite")
    with pytest.raises(ValueError, match="positive"):
        run_backfill(
            connection,
            (2022, 1),
            (2022, 1),
            downloads=tmp_path,
            output_dir=tmp_path / "monthly",
            limit_per_zip=0,
        )
    connection.close()
