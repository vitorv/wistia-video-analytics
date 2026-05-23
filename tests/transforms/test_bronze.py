"""Tests for the Bronze transform."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyspark.sql import SparkSession

from src.ingestion.landing import write_landing
from src.transforms.bronze import run_bronze, to_bronze
from src.transforms.schemas import ENVELOPE_SCHEMAS

_EVENT = {
    "received_at": "2026-05-19T14:00:00.000Z",
    "event_key": "evt_1",
    "ip": "192.0.2.10",
    "country": "ZZ",
    "percent_viewed": 0.5,
    "conversion_type": "",
    "visitor_key": "vis_1",
    "media_id": "m1",
    "media_name": "Sample",
    "media_url": "https://example.com/m1",
}


def _envelope(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an events-shaped landing envelope around ``records``."""
    return {
        "ingestion_metadata": {
            "endpoint": "events",
            "media_id": "m1",
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
            "record_count": len(records),
        },
        "records": records,
    }


def test_to_bronze_explodes_records_with_lineage(spark: SparkSession) -> None:
    df = spark.createDataFrame([_envelope([_EVENT, _EVENT])], schema=ENVELOPE_SCHEMAS["events"])

    bronze = to_bronze(df)

    assert bronze.count() == 2
    row = bronze.first()
    assert row is not None
    assert row["event_key"] == "evt_1"
    assert row["ingest_timestamp"] == "2026-05-22T10:00:00+00:00"
    assert row["ingest_date"] == "2026-05-22"


def test_to_bronze_empty_records_yields_no_rows(spark: SparkSession) -> None:
    df = spark.createDataFrame([_envelope([])], schema=ENVELOPE_SCHEMAS["events"])

    assert to_bronze(df).count() == 0


def test_run_bronze_end_to_end(
    spark: SparkSession,
    load_fixture: Callable[[str], Any],
    tmp_path: Path,
) -> None:
    landing = tmp_path / "landing"
    bronze = tmp_path / "bronze"
    write_landing("events", "gskhw4w4lm", load_fixture("events_page.json"), landing_root=landing)
    write_landing("by_date", "gskhw4w4lm", load_fixture("by_date.json"), landing_root=landing)
    write_landing(
        "media_metadata",
        "gskhw4w4lm",
        [load_fixture("media_metadata.json")],
        landing_root=landing,
    )

    counts = run_bronze(spark, landing_root=landing, bronze_root=bronze)

    assert counts == {"events": 3, "by_date": 3, "media_metadata": 1}
    events = spark.read.parquet(str(bronze / "events"))
    assert events.count() == 3
    assert {"ingest_timestamp", "ingest_date"}.issubset(set(events.columns))
    media_ids = {r["media_id"] for r in events.select("media_id").collect()}
    assert media_ids == {"gskhw4w4lm"}


def test_to_bronze_by_date_carries_media_id_from_metadata(spark: SparkSession) -> None:
    # by_date records carry no media_id in the API response; Bronze must source
    # it from ingestion_metadata.media_id so the column is consistent across
    # endpoints and by_date rows still have the join key Gold needs.
    # Regression guard for the design oversight discovered during WS4.
    envelope = {
        "ingestion_metadata": {
            "endpoint": "by_date",
            "media_id": "from_metadata",
            "ingest_timestamp": "2026-05-22T10:00:00+00:00",
            "ingest_date": "2026-05-22",
            "record_count": 1,
        },
        "records": [
            {"date": "2026-05-19", "load_count": 12, "play_count": 8, "hours_watched": 0.95},
        ],
    }
    df = spark.createDataFrame([envelope], schema=ENVELOPE_SCHEMAS["by_date"])

    bronze = to_bronze(df)

    assert "media_id" in bronze.columns
    row = bronze.first()
    assert row is not None
    assert row["media_id"] == "from_metadata"
