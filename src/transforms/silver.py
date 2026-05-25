"""Silver transform: Bronze Parquet -> Silver Parquet.

Silver cleans, types, deduplicates, and filters the Bronze data into the shape
the Gold star schema consumes:

- ``events``         cast timestamps; drop non-play events (``conversion_type``
                     non-empty; per ADR-002); deduplicate by ``event_key``
                     keeping the latest ingestion.
- ``by_date``        cast dates; drop zero-activity rows (``load_count = 0``;
                     ADR-006); deduplicate by ``media_id + date``.
- ``media_metadata`` rename ``hashed_id`` -> ``media_id``; cast ``created`` to
                     timestamp; deduplicate by ``media_id``.

Each transform is a pure ``DataFrame -> DataFrame`` function so a Phase-3 Glue
job can import it unchanged. Dedup ordering uses the Bronze lineage column
``ingest_timestamp`` (an ISO-8601 string written by ``src.ingestion.landing``;
lexical sort matches chronological order for that format).
"""

import logging
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from src.transforms import config

logger = logging.getLogger(__name__)


def _dedupe_keep_latest(df: DataFrame, key_cols: list[str]) -> DataFrame:
    """Return rows with the latest ``ingest_timestamp`` per ``key_cols``."""
    window = Window.partitionBy(*key_cols).orderBy(F.col("ingest_timestamp").desc())
    return df.withColumn("_rn", F.row_number().over(window)).where(F.col("_rn") == 1).drop("_rn")


def to_silver_events(bronze: DataFrame) -> DataFrame:
    """Bronze events -> Silver events: drop non-plays, cast timestamps, dedupe."""
    return (
        bronze.where(
            F.col("event_key").isNotNull()
            & F.col("visitor_key").isNotNull()
            & F.col("media_id").isNotNull()
            & F.col("received_at").isNotNull()
        )
        # ADR-002 D2: keep only play events (conversion_type empty or null).
        .where(F.col("conversion_type").isNull() | (F.col("conversion_type") == ""))
        .withColumn("received_at", F.to_timestamp("received_at"))
        .transform(lambda d: _dedupe_keep_latest(d, ["event_key"]))
        .select(
            "event_key",
            "visitor_key",
            "media_id",
            "media_name",
            "media_url",
            "received_at",
            "ip",
            "country",
            "percent_viewed",
        )
    )


def to_silver_by_date(bronze: DataFrame) -> DataFrame:
    """Bronze by_date -> Silver by_date: drop zero-activity, cast date, dedupe."""
    return (
        bronze.where(
            F.col("media_id").isNotNull()
            & F.col("date").isNotNull()
            & F.col("load_count").isNotNull()
        )
        # ADR-006 D3: drop days where the media had no engagement.
        .where(F.col("load_count") > 0)
        .withColumn("date", F.to_date("date"))
        .transform(lambda d: _dedupe_keep_latest(d, ["media_id", "date"]))
        .select("media_id", "date", "load_count", "play_count", "hours_watched")
    )


def to_silver_media_metadata(bronze: DataFrame) -> DataFrame:
    """Bronze media_metadata -> Silver media_metadata: rename PK, cast, dedupe."""
    return (
        bronze.drop("media_id")  # lineage media_id duplicates the record's hashed_id
        .withColumnRenamed("hashed_id", "media_id")
        .where(F.col("media_id").isNotNull())
        .withColumn("created", F.to_timestamp("created"))
        .transform(lambda d: _dedupe_keep_latest(d, ["media_id"]))
        .select("media_id", "name", "created")
    )


def read_bronze(spark: SparkSession, endpoint: str, bronze_root: Path) -> DataFrame:
    """Read Bronze Parquet for ``endpoint``."""
    return spark.read.parquet(str(bronze_root / endpoint))


def write_silver(df: DataFrame, endpoint: str, silver_root: Path) -> None:
    """Write a Silver DataFrame to ``silver_root/endpoint`` as Parquet (overwrite)."""
    path = str(silver_root / endpoint)
    df.write.mode("overwrite").parquet(path)
    logger.info("silver written endpoint=%s path=%s", endpoint, path)


_TRANSFORMS = {
    config.EVENTS: to_silver_events,
    config.BY_DATE: to_silver_by_date,
    config.MEDIA_METADATA: to_silver_media_metadata,
}


def run_silver(
    spark: SparkSession,
    *,
    bronze_root: Path = config.BRONZE_ROOT,
    silver_root: Path = config.SILVER_ROOT,
) -> dict[str, int]:
    """Build the Silver layer for every endpoint; return per-endpoint row counts."""
    counts: dict[str, int] = {}
    for endpoint, transform in _TRANSFORMS.items():
        silver = transform(read_bronze(spark, endpoint, bronze_root)).cache()
        counts[endpoint] = silver.count()
        write_silver(silver, endpoint, silver_root)
        silver.unpersist()
    logger.info("silver run complete counts=%s", counts)
    return counts
