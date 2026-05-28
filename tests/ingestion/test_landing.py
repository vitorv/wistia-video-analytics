"""Tests for the landing-zone writer — local + S3 backends."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from src.ingestion.landing import write_landing


def test_write_landing_creates_partitioned_path(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, 14, 30, tzinfo=timezone.utc)
    location = write_landing(
        "events",
        "gskhw4w4lm",
        [{"event_key": "e1"}],
        landing_root=tmp_path,
        ingest_time=ts,
    )
    path = Path(location)
    assert path.parent == (tmp_path / "events" / "media_id=gskhw4w4lm" / "ingest_date=2026-05-21")
    assert path.name.startswith("data_") and path.name.endswith(".json")
    assert path.is_file()


def test_write_landing_stores_raw_records_and_metadata(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, 14, 30, 0, tzinfo=timezone.utc)
    records: list[dict[str, Any]] = [
        {"event_key": "e1", "percent_viewed": 0.5},
        {"event_key": "e2"},
    ]
    location = write_landing("events", "abc", records, landing_root=tmp_path, ingest_time=ts)

    content = json.loads(Path(location).read_text(encoding="utf-8"))
    assert content["records"] == records  # raw records stored unmodified
    meta = content["ingestion_metadata"]
    assert meta["endpoint"] == "events"
    assert meta["media_id"] == "abc"
    assert meta["ingest_date"] == "2026-05-21"
    assert meta["ingest_timestamp"] == "2026-05-21T14:30:00+00:00"
    assert meta["record_count"] == 2


def test_write_landing_distinct_runs_keep_separate_files(tmp_path: Path) -> None:
    run1 = Path(
        write_landing(
            "by_date",
            "abc",
            [{"date": "2026-05-20"}],
            landing_root=tmp_path,
            ingest_time=datetime(2026, 5, 21, 9, 0, 0, tzinfo=timezone.utc),
        )
    )
    run2 = Path(
        write_landing(
            "by_date",
            "abc",
            [{"date": "2026-05-21"}],
            landing_root=tmp_path,
            ingest_time=datetime(2026, 5, 21, 15, 30, 0, tzinfo=timezone.utc),
        )
    )

    # both runs land on 2026-05-21 — same partition, distinct immutable files
    assert run1 != run2
    assert run1.parent == run2.parent
    assert sorted(run1.parent.iterdir()) == sorted([run1, run2])
    assert json.loads(run1.read_text(encoding="utf-8"))["records"] == [{"date": "2026-05-20"}]
    assert json.loads(run2.read_text(encoding="utf-8"))["records"] == [{"date": "2026-05-21"}]


def test_write_landing_empty_records(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, tzinfo=timezone.utc)
    location = write_landing("events", "abc", [], landing_root=tmp_path, ingest_time=ts)

    content = json.loads(Path(location).read_text(encoding="utf-8"))
    assert content["records"] == []
    assert content["ingestion_metadata"]["record_count"] == 0


# --- S3 backend ----------------------------------------------------------------


@pytest.fixture
def s3_bucket() -> Any:
    """A moto-backed S3 bucket fixture; yields its name."""
    with mock_aws():
        bucket = "test-landing-bucket"
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=bucket)
        yield bucket


def test_write_landing_s3_puts_object_at_expected_key(s3_bucket: str) -> None:
    ts = datetime(2026, 5, 21, 14, 30, 0, tzinfo=timezone.utc)
    location = write_landing(
        "events",
        "abc",
        [{"event_key": "e1"}],
        landing_root=f"s3://{s3_bucket}/landing",
        ingest_time=ts,
    )

    expected_key_prefix = "landing/events/media_id=abc/ingest_date=2026-05-21/data_20260521T143000"
    assert location.startswith(f"s3://{s3_bucket}/{expected_key_prefix}")
    assert location.endswith(".json")

    key = location.removeprefix(f"s3://{s3_bucket}/")
    body = boto3.client("s3", region_name="us-east-1").get_object(Bucket=s3_bucket, Key=key)
    content = json.loads(body["Body"].read().decode("utf-8"))
    assert content["records"] == [{"event_key": "e1"}]
    assert content["ingestion_metadata"]["endpoint"] == "events"
    assert content["ingestion_metadata"]["record_count"] == 1


def test_write_landing_s3_handles_uri_with_no_prefix(s3_bucket: str) -> None:
    ts = datetime(2026, 5, 21, 14, 30, 0, tzinfo=timezone.utc)
    location = write_landing(
        "by_date",
        "abc",
        [{"date": "2026-05-21", "play_count": 3}],
        landing_root=f"s3://{s3_bucket}",
        ingest_time=ts,
    )

    # No prefix — key starts at the endpoint directly
    assert location.startswith(f"s3://{s3_bucket}/by_date/media_id=abc/")
