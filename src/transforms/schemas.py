"""Explicit Spark schemas for the landing-zone JSON envelopes.

Each landing file is one envelope written by ``src.ingestion.landing.write_landing``:
an ``ingestion_metadata`` header plus a ``records`` array of raw API records.
Declaring the schema explicitly — rather than letting Spark infer it — keeps the
Bronze read fast, deterministic, and resilient to empty ``records`` arrays.

Only the fields the Gold model consumes are declared; unused API fields (nested
heatmap / thumbnail / user-agent objects) are intentionally dropped on read.
"""

from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

# Envelope header stamped by the ingestion landing writer.
INGESTION_METADATA_SCHEMA = StructType(
    [
        StructField("endpoint", StringType()),
        StructField("media_id", StringType()),
        StructField("ingest_timestamp", StringType()),
        StructField("ingest_date", StringType()),
        StructField("record_count", LongType()),
    ]
)

# --- per-endpoint raw record schemas -------------------------------------

EVENTS_RECORD_SCHEMA = StructType(
    [
        StructField("received_at", StringType()),
        StructField("event_key", StringType()),
        StructField("ip", StringType()),
        StructField("country", StringType()),
        StructField("percent_viewed", DoubleType()),
        StructField("conversion_type", StringType()),
        StructField("visitor_key", StringType()),
        StructField("media_id", StringType()),
        StructField("media_name", StringType()),
        StructField("media_url", StringType()),
    ]
)

BY_DATE_RECORD_SCHEMA = StructType(
    [
        StructField("date", StringType()),
        StructField("load_count", LongType()),
        StructField("play_count", LongType()),
        StructField("hours_watched", DoubleType()),
    ]
)

MEDIA_METADATA_RECORD_SCHEMA = StructType(
    [
        StructField("hashed_id", StringType()),
        StructField("name", StringType()),
        StructField("created", StringType()),
    ]
)


def envelope_schema(record_schema: StructType) -> StructType:
    """Return the landing-envelope schema wrapping ``record_schema``."""
    return StructType(
        [
            StructField("ingestion_metadata", INGESTION_METADATA_SCHEMA),
            StructField("records", ArrayType(record_schema)),
        ]
    )


# Ready-made envelope schemas keyed by endpoint name (see transforms.config).
ENVELOPE_SCHEMAS = {
    "events": envelope_schema(EVENTS_RECORD_SCHEMA),
    "by_date": envelope_schema(BY_DATE_RECORD_SCHEMA),
    "media_metadata": envelope_schema(MEDIA_METADATA_RECORD_SCHEMA),
}
