"""Tests for the landing-zone writer."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingestion.landing import write_landing


def test_write_landing_creates_partitioned_path(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, 14, 30, tzinfo=timezone.utc)
    path = write_landing(
        "events",
        "gskhw4w4lm",
        [{"event_key": "e1"}],
        landing_root=tmp_path,
        ingest_time=ts,
    )
    expected = tmp_path / "events" / "media_id=gskhw4w4lm" / "ingest_date=2026-05-21" / "data.json"
    assert path == expected
    assert path.is_file()


def test_write_landing_stores_raw_records_and_metadata(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, 14, 30, 0, tzinfo=timezone.utc)
    records: list[dict[str, Any]] = [
        {"event_key": "e1", "percent_viewed": 0.5},
        {"event_key": "e2"},
    ]
    path = write_landing("events", "abc", records, landing_root=tmp_path, ingest_time=ts)

    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["records"] == records  # raw records stored unmodified
    meta = content["ingestion_metadata"]
    assert meta["endpoint"] == "events"
    assert meta["media_id"] == "abc"
    assert meta["ingest_date"] == "2026-05-21"
    assert meta["ingest_timestamp"] == "2026-05-21T14:30:00+00:00"
    assert meta["record_count"] == 2


def test_write_landing_same_day_rerun_overwrites(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, tzinfo=timezone.utc)
    write_landing("by_date", "abc", [{"date": "2026-05-20"}], landing_root=tmp_path, ingest_time=ts)
    path = write_landing(
        "by_date", "abc", [{"date": "2026-05-21"}], landing_root=tmp_path, ingest_time=ts
    )

    assert list(path.parent.iterdir()) == [path]  # one file — re-run overwrote
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["records"] == [{"date": "2026-05-21"}]


def test_write_landing_empty_records(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, tzinfo=timezone.utc)
    path = write_landing("events", "abc", [], landing_root=tmp_path, ingest_time=ts)

    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["records"] == []
    assert content["ingestion_metadata"]["record_count"] == 0
