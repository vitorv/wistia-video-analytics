"""Tests for the incremental watermark store."""

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import pytest

from src.ingestion import config
from src.ingestion.watermark import WatermarkStore, newest_received_at


def test_load_missing_file_returns_floor_defaults(tmp_path: Path) -> None:
    store = WatermarkStore.load(tmp_path / "_watermark.json")
    assert store.events_since("abc") == datetime.combine(
        config.BACKFILL_FLOOR_DATE, time.min, tzinfo=timezone.utc
    )
    assert store.by_date_start("abc") == config.BACKFILL_FLOOR_DATE


def test_events_since_floor_default_is_timezone_aware(tmp_path: Path) -> None:
    store = WatermarkStore.load(tmp_path / "_watermark.json")
    assert store.events_since("abc").utcoffset() is not None


def test_events_watermark_round_trips_aware(tmp_path: Path) -> None:
    path = tmp_path / "_watermark.json"
    store = WatermarkStore.load(path)
    watermark = datetime(2026, 5, 20, 14, 47, 14, tzinfo=timezone.utc)
    store.set_events_watermark("abc", watermark)
    store.save()

    reloaded = WatermarkStore.load(path).events_since("abc")
    assert reloaded == watermark
    assert reloaded.utcoffset() is not None  # still aware after the JSON round-trip


def test_set_events_watermark_rejects_naive(tmp_path: Path) -> None:
    store = WatermarkStore.load(tmp_path / "_watermark.json")
    with pytest.raises(ValueError, match="timezone-aware"):
        store.set_events_watermark("abc", datetime(2026, 5, 20))


def test_by_date_watermark_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "_watermark.json"
    store = WatermarkStore.load(path)
    store.set_by_date_watermark("abc", date(2026, 5, 20))
    store.save()

    assert WatermarkStore.load(path).by_date_start("abc") == date(2026, 5, 20)


def test_watermarks_are_isolated_per_media(tmp_path: Path) -> None:
    path = tmp_path / "_watermark.json"
    store = WatermarkStore.load(path)
    store.set_by_date_watermark("media_a", date(2026, 5, 1))
    store.set_by_date_watermark("media_b", date(2026, 5, 15))
    store.save()

    reloaded = WatermarkStore.load(path)
    assert reloaded.by_date_start("media_a") == date(2026, 5, 1)
    assert reloaded.by_date_start("media_b") == date(2026, 5, 15)


def test_newest_received_at_returns_latest() -> None:
    events: list[dict[str, Any]] = [
        {"received_at": "2026-05-03T00:00:00Z"},
        {"received_at": "2026-05-05T00:00:00Z"},
        {"received_at": "2026-05-04T00:00:00Z"},
    ]
    assert newest_received_at(events) == datetime(2026, 5, 5, tzinfo=timezone.utc)


def test_newest_received_at_empty_returns_none() -> None:
    assert newest_received_at([]) is None
