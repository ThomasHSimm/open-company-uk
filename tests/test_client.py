import pytest

from ukcompany.client import CHAuthError, CHClient, TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def test_token_bucket_blocks_at_capacity():
    clock = FakeClock()
    bucket = TokenBucket(capacity=3, window_s=300.0, clock=clock.now, sleep=clock.sleep)
    for _ in range(3):
        bucket.acquire()
    assert clock.slept == []
    bucket.acquire()  # 4th within the window must wait out the remainder
    assert len(clock.slept) == 1
    assert clock.slept[0] == pytest.approx(300.0)


def test_token_bucket_window_slides():
    clock = FakeClock()
    bucket = TokenBucket(capacity=2, window_s=10.0, clock=clock.now, sleep=clock.sleep)
    bucket.acquire()
    clock.t = 11.0  # first stamp expired
    bucket.acquire()
    bucket.acquire()
    assert clock.slept == []  # capacity 2, only 2 live stamps at any point


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    """Yields queued responses; records calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.auth = None

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def make_client(responses):
    clock = FakeClock()
    bucket = TokenBucket(capacity=1000, window_s=300.0, clock=clock.now, sleep=clock.sleep)
    session = FakeSession(responses)
    client = CHClient(api_key="test-key", session=session, bucket=bucket, sleep=clock.sleep)
    return client, session, clock


def test_get_200():
    client, session, _ = make_client([FakeResponse(200, {"company_number": "01234567"})])
    resp = client.get("/company/01234567")
    assert resp.status_code == 200 and resp.json["company_number"] == "01234567"


def test_get_404_returned_not_retried():
    client, session, _ = make_client([FakeResponse(404)])
    resp = client.get("/company/99999999")
    assert resp.not_found and session.calls == 1


def test_429_respects_retry_after_then_succeeds():
    client, session, clock = make_client(
        [FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200, {"ok": True})]
    )
    resp = client.get("/company/01234567")
    assert resp.status_code == 200 and session.calls == 2
    assert 7.0 in clock.slept


def test_5xx_backs_off_then_succeeds():
    client, session, clock = make_client([FakeResponse(502), FakeResponse(200, {"ok": True})])
    resp = client.get("/company/01234567")
    assert resp.status_code == 200 and session.calls == 2
    assert clock.slept  # some backoff happened


def test_401_raises_auth_error():
    client, _, _ = make_client([FakeResponse(401)])
    with pytest.raises(CHAuthError):
        client.get("/company/01234567")


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("CH_API_KEY", raising=False)
    with pytest.raises(CHAuthError):
        CHClient()
