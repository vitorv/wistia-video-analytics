"""Tests for the Gold transform."""

from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pyspark.sql import Row, SparkSession

from src.ingestion.landing import write_landing
from src.transforms.bronze import run_bronze
from src.transforms.gold import (
    run_gold,
    to_dim_media,
    to_dim_visitor,
    to_fact_media_engagement,
)
from src.transforms.silver import run_silver

UTC = timezone.utc


def _silver_event(**overrides: Any) -> dict[str, Any]:
    """Return a Silver-shaped events row with sensible defaults."""
    row: dict[str, Any] = {
        "event_key": "evt_1",
        "visitor_key": "vis_1",
        "media_id": "m1",
        "media_name": "Sample",
        "media_url": "https://example.com/m1",
        "received_at": datetime(2026, 5, 19, 14, 0, 0, tzinfo=UTC),
        "ip": "192.0.2.10",
        "country": "ZZ",
        "percent_viewed": 0.5,
    }
    row.update(overrides)
    return row


def test_to_dim_media_derives_channel_from_name(spark: SparkSession) -> None:
    media = spark.createDataFrame(
        [
            Row(
                media_id="m1",
                name="Sample VSL Youtube Paid Ads",
                created=datetime(2025, 1, 13, tzinfo=UTC),
            ),
            Row(
                media_id="m2",
                name="Brand Awareness Facebook Q3",
                created=datetime(2025, 2, 1, tzinfo=UTC),
            ),
            Row(
                media_id="m3",
                name="Untagged Video",
                created=datetime(2025, 3, 1, tzinfo=UTC),
            ),
        ]
    )
    events_rows = [
        _silver_event(media_id="m1"),
        _silver_event(media_id="m2", media_url="https://example.com/m2"),
    ]
    events = spark.createDataFrame([Row(**r) for r in events_rows])

    dim = to_dim_media(media, events).orderBy("media_id").collect()

    assert [r["channel"] for r in dim] == ["Youtube", "Facebook", "Unknown"]
    assert dim[0]["url"] == "https://example.com/m1"
    # m3 has no events -> url null after the left join.
    assert dim[2]["url"] is None


def test_to_dim_visitor_most_recent_event_wins(spark: SparkSession) -> None:
    # D1 / ADR-005: a roaming visitor's newest event supplies ip + country.
    rows = [
        _silver_event(
            visitor_key="v_1",
            received_at=datetime(2026, 5, 19, 8, 0, 0, tzinfo=UTC),
            ip="10.0.0.1",
            country="US",
        ),
        _silver_event(
            visitor_key="v_1",
            received_at=datetime(2026, 5, 19, 20, 0, 0, tzinfo=UTC),
            ip="10.0.0.2",
            country="DE",
        ),
        _silver_event(
            visitor_key="v_2",
            received_at=datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC),
            ip="10.0.0.3",
            country="GB",
        ),
    ]
    events = spark.createDataFrame([Row(**r) for r in rows])

    dim = to_dim_visitor(events).orderBy("visitor_id").collect()

    assert len(dim) == 2
    assert dim[0]["visitor_id"] == "v_1"
    assert dim[0]["ip_address"] == "10.0.0.2"  # the 20:00 event wins
    assert dim[0]["country"] == "DE"
    assert dim[1]["visitor_id"] == "v_2"
    assert dim[1]["country"] == "GB"


def test_to_fact_media_engagement_aggregates_and_joins(spark: SparkSession) -> None:
    rows = [
        _silver_event(
            visitor_key="v_1",
            percent_viewed=0.8,
            received_at=datetime(2026, 5, 19, 9, 0, 0, tzinfo=UTC),
        ),
        _silver_event(
            visitor_key="v_1",
            percent_viewed=0.4,
            received_at=datetime(2026, 5, 19, 15, 0, 0, tzinfo=UTC),
        ),
        _silver_event(
            visitor_key="v_2",
            percent_viewed=0.5,
            received_at=datetime(2026, 5, 19, 10, 0, 0, tzinfo=UTC),
        ),
    ]
    events = spark.createDataFrame([Row(**r) for r in rows])
    by_date = spark.createDataFrame(
        [
            Row(
                media_id="m1",
                date=date(2026, 5, 19),
                load_count=10,
                play_count=8,
                hours_watched=1.5,
            ),
        ]
    )

    fact = to_fact_media_engagement(events, by_date).orderBy("visitor_id").collect()

    assert len(fact) == 2
    # v_1 saw 2 events that day -> play_count=2, watched_percent=(0.8+0.4)/2=0.6
    assert fact[0]["visitor_id"] == "v_1"
    assert fact[0]["play_count"] == 2
    assert fact[0]["watched_percent"] == pytest.approx(0.6)
    # by_date denormalized onto every visitor row for the media+date
    assert fact[0]["play_rate"] == pytest.approx(0.8)  # 8/10
    assert fact[0]["total_watch_time"] == pytest.approx(1.5)
    assert fact[1]["visitor_id"] == "v_2"
    assert fact[1]["play_count"] == 1


def test_to_fact_media_engagement_left_joins_by_date(spark: SparkSession) -> None:
    # When by_date has no matching media+date (e.g. D3 filtered it), the
    # fact row still appears but play_rate / total_watch_time are null.
    rows = [
        _silver_event(
            visitor_key="v_1",
            received_at=datetime(2026, 5, 19, 9, 0, 0, tzinfo=UTC),
        ),
    ]
    events = spark.createDataFrame([Row(**r) for r in rows])
    by_date = spark.createDataFrame(
        [
            Row(
                media_id="other_media",
                date=date(2026, 5, 19),
                load_count=10,
                play_count=8,
                hours_watched=1.5,
            ),
        ]
    )

    fact = to_fact_media_engagement(events, by_date).collect()

    assert len(fact) == 1
    assert fact[0]["play_rate"] is None
    assert fact[0]["total_watch_time"] is None


def test_run_gold_end_to_end(
    spark: SparkSession,
    load_fixture: Callable[[str], Any],
    tmp_path: Path,
) -> None:
    landing = tmp_path / "landing"
    bronze_root = tmp_path / "bronze"
    silver_root = tmp_path / "silver"
    gold_root = tmp_path / "gold"
    write_landing("events", "gskhw4w4lm", load_fixture("events_page.json"), landing_root=landing)
    write_landing("by_date", "gskhw4w4lm", load_fixture("by_date.json"), landing_root=landing)
    write_landing(
        "media_metadata",
        "gskhw4w4lm",
        [load_fixture("media_metadata.json")],
        landing_root=landing,
    )
    run_bronze(spark, landing_root=landing, bronze_root=bronze_root)
    run_silver(spark, bronze_root=bronze_root, silver_root=silver_root)

    counts = run_gold(spark, silver_root=silver_root, gold_root=gold_root)

    # dim_media: 1 media (gskhw4w4lm)
    # dim_visitor: 2 distinct visitors in the fixture
    # fact: 2 (media, visitor, 2026-05-19) groups (vis_001 had 2 events; vis_002 had 1)
    assert counts == {"dim_media": 1, "dim_visitor": 2, "fact_media_engagement": 2}

    # Channel derivation lands; media name comes from media_metadata.
    dim_media = spark.read.parquet(str(gold_root / "dim_media")).first()
    assert dim_media is not None
    assert dim_media["channel"] == "Youtube"
    assert dim_media["title"] == "Sample VSL Youtube Paid Ads"

    # Fact PK uniqueness: (media_id, visitor_id, date) is unique.
    fact = spark.read.parquet(str(gold_root / "fact_media_engagement"))
    pk_count = fact.select("media_id", "visitor_id", "date").distinct().count()
    assert pk_count == fact.count() == 2
