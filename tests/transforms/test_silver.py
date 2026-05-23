"""Tests for the Silver transform."""

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pyspark.sql import Row, SparkSession

from src.ingestion.landing import write_landing
from src.transforms.bronze import run_bronze
from src.transforms.silver import (
    run_silver,
    to_silver_by_date,
    to_silver_events,
    to_silver_media_metadata,
)


def _bronze_event(**overrides: Any) -> dict[str, Any]:
    """Return a Bronze-shaped events row with sensible defaults."""
    row: dict[str, Any] = {
        "received_at": "2026-05-19T14:00:00.000Z",
        "event_key": "evt_1",
        "ip": "192.0.2.10",
        "country": "ZZ",
        "percent_viewed": 0.5,
        "conversion_type": "",
        "visitor_key": "vis_1",
        "media_name": "Sample",
        "media_url": "https://example.com/m1",
        "ingest_timestamp": "2026-05-22T10:00:00+00:00",
        "ingest_date": "2026-05-22",
        "media_id": "m1",
    }
    row.update(overrides)
    return row


def test_to_silver_events_dedupes_filters_and_casts(spark: SparkSession) -> None:
    rows = [
        _bronze_event(
            event_key="evt_1",
            ingest_timestamp="2026-05-22T10:00:00+00:00",
            percent_viewed=0.3,
        ),
        _bronze_event(
            event_key="evt_1",
            ingest_timestamp="2026-05-23T10:00:00+00:00",
            percent_viewed=0.9,
        ),
        _bronze_event(event_key="evt_2", conversion_type="form-submit"),  # non-play -> dropped
        _bronze_event(event_key=None),  # null PK -> dropped
    ]

    silver = to_silver_events(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 1
    row = silver.first()
    assert row is not None
    assert row["event_key"] == "evt_1"
    assert row["percent_viewed"] == 0.9  # the latest ingest wins
    assert isinstance(row["received_at"], datetime)
    assert "conversion_type" not in silver.columns
    assert "ingest_timestamp" not in silver.columns


def test_to_silver_by_date_drops_zero_activity_and_dedupes(spark: SparkSession) -> None:
    rows = [
        # zero-activity day -> dropped (D3 / ADR-006)
        {
            "media_id": "m1",
            "date": "2026-05-18",
            "load_count": 0,
            "play_count": 0,
            "hours_watched": 0.0,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
        # earlier ingest for 2026-05-19 -> superseded
        {
            "media_id": "m1",
            "date": "2026-05-19",
            "load_count": 12,
            "play_count": 8,
            "hours_watched": 0.95,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
        # later ingest for the same day -> wins
        {
            "media_id": "m1",
            "date": "2026-05-19",
            "load_count": 12,
            "play_count": 8,
            "hours_watched": 1.10,
            "ingest_timestamp": "2026-05-23T10:00:00+00:00",
            "ingest_date": "2026-05-23",
        },
    ]

    silver = to_silver_by_date(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 1
    row = silver.first()
    assert row is not None
    assert row["date"] == date(2026, 5, 19)
    assert row["hours_watched"] == 1.10


def test_to_silver_media_metadata_renames_and_dedupes(spark: SparkSession) -> None:
    rows = [
        {
            "hashed_id": "m1",
            "name": "Sample VSL Youtube Paid Ads",
            "created": "2025-01-13T00:31:55+00:00",
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
            "media_id": "m1",
        },
        {
            "hashed_id": "m1",
            "name": "Renamed Title",
            "created": "2025-01-13T00:31:55+00:00",
            "ingest_timestamp": "2026-05-23T10:00:00+00:00",
            "ingest_date": "2026-05-23",
            "media_id": "m1",
        },
    ]

    silver = to_silver_media_metadata(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 1
    row = silver.first()
    assert row is not None
    assert row["media_id"] == "m1"
    assert row["name"] == "Renamed Title"
    assert set(silver.columns) == {"media_id", "name", "created"}


def test_run_silver_end_to_end(
    spark: SparkSession,
    load_fixture: Callable[[str], Any],
    tmp_path: Path,
) -> None:
    landing = tmp_path / "landing"
    bronze_root = tmp_path / "bronze"
    silver_root = tmp_path / "silver"
    write_landing("events", "gskhw4w4lm", load_fixture("events_page.json"), landing_root=landing)
    write_landing("by_date", "gskhw4w4lm", load_fixture("by_date.json"), landing_root=landing)
    write_landing(
        "media_metadata",
        "gskhw4w4lm",
        [load_fixture("media_metadata.json")],
        landing_root=landing,
    )
    run_bronze(spark, landing_root=landing, bronze_root=bronze_root)

    counts = run_silver(spark, bronze_root=bronze_root, silver_root=silver_root)

    # events fixture: 3 play events, distinct keys -> 3
    # by_date fixture: 3 days, one zero-activity -> 2
    # media_metadata fixture: 1 -> 1
    assert counts == {"events": 3, "by_date": 2, "media_metadata": 1}
    # by_date Silver carries media_id from Bronze lineage (regression guard for
    # the design oversight discovered during WS4).
    by_date_silver = spark.read.parquet(str(silver_root / "by_date"))
    assert "media_id" in by_date_silver.columns
    assert {r["media_id"] for r in by_date_silver.collect()} == {"gskhw4w4lm"}


def test_to_silver_events_filters_all_null_pk_fields(spark: SparkSession) -> None:
    # Each PK-relevant column must individually drop rows when null —
    # exercising all four arms of the AND filter (the original test only
    # covered event_key=None).
    rows = [
        _bronze_event(event_key="evt_keep"),
        _bronze_event(event_key=None),
        _bronze_event(visitor_key=None),
        _bronze_event(media_id=None),
        _bronze_event(received_at=None),
    ]

    silver = to_silver_events(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 1
    row = silver.first()
    assert row is not None
    assert row["event_key"] == "evt_keep"


def test_to_silver_events_keeps_play_events_with_null_conversion_type(
    spark: SparkSession,
) -> None:
    # The API may return null for conversion_type (not just ""); both forms
    # mean "play event" and must be kept.
    rows = [
        _bronze_event(event_key="evt_a", conversion_type=None),
        _bronze_event(event_key="evt_b", conversion_type=""),
        _bronze_event(event_key="evt_c", conversion_type="form-submit"),
    ]

    silver = to_silver_events(spark.createDataFrame([Row(**r) for r in rows]))

    assert {r["event_key"] for r in silver.collect()} == {"evt_a", "evt_b"}


def test_to_silver_by_date_partitions_dedup_by_media_id(spark: SparkSession) -> None:
    # Dedup window is media_id + date — two media on the same date must both
    # survive (regression guard against a partitionBy that drops media_id).
    rows = [
        {
            "media_id": "m1",
            "date": "2026-05-19",
            "load_count": 12,
            "play_count": 8,
            "hours_watched": 0.95,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
        {
            "media_id": "m2",
            "date": "2026-05-19",
            "load_count": 5,
            "play_count": 3,
            "hours_watched": 0.40,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
    ]

    silver = to_silver_by_date(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 2
    assert {r["media_id"] for r in silver.collect()} == {"m1", "m2"}


def test_to_silver_by_date_load_count_boundary(spark: SparkSession) -> None:
    # Boundary check around the D3 / ADR-006 filter:
    # load_count == 0 drops, load_count == 1 keeps.
    rows = [
        {
            "media_id": "m1",
            "date": "2026-05-18",
            "load_count": 0,
            "play_count": 0,
            "hours_watched": 0.0,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
        {
            "media_id": "m1",
            "date": "2026-05-19",
            "load_count": 1,
            "play_count": 1,
            "hours_watched": 0.05,
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
        },
    ]

    silver = to_silver_by_date(spark.createDataFrame([Row(**r) for r in rows]))

    assert silver.count() == 1
    row = silver.first()
    assert row is not None
    assert row["load_count"] == 1
