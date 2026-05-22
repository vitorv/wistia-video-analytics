"""Tests for the per-endpoint extractors. HTTP is mocked with ``responses``."""

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from src.ingestion import config
from src.ingestion.client import WistiaClient
from src.ingestion.extractors import (
    extract_by_date,
    extract_events,
    extract_media_metadata,
)

TOKEN = "test-token"  # noqa: S105 — dummy value, not a real secret
EVENTS_URL = f"{config.BASE_URL}/stats/events"


def _event(key: str, received_at: str) -> dict[str, str]:
    """Build a minimal Events record with the fields the extractor reads."""
    return {"event_key": key, "received_at": received_at, "media_id": "abc"}


def _query(request: requests.PreparedRequest) -> dict[str, list[str]]:
    """Parse the query string of a recorded request into a dict."""
    return parse_qs(urlparse(request.url or "").query)


# ── extract_events ───────────────────────────────────────────────────────────


@responses.activate
def test_extract_events_collects_all_pages_when_no_cutoff() -> None:
    responses.get(
        EVENTS_URL,
        json=[
            _event("e3", "2026-05-03T00:00:00Z"),
            _event("e2", "2026-05-02T00:00:00Z"),
        ],
    )
    responses.get(EVENTS_URL, json=[_event("e1", "2026-05-01T00:00:00Z")])
    responses.get(EVENTS_URL, json=[])
    events = extract_events(WistiaClient(TOKEN), "abc")
    assert [e["event_key"] for e in events] == ["e3", "e2", "e1"]


@responses.activate
def test_extract_events_stops_at_watermark() -> None:
    # newest-first; watermark = 2026-05-02, so e2 (==) and e1 (older) are excluded
    responses.get(
        EVENTS_URL,
        json=[
            _event("e3", "2026-05-03T00:00:00Z"),
            _event("e2", "2026-05-02T00:00:00Z"),
            _event("e1", "2026-05-01T00:00:00Z"),
        ],
    )
    since = datetime(2026, 5, 2, tzinfo=timezone.utc)
    events = extract_events(WistiaClient(TOKEN), "abc", since=since)
    assert [e["event_key"] for e in events] == ["e3"]


@responses.activate
def test_extract_events_watermark_spans_pages() -> None:
    responses.get(
        EVENTS_URL,
        json=[
            _event("e4", "2026-05-04T00:00:00Z"),
            _event("e3", "2026-05-03T00:00:00Z"),
        ],
    )
    responses.get(
        EVENTS_URL,
        json=[
            _event("e2", "2026-05-02T00:00:00Z"),
            _event("e1", "2026-05-01T00:00:00Z"),
        ],
    )
    since = datetime(2026, 5, 2, 12, tzinfo=timezone.utc)
    events = extract_events(WistiaClient(TOKEN), "abc", since=since)
    assert [e["event_key"] for e in events] == ["e4", "e3"]


@responses.activate
def test_extract_events_sends_media_id_filter() -> None:
    responses.get(EVENTS_URL, json=[])
    extract_events(WistiaClient(TOKEN), "xyz123")
    assert _query(responses.calls[0].request)["media_id"] == ["xyz123"]


@responses.activate
def test_extract_events_empty_returns_empty_list() -> None:
    responses.get(EVENTS_URL, json=[])
    assert extract_events(WistiaClient(TOKEN), "abc") == []


@responses.activate
def test_extract_events_rejects_naive_since() -> None:
    naive_since = datetime(2026, 5, 2)  # no tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        extract_events(WistiaClient(TOKEN), "abc", since=naive_since)


# ── extract_by_date ──────────────────────────────────────────────────────────


@responses.activate
def test_extract_by_date_returns_records_and_sends_date_range() -> None:
    url = f"{config.BASE_URL}/stats/medias/abc/by_date"
    responses.get(url, json=[{"date": "2024-03-01", "play_count": 5}])
    records = extract_by_date(WistiaClient(TOKEN), "abc", date(2024, 3, 1), date(2024, 3, 31))
    assert records == [{"date": "2024-03-01", "play_count": 5}]
    query = _query(responses.calls[0].request)
    assert query["start_date"] == ["2024-03-01"]
    assert query["end_date"] == ["2024-03-31"]


# ── extract_media_metadata ───────────────────────────────────────────────────


@responses.activate
def test_extract_media_metadata_returns_dict() -> None:
    url = f"{config.BASE_URL}/medias/abc"
    responses.get(url, json={"hashed_id": "abc", "name": "Demo Video"})
    metadata = extract_media_metadata(WistiaClient(TOKEN), "abc")
    assert metadata == {"hashed_id": "abc", "name": "Demo Video"}


# ── fixture-based shape tests (sanitized real API response shapes) ────────────


@responses.activate
def test_extract_events_handles_full_record_shape(
    load_fixture: Callable[[str], Any],
) -> None:
    page = load_fixture("events_page.json")  # 3 events, newest-first
    responses.get(EVENTS_URL, json=page)
    # cutoff falls between event 2 (13:30) and event 3 (11:15)
    since = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    events = extract_events(WistiaClient(TOKEN), "gskhw4w4lm", since=since)
    # watermark cutoff works on the real ".000Z" received_at format
    assert len(events) == 2
    # the full nested record shape survives the pull intact
    assert events[0]["user_agent_details"]["browser"] == "Chrome"
    assert events[0]["thumbnail"]["type"] == "StillImageFile"


@responses.activate
def test_extract_by_date_handles_full_record_shape(
    load_fixture: Callable[[str], Any],
) -> None:
    rows = load_fixture("by_date.json")
    url = f"{config.BASE_URL}/stats/medias/gskhw4w4lm/by_date"
    responses.get(url, json=rows)
    result = extract_by_date(
        WistiaClient(TOKEN), "gskhw4w4lm", date(2026, 5, 18), date(2026, 5, 20)
    )
    assert result == rows
    assert {"date", "load_count", "play_count", "hours_watched"} <= result[0].keys()


@responses.activate
def test_extract_media_metadata_handles_full_record_shape(
    load_fixture: Callable[[str], Any],
) -> None:
    meta = load_fixture("media_metadata.json")
    responses.get(f"{config.BASE_URL}/medias/gskhw4w4lm", json=meta)
    result = extract_media_metadata(WistiaClient(TOKEN), "gskhw4w4lm")
    assert result == meta
    # fields the Gold dim_media is derived from
    assert {"hashed_id", "name", "created"} <= result.keys()
