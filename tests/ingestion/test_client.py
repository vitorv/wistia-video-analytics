"""Tests for the Wistia API client.

HTTP behaviour is mocked with the ``responses`` library — no live API calls.
The retry/backoff loop lives inside urllib3's adapter, which ``responses``
patches over; that loop cannot be exercised here, so the retry *policy* is
verified by introspection instead (see ``test_retry_policy_is_configured``).
"""

import logging
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.ingestion.client import WistiaClient
from src.ingestion.errors import WistiaAPIError, WistiaAuthError, WistiaNotFoundError

BASE = "https://api.wistia.com/modern"
TOKEN = "test-token"  # noqa: S105 — dummy value, not a real secret


def _query(request: requests.PreparedRequest) -> dict[str, list[str]]:
    """Parse the query string of a recorded request into a dict."""
    return parse_qs(urlparse(request.url or "").query)


@responses.activate
def test_get_returns_parsed_json() -> None:
    responses.get(f"{BASE}/medias/abc", json={"hashed_id": "abc", "name": "Demo"})
    client = WistiaClient(TOKEN)
    assert client.get(f"{BASE}/medias/abc") == {"hashed_id": "abc", "name": "Demo"}


@responses.activate
def test_get_sends_bearer_auth_header() -> None:
    responses.get(f"{BASE}/medias/abc", json={})
    WistiaClient(TOKEN).get(f"{BASE}/medias/abc")
    assert responses.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
def test_get_raises_not_found_on_404() -> None:
    responses.get(f"{BASE}/medias/missing", status=404)
    with pytest.raises(WistiaNotFoundError):
        WistiaClient(TOKEN).get(f"{BASE}/medias/missing")


@responses.activate
def test_get_raises_auth_error_on_401() -> None:
    responses.get(f"{BASE}/medias/abc", status=401)
    with pytest.raises(WistiaAuthError):
        WistiaClient(TOKEN).get(f"{BASE}/medias/abc")


@responses.activate
def test_get_raises_api_error_on_server_error() -> None:
    responses.get(f"{BASE}/medias/abc", status=503)
    with pytest.raises(WistiaAPIError):
        WistiaClient(TOKEN).get(f"{BASE}/medias/abc")


@responses.activate
def test_get_raises_api_error_on_connection_failure() -> None:
    responses.get(f"{BASE}/medias/abc", body=requests.ConnectionError("boom"))
    with pytest.raises(WistiaAPIError):
        WistiaClient(TOKEN).get(f"{BASE}/medias/abc")


@responses.activate
def test_failure_emits_error_log(caplog: pytest.LogCaptureFixture) -> None:
    responses.get(f"{BASE}/medias/abc", status=500)
    with caplog.at_level(logging.ERROR), pytest.raises(WistiaAPIError):
        WistiaClient(TOKEN).get(f"{BASE}/medias/abc")
    assert any(record.levelno == logging.ERROR for record in caplog.records)


@responses.activate
def test_paginate_yields_pages_until_empty() -> None:
    url = f"{BASE}/stats/events"
    responses.get(url, json=[{"event_key": "e1"}, {"event_key": "e2"}])
    responses.get(url, json=[{"event_key": "e3"}])
    responses.get(url, json=[])
    pages = list(WistiaClient(TOKEN).paginate(url))
    assert pages == [
        [{"event_key": "e1"}, {"event_key": "e2"}],
        [{"event_key": "e3"}],
    ]


@responses.activate
def test_paginate_empty_first_page_yields_nothing() -> None:
    url = f"{BASE}/stats/events"
    responses.get(url, json=[])
    assert list(WistiaClient(TOKEN).paginate(url)) == []


@responses.activate
def test_paginate_increments_page_and_keeps_base_params() -> None:
    url = f"{BASE}/stats/events"
    responses.get(url, json=[{"event_key": "e1"}])
    responses.get(url, json=[])
    list(WistiaClient(TOKEN).paginate(url, params={"media_id": "abc"}))
    assert _query(responses.calls[0].request) == {"page": ["1"], "media_id": ["abc"]}
    assert _query(responses.calls[1].request) == {"page": ["2"], "media_id": ["abc"]}


@responses.activate
def test_paginate_does_not_mutate_caller_params() -> None:
    url = f"{BASE}/stats/events"
    responses.get(url, json=[])
    params = {"media_id": "abc"}
    list(WistiaClient(TOKEN).paginate(url, params=params))
    assert params == {"media_id": "abc"}  # no "page" key leaked back


def test_retry_policy_is_configured() -> None:
    adapter = WistiaClient(TOKEN)._session.get_adapter("https://api.wistia.com")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.backoff_factor == 1
    assert {429, 500, 502, 503, 504}.issubset(set(retry.status_forcelist or []))


def test_context_manager_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = WistiaClient(TOKEN)
    closed: list[bool] = []
    monkeypatch.setattr(client._session, "close", lambda: closed.append(True))
    with client:
        pass
    assert closed == [True]
