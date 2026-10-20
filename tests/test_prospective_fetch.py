"""Tests for the profile + /insolvency-only prospective fetch path.

No network: a fake client serves canned responses and records every path it was
asked for, so the tests assert that officers/PSC endpoints are NEVER called and
that /insolvency is called only when the profile links to it.
"""

from __future__ import annotations

from ukcompany.cache import RawCache
from ukcompany.cli import main
from ukcompany.client import APIResponse
from ukcompany.fetch import fetch_profile_insolvency
from ukcompany.validate import is_registered_society_number


class RecordingClient:
    """Minimal stand-in for CHClient.get, recording requested paths."""

    def __init__(self, responses: dict[str, APIResponse]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, path: str, params: dict | None = None) -> APIResponse:
        self.calls.append(path)
        if path in self.responses:
            return self.responses[path]
        return APIResponse(404, None, f"https://x{path}")


def _profile(number: str, *, insolvency: bool) -> APIResponse:
    links = {"self": f"/company/{number}"}
    if insolvency:
        links["insolvency"] = f"/company/{number}/insolvency"
    return APIResponse(200, {"company_number": number, "links": links}, f"https://x/company/{number}")


def test_fetches_only_profile_and_linked_insolvency(tmp_path):
    responses = {
        "/company/01234567": _profile("01234567", insolvency=False),
        "/company/07654321": _profile("07654321", insolvency=True),
        "/company/07654321/insolvency": APIResponse(
            200, {"cases": [{"type": "creditors-voluntary-liquidation"}]}, "https://x"
        ),
    }
    client = RecordingClient(responses)
    cache = RawCache(tmp_path)
    stats = fetch_profile_insolvency(client, cache, ["01234567", "07654321"])

    # Only profile + the one linked insolvency; never officers/psc/statements.
    assert client.calls == [
        "/company/01234567",
        "/company/07654321",
        "/company/07654321/insolvency",
    ]
    assert not any("officers" in c or "significant-control" in c for c in client.calls)
    assert stats.profile_requests == 2
    assert stats.insolvency_requests == 1
    assert stats.not_found == []


def test_insolvency_skipped_when_not_linked(tmp_path):
    responses = {"/company/01234567": _profile("01234567", insolvency=False)}
    client = RecordingClient(responses)
    stats = fetch_profile_insolvency(client, RawCache(tmp_path), ["01234567"])
    assert client.calls == ["/company/01234567"]
    assert stats.insolvency_requests == 0


def test_not_found_profile_is_recorded_not_errored(tmp_path):
    client = RecordingClient({})  # everything 404s
    stats = fetch_profile_insolvency(client, RawCache(tmp_path), ["00000000"])
    assert stats.not_found == ["00000000"]
    assert stats.errors == []
    # A 404 profile must not trigger an insolvency call.
    assert client.calls == ["/company/00000000"]


def test_resumes_from_cache_without_refetch(tmp_path):
    responses = {"/company/01234567": _profile("01234567", insolvency=False)}
    cache = RawCache(tmp_path)
    first = fetch_profile_insolvency(RecordingClient(responses), cache, ["01234567"])
    assert first.profile_requests == 1
    # Second run against the same cache: large default max_age_days => no refetch.
    client2 = RecordingClient(responses)
    second = fetch_profile_insolvency(client2, cache, ["01234567"])
    assert second.profile_requests == 0
    assert second.from_cache == 1
    assert client2.calls == []


def test_registered_society_recogniser():
    # Observed real forms accepted.
    for good in ("IP00120C", "SP3COLLS", "R0000173", "SL01002A", "SP0006CU"):
        assert is_registered_society_number(good), good
    # Ordinary / malformed forms rejected.
    for bad in ("01234567", "SC123456", "not-a-number", "IP0012", "1234567.0", "ZZ000001"):
        assert not is_registered_society_number(bad), bad


def _write_sample(path, numbers):
    path.write_text("company_number\n" + "\n".join(numbers) + "\n", encoding="utf-8")


def test_cli_allows_society_numbers_but_rejects_other_invalid(tmp_path, monkeypatch, capsys):
    """prospective-fetch allows IP/SP/R/SL forms; any other invalid hard-fails."""
    # With a genuinely malformed number present -> hard fail (rc 2), no --allow-invalid.
    bad = tmp_path / "bad.csv"
    _write_sample(bad, ["01234567", "IP00120C", "not-a-number"])
    rc = main(["prospective-fetch", "--input", str(bad), "--cache-dir", str(tmp_path / "c1")])
    assert rc == 2
    assert "refusing to drop" in capsys.readouterr().err

    # Society numbers only alongside valid ones, limit 0 network via --limit 0.
    ok = tmp_path / "ok.csv"
    _write_sample(ok, ["01234567", "IP00120C", "SP3COLLS"])
    rc = main(
        ["prospective-fetch", "--input", str(ok), "--cache-dir", str(tmp_path / "c2"), "--limit", "0"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "allowing 2 registered-society/royal-charter number(s)" in out


def test_one_bad_company_does_not_kill_the_run(tmp_path):
    class Boom(RecordingClient):
        def get(self, path, params=None):
            self.calls.append(path)
            if path == "/company/00000001":
                raise RuntimeError("boom")
            return _profile(path.rsplit("/", 1)[-1], insolvency=False)

    client = Boom({})
    stats = fetch_profile_insolvency(client, RawCache(tmp_path), ["00000001", "01234567"])
    assert len(stats.errors) == 1 and stats.errors[0][0] == "00000001"
    assert stats.profile_requests == 1  # the good one still fetched
