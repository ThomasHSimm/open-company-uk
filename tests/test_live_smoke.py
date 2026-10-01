"""Manual smoke test against the real API. Skipped by default (pyproject addopts).

Run with a real key:
    CH_API_KEY=... pytest -m live -q
"""

import os

import pytest

from ukcompany.client import CHClient


@pytest.mark.live
@pytest.mark.skipif("CH_API_KEY" not in os.environ, reason="needs CH_API_KEY")
def test_live_profile_fetch():
    client = CHClient()
    # 00000006 is a long-standing real company number often used in CH examples.
    resp = client.get("/company/00000006")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert resp.json.get("company_number") == "00000006"
