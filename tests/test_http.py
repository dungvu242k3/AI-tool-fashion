"""Retry behavior is verified with virtual time and isolated HTTP responses."""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from email.utils import format_datetime

import pytest
import requests

from src.collectors.errors import CollectionError, ResponseParseError
from src.collectors.http import HTTPClient, retry_after_seconds
from src.collectors.http_policy import HTTPPolicy


def fetch(http, journal, *, method="GET", **kwargs):
    return http.client.fetch(
        method, "https://example.test/search", source="fixture", operation="search",
        query={"search_term": "fixture query"}, journal=journal, **kwargs,
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_recovers_with_bounded_observed_attempts(http_factory, response_factory, status):
    first, second = response_factory(status), response_factory(payload={"data": "observed"})
    http = http_factory([first, second], policy=HTTPPolicy(max_attempts=3))
    journal = []
    response = fetch(http, journal)
    assert response.json() == {"data": "observed"}
    assert [trace.status_code for trace in journal] == [status, 200]
    assert [trace.attempt for trace in journal] == [1, 2]
    assert len({trace.operation_id for trace in journal}) == 1
    assert len({trace.request_id for trace in journal}) == 2
    assert response.request_id == journal[-1].request_id
    assert http.clock.sleeps == [0.375]
    assert journal[0].retry_delay_seconds == 0.375
    first.close.assert_called_once()
    second.close.assert_called_once()
    kwargs = http.session.request.call_args.kwargs
    assert kwargs["timeout"] == (5.0, 20.0)
    assert kwargs["allow_redirects"] is False


def test_retries_exhaust_without_a_success_response(http_factory, response_factory):
    http = http_factory([response_factory(503) for _ in range(3)], policy=HTTPPolicy(max_attempts=3))
    journal = []
    with pytest.raises(CollectionError) as failure:
        fetch(http, journal)
    assert failure.value.warning.code == "http_503"
    assert failure.value.warning.request_id == journal[-1].request_id
    assert len(journal) == 3
    assert http.clock.sleeps == [0.375, 0.75]
    assert journal[-1].retry_delay_seconds == 0


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 409, 422, 501])
def test_other_http_errors_are_not_retried(http_factory, response_factory, status):
    http = http_factory([response_factory(status)], policy=HTTPPolicy(max_attempts=3))
    journal = []
    with pytest.raises(CollectionError):
        fetch(http, journal)
    assert len(journal) == 1
    assert http.clock.sleeps == []


@pytest.mark.parametrize("error", [requests.ConnectTimeout, requests.ReadTimeout, requests.ConnectionError])
def test_transient_network_failures_recover(http_factory, response_factory, error):
    http = http_factory([error("private error details"), response_factory()], policy=HTTPPolicy(max_attempts=3))
    journal = []
    fetch(http, journal)
    assert len(journal) == 2
    assert journal[0].status_code is None
    assert "private error details" not in json.dumps([asdict(trace) for trace in journal])


def test_tls_failure_is_not_retried(http_factory):
    http = http_factory([requests.exceptions.SSLError("fixture certificate error")], policy=HTTPPolicy(max_attempts=3))
    journal = []
    with pytest.raises(CollectionError) as failure:
        fetch(http, journal)
    assert failure.value.warning.code == "tls_error"
    assert len(journal) == 1
    assert not http.clock.sleeps


@pytest.mark.parametrize("kind", ["seconds", "http_date"])
def test_retry_after_is_a_minimum_delay(http_factory, response_factory, kind):
    header = "4" if kind == "seconds" else "Wed, 21 Oct 2026 00:00:04 GMT"
    http = http_factory([
        response_factory(429, headers={"Retry-After": header}), response_factory(),
    ], policy=HTTPPolicy(max_attempts=3))
    journal = []
    fetch(http, journal)
    assert http.clock.sleeps == [4]
    assert journal[0].retry_after_seconds == 4
    assert journal[1].started_at >= journal[0].completed_at


def test_long_retry_after_defers_request_and_next_query(http_factory, response_factory):
    http = http_factory([response_factory(429, headers={"Retry-After": "3600"})], policy=HTTPPolicy(retry_wait_budget=3))
    journal = []
    with pytest.raises(CollectionError) as failure:
        fetch(http, journal)
    assert failure.value.warning.code == "retry_after_deferred"
    assert journal[0].retry_after_seconds == 3600
    assert http.clock.sleeps == []
    next_journal = []
    with pytest.raises(CollectionError) as next_failure:
        fetch(http, next_journal)
    assert next_failure.value.warning.code == "source_cooldown"
    assert next_journal == []  # No invented attempt for a call that did not happen.
    assert http.session.request.call_count == 1


def test_cumulative_retry_wait_budget_cannot_be_exceeded(http_factory, response_factory):
    http = http_factory([
        response_factory(503, headers={"Retry-After": "2"}),
        response_factory(503, headers={"Retry-After": "2"}),
    ], policy=HTTPPolicy(retry_wait_budget=3))
    journal = []
    with pytest.raises(CollectionError):
        fetch(http, journal)
    assert len(journal) == 2
    assert http.clock.sleeps == [2]


@pytest.mark.parametrize("value", [None, "bad value", "-1", "1.5"])
def test_invalid_retry_after_uses_backoff(value):
    assert retry_after_seconds(value, datetime(2026, 10, 21, tzinfo=timezone.utc)) is None


def test_past_retry_date_does_not_introduce_a_negative_delay():
    assert retry_after_seconds("Tue, 20 Oct 2026 00:00:00 GMT", datetime(2026, 10, 21, tzinfo=timezone.utc)) == 0


def test_malformed_json_is_not_an_http_retry(http_factory, response_factory):
    http = http_factory([response_factory(text="{invalid")], policy=HTTPPolicy(max_attempts=3))
    journal = []
    response = fetch(http, journal)
    with pytest.raises(ResponseParseError) as failure:
        response.json()
    assert failure.value.warning.request_id == journal[0].request_id
    assert len(journal) == 1
    assert not http.clock.sleeps


def test_post_requires_explicit_retry_safety(http_factory, response_factory):
    unsafe = http_factory([response_factory(503)], policy=HTTPPolicy(max_attempts=3))
    with pytest.raises(CollectionError):
        fetch(unsafe, [], method="POST")
    assert unsafe.session.request.call_count == 1
    safe = http_factory([response_factory(503), response_factory()], policy=HTTPPolicy(max_attempts=3))
    fetch(safe, [], method="POST", retry_safe=True)
    assert safe.session.request.call_count == 2


def test_redirects_are_bounded_and_recorded(http_factory, response_factory):
    http = http_factory([response_factory(302, headers={"Location": "/next"}), response_factory()])
    journal = []
    fetch(http, journal)
    assert [trace.status_code for trace in journal] == [302, 200]
    assert [trace.redirect_hop for trace in journal] == [0, 1]
    assert journal[-1].url == "https://example.test/next"
    assert len({trace.operation_id for trace in journal}) == 1


@pytest.mark.parametrize("target", ["https://other.test/next", "http://example.test/next"])
def test_redirect_never_forwards_auth_to_another_origin(http_factory, response_factory, target):
    http = http_factory([response_factory(302, headers={"Location": target})])
    journal = []
    with pytest.raises(CollectionError) as failure:
        fetch(http, journal, headers={"Authorization": "private auth"})
    assert failure.value.warning.code == "redirect_rejected"
    assert len(journal) == 1


def test_redirect_loop_terminates_at_limit(http_factory, response_factory):
    http = http_factory([response_factory(302, headers={"Location": "/next"}) for _ in range(3)], policy=HTTPPolicy(max_redirects=2))
    journal = []
    with pytest.raises(CollectionError):
        fetch(http, journal)
    assert len(journal) == 3


def test_request_audit_redacts_credentials_without_altering_outbound_request(http_factory, response_factory):
    http = http_factory([response_factory()])
    journal = []
    fetch(http, journal, params={"q": "visible query", "token": "private-token", "req": json.dumps({"api_key": "private-key"})}, headers={"Authorization": "private-auth"}, cookies={"NID": "private-cookie"})
    audit = json.dumps([asdict(trace) for trace in journal])
    assert "private-" not in audit
    assert "visible" in audit
    assert http.session.request.call_args.kwargs["params"]["token"] == "private-token"


def test_default_client_has_no_hidden_retries_and_closes_session_once(monkeypatch):
    session = requests.Session()
    closed = []
    monkeypatch.setattr(session, "close", lambda: closed.append(True))
    monkeypatch.setattr(requests, "Session", lambda: session)
    client = HTTPClient(policy=HTTPPolicy())
    assert session.get_adapter("https://").max_retries.total == 0
    client.close()
    client.close()
    assert closed == [True]


def test_borrowed_session_is_not_closed(http_factory):
    http = http_factory([])
    http.client.close()
    http.session.close.assert_not_called()


@pytest.mark.parametrize("values", [
    {"connect_timeout": 0}, {"read_timeout": float("nan")}, {"max_attempts": 0},
    {"max_attempts": 2.5}, {"max_redirects": -1}, {"backoff_base": 10, "backoff_cap": 2},
])
def test_invalid_http_configuration_fails_fast(values):
    with pytest.raises(ValueError):
        HTTPPolicy(**values)


def test_http_policy_reads_environment_and_validates(monkeypatch):
    monkeypatch.setenv("TREND_HTTP_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("TREND_HTTP_CONNECT_TIMEOUT", "3.5")
    assert HTTPPolicy.from_env().max_attempts == 2
    assert HTTPPolicy.from_env().connect_timeout == 3.5
    monkeypatch.setenv("TREND_HTTP_MAX_ATTEMPTS", "broken")
    with pytest.raises(ValueError, match="TREND_HTTP_MAX_ATTEMPTS"):
        HTTPPolicy.from_env()


def test_nested_json_query_secrets_are_redacted_despite_leading_whitespace(http_factory, response_factory):
    http = http_factory([response_factory()])
    journal = []
    fetch(http, journal, params={"req": ' \n{"token": "private-token", "query": "visible"}'})
    assert "private-token" not in journal[0].url
    assert "visible" in journal[0].url
