import json
from pathlib import Path

from ukcompany.cache import RawCache
from ukcompany.cli import main
from ukcompany.derive import derive_all
from ukcompany.score import score_all, write_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_cache_roundtrip_and_freshness(tmp_path):
    cache = RawCache(tmp_path)
    data = json.loads((FIXTURES / "profile_active_clean.json").read_text())
    cache.write("01234567", "profile", 200, "https://x/company/01234567", data)
    got = cache.read("01234567", "profile")
    assert got is not None and got.data["company_name"] == "SYNTHETIC TRADING LIMITED"
    assert cache.is_fresh("01234567", "profile", max_age_days=1)
    assert not cache.is_fresh("01234567", "profile", max_age_days=0)


def test_cached_404_roundtrip(tmp_path):
    cache = RawCache(tmp_path)
    cache.write("99999999", "profile", 404, "https://x/company/99999999", None)
    got = cache.read("99999999", "profile")
    assert got is not None and got.not_found and got.data is None


def test_write_csv_heterogeneous_rows(tmp_path):
    rows = [{"a": 1}, {"a": 2, "b": 3}]
    out = tmp_path / "x.csv"
    write_csv(rows, out)
    text = out.read_text()
    assert "a,b" in text.splitlines()[0]


def _seed_cache(cache_dir: Path):
    cache = RawCache(cache_dir)
    for fixture, endpoint, number in [
        ("profile_active_clean.json", "profile", "01234567"),
        ("profile_liquidation.json", "profile", "07654321"),
        ("insolvency_07654321.json", "insolvency", "07654321"),
        ("profile_dissolved.json", "profile", "02222222"),
    ]:
        data = json.loads((FIXTURES / fixture).read_text())
        cache.write(number, endpoint, 200, f"fixture://{fixture}", data)
    cache.write("00009999", "profile", 404, "fixture://notfound", None)
    return cache


def test_pipeline_from_cache(tmp_path):
    cache = _seed_cache(tmp_path / "raw")
    numbers = ["01234567", "07654321", "02222222", "00009999"]
    profiles = [c for c in (cache.read(n, "profile") for n in numbers) if c is not None]
    insolvency = {"07654321": cache.read("07654321", "insolvency")}
    records = derive_all(profiles, insolvency)
    result = score_all(records)
    assert len(result["not_found"]) == 1
    assert len(result["excluded"]) == 1
    assert {f["company_number"] for f in result["flags"]} == {"07654321"}


def test_cli_no_fetch_end_to_end(tmp_path, monkeypatch, capsys):
    """Full CLI run against a seeded cache: no network, real files out."""
    monkeypatch.chdir(tmp_path)
    _seed_cache(tmp_path / "data" / "raw")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.yaml").write_text(
        "paths:\n  cache_dir: data/raw\n  output_dir: data/processed\n"
    )
    (tmp_path / "in.csv").write_text(
        "company_number\n01234567\n7654321\n02222222\n00009999\n"  # note Excel-damaged row
    )
    rc = main(["run", "--input", "in.csv", "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "FIXED" in out  # 7654321 -> 07654321 reported
    flags = (tmp_path / "data" / "processed" / "flags.csv").read_text()
    assert "STATUS_INSOLVENT" in flags and "07654321" in flags
    assert (tmp_path / "data" / "processed" / "excluded.csv").read_text().count("02222222") == 1


def test_cli_hard_fails_on_invalid_input(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "in.csv").write_text("company_number\nnot-a-number\n01234567\n")
    rc = main(["run", "--input", "in.csv", "--no-fetch"])
    assert rc == 2  # refuses to silently drop rows


def test_cache_archive_on_change(tmp_path):
    cache = RawCache(tmp_path)
    cache.write("01234567", "profile", 200, "https://x", {"company_status": "active"})
    # Same content: no history entry created.
    cache.write("01234567", "profile", 200, "https://x", {"company_status": "active"})
    assert cache.read_history("01234567", "profile") == []
    # Changed content: previous response archived, both states observable.
    cache.write("01234567", "profile", 200, "https://x", {"company_status": "liquidation"})
    history = cache.read_history("01234567", "profile")
    assert len(history) == 1
    assert history[0].data["company_status"] == "active"
    assert cache.read("01234567", "profile").data["company_status"] == "liquidation"


def test_cache_stores_etag_and_hash(tmp_path):
    cache = RawCache(tmp_path)
    cache.write("01234567", "profile", 200, "https://x", {"a": 1}, etag="abc123")
    got = cache.read("01234567", "profile")
    assert got.etag == "abc123" and got.content_hash
