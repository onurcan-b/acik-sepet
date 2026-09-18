from datetime import datetime, timezone
from email.utils import format_datetime

import pytest
import requests

from acik_sepet import api
from acik_sepet.api import MarketFiyatiError, search_products


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(api.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(api.time, "time", lambda: 1_800_000_000 + clock.now)
    monkeypatch.setattr(api.time, "sleep", clock.sleep)
    monkeypatch.setattr(api.random, "uniform", lambda *_: 0.5)
    return clock


class FakeResponse:
    def __init__(self, body=None, *, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.body = body if body is not None else {"content": [{"id": "a", "title": "Yerli Muz 1 Kg"}]}

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeSession:
    def __init__(self, outcomes=None):
        self.payloads = []
        self.started_at = []
        self.outcomes = iter(outcomes or [FakeResponse()])
        self.closed = False

    def post(self, _url, *, headers, json, timeout):
        assert timeout == 30
        assert "Connection" not in headers
        self.payloads.append(json)
        self.started_at.append(api.time.monotonic())
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


def test_search_sends_market_category_filter():
    session = FakeSession()
    rows = search_products(
        "muz kg",
        category_level="sub_category",
        category_values=["Muz"],
        session=session,
    )
    assert [row["id"] for row in rows] == ["a"]
    assert session.payloads == [{"keywords": "muz kg", "pages": 0, "size": 25, "sub_category": ["Muz"]}]
    assert rows[0]["_query_category_level"] == "sub_category"
    assert rows[0]["_query_category_values"] == ["Muz"]
    assert not session.closed


def test_transient_page_failure_recovers_complete_pool_and_keeps_page_number():
    session = FakeSession([
        FakeResponse({"content": [{"id": "a"}, {"id": "b"}]}),
        requests.ConnectionError("RemoteDisconnected"),
        FakeResponse({"content": [{"id": "b"}, {"id": "c"}]}),
        FakeResponse({"content": []}),
    ])
    result = search_products("q", page_size=2, session=session)
    assert [row["id"] for row in result] == ["a", "b", "c"]
    assert [payload["pages"] for payload in session.payloads] == [0, 1, 1, 2]
    assert all(b - a >= 1.25 for a, b in zip(session.started_at, session.started_at[1:]))


def test_failed_page_raises_instead_of_returning_partial_results(clock):
    session = FakeSession([
        FakeResponse({"content": [{"id": "a"}, {"id": "b"}]}),
        requests.ConnectionError("disconnected"),
        requests.ConnectionError("disconnected"),
        requests.ConnectionError("disconnected"),
    ])
    with pytest.raises(MarketFiyatiError, match="sayfa 1") as error:
        search_products("q", page_size=2, session=session)
    assert error.value.retryable
    assert [payload["pages"] for payload in session.payloads] == [0, 1, 1, 1]
    assert clock.sleeps == [1.25, 1.5, 2.5]
    assert not session.closed


def test_pacing_is_shared_across_pages_and_product_searches():
    session = FakeSession([
        FakeResponse({"content": [{"id": "a"}, {"id": "b"}]}),
        FakeResponse({"content": []}),
        FakeResponse({"content": [{"id": "c"}]}),
    ])
    search_products("first", page_size=2, session=session)
    search_products("second", session=session)
    assert session.started_at == [1000.0, 1001.25, 1002.5]


@pytest.mark.parametrize("error", [requests.Timeout("timeout"), requests.exceptions.ChunkedEncodingError("body interrupted")])
def test_transient_timeout_or_interrupted_response_recovers(error):
    session = FakeSession([error, FakeResponse()])
    assert search_products("q", session=session)[0]["id"] == "a"
    assert len(session.payloads) == 2


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize("use_date", [False, True])
def test_retry_after_seconds_and_http_date_are_honored(status, use_date, clock):
    retry_after = (
        format_datetime(datetime.fromtimestamp(api.time.time() + 9, tz=timezone.utc), usegmt=True)
        if use_date else "9"
    )
    session = FakeSession([
        FakeResponse(status=status, headers={"Retry-After": retry_after}),
        FakeResponse(),
    ])
    assert search_products("q", session=session)[0]["id"] == "a"
    assert session.started_at == [1000.0, 1009.0]
    assert clock.sleeps == [9.0]


def test_long_server_cooldown_is_deferred_without_early_request(clock):
    session = FakeSession([
        FakeResponse(status=429, headers={"Retry-After": "120"}),
        FakeResponse(),
    ])
    for query in ["first", "second"]:
        with pytest.raises(MarketFiyatiError) as error:
            search_products(query, session=session)
        assert error.value.retryable
        assert error.value.retry_after == 120
    assert len(session.payloads) == 1
    assert clock.sleeps == []
    clock.now += 120
    assert search_products("after cooldown", session=session)[0]["id"] == "a"
    assert session.started_at == [1000.0, 1120.0]


@pytest.mark.parametrize("header", ["invalid", "nan", "inf", "-8"])
def test_invalid_or_past_retry_after_uses_bounded_backoff(header, clock):
    session = FakeSession([
        FakeResponse(status=503, headers={"Retry-After": header}),
        FakeResponse(),
    ])
    search_products("q", session=session)
    assert clock.sleeps == [1.5]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 418])
def test_permanent_http_errors_are_never_retried(status, clock):
    session = FakeSession([FakeResponse(status=status)])
    with pytest.raises(MarketFiyatiError, match=f"HTTP {status}") as error:
        search_products("q", session=session)
    assert not error.value.retryable
    assert len(session.payloads) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("body", [
    ValueError("not JSON"), {}, [], {"content": "bad"}, {"content": [None]},
])
def test_schema_errors_are_nonretryable(body, clock):
    session = FakeSession([FakeResponse(body)])
    with pytest.raises(MarketFiyatiError) as error:
        search_products("q", session=session)
    assert not error.value.retryable
    assert len(session.payloads) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize("fails", [False, True])
def test_owned_session_is_closed_on_success_and_failure(monkeypatch, fails):
    session = FakeSession([FakeResponse(status=403)] if fails else None)
    monkeypatch.setattr(api.requests, "Session", lambda: session)
    if fails:
        with pytest.raises(MarketFiyatiError):
            search_products("q")
    else:
        search_products("q")
    assert session.closed


def test_retryable_default_keeps_caller_test_doubles_compatible():
    assert MarketFiyatiError("temporary").retryable
    assert MarketFiyatiError("temporary").retry_after is None
