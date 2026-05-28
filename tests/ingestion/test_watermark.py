"""Tests for the incremental watermark store — local + S3 backends."""

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

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


# --- S3 backend ----------------------------------------------------------------


@pytest.fixture
def s3_bucket() -> Any:
    """A moto-backed S3 bucket fixture; yields its name."""
    with mock_aws():
        bucket = "test-state-bucket"
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        yield bucket


def test_load_missing_s3_object_returns_floor_defaults(s3_bucket: str) -> None:
    """Loading from an S3 key that doesn't exist yet starts from the floor."""
    uri = f"s3://{s3_bucket}/state/watermark.json"
    store = WatermarkStore.load(uri)
    assert store.events_since("abc") == datetime.combine(
        config.BACKFILL_FLOOR_DATE, time.min, tzinfo=timezone.utc
    )
    assert store.by_date_start("abc") == config.BACKFILL_FLOOR_DATE


def test_watermark_round_trips_through_s3(s3_bucket: str) -> None:
    """Save → re-load preserves both watermark kinds via S3."""
    uri = f"s3://{s3_bucket}/state/watermark.json"
    store = WatermarkStore.load(uri)
    events_wm = datetime(2026, 5, 20, 14, 47, 14, tzinfo=timezone.utc)
    by_date_wm = date(2026, 5, 20)
    store.set_events_watermark("abc", events_wm)
    store.set_by_date_watermark("abc", by_date_wm)
    store.save()

    # Confirm the object exists in S3
    head = boto3.client("s3", region_name="us-east-1").head_object(
        Bucket=s3_bucket, Key="state/watermark.json"
    )
    assert head["ContentType"] == "application/json"

    # Round-trip through a fresh load
    reloaded = WatermarkStore.load(uri)
    assert reloaded.events_since("abc") == events_wm
    assert reloaded.by_date_start("abc") == by_date_wm


def test_load_s3_propagates_unexpected_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-NoSuchKey ClientError is re-raised (not silently treated as absent)."""
    from botocore.exceptions import ClientError

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "GetObject")

    monkeypatch.setattr("botocore.client.BaseClient._make_api_call", _raise)
    with pytest.raises(ClientError, match="AccessDenied"):
        WatermarkStore.load("s3://any-bucket/any-key")
