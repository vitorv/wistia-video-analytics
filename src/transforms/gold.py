"""Gold transform: Silver Parquet -> Gold star schema (Parquet).

The Gold layer is a star schema (per ADR-002):

- ``dim_media``  one row per media; PK ``media_id``. Derives ``channel`` from
                 the media name; sources ``url`` from events (the only endpoint
                 that returns the public media URL).
- ``dim_visitor``  one row per visitor; PK ``visitor_id``. **D1 / ADR-005**:
                   most-recent event wins for ``ip_address`` and ``country``.
- ``fact_media_engagement``  one row per ``media_id + visitor_id + date``.
                             ``play_count = count(*)`` per group;
                             ``watched_percent = avg(percent_viewed)`` per
                             group; ``play_rate`` and ``total_watch_time`` come
                             from by_date and are denormalized at the
                             media+day grain (per ADR-002).

Each transform is a pure ``DataFrame -> DataFrame`` function so a Phase-3
Glue job imports it unchanged.
"""

import logging
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from src.transforms import config

logger = logging.getLogger(__name__)


def to_dim_media(media_metadata: DataFrame, events: DataFrame) -> DataFrame:
    """Build ``dim_media`` from Silver media_metadata + events.

    ``url`` is sourced from events (the only endpoint that returns it) via a
    left join, so a media without events still appears in ``dim_media`` with a
    null url. ``channel`` is derived from the media name with a simple lower /
    contains match.
    """
    urls = events.groupBy("media_id").agg(
        F.first("media_url", ignorenulls=True).alias("url"),
    )
    return (
        media_metadata.join(urls, on="media_id", how="left")
        .withColumn(
            "channel",
            F.when(F.lower(F.col("name")).contains("youtube"), F.lit("Youtube"))
            .when(F.lower(F.col("name")).contains("facebook"), F.lit("Facebook"))
            .otherwise(F.lit("Unknown")),
        )
        .select(
            F.col("media_id"),
            F.col("name").alias("title"),
            F.col("url"),
            F.col("channel"),
            F.col("created").alias("created_at"),
        )
    )


def to_dim_visitor(events: DataFrame) -> DataFrame:
    """Build ``dim_visitor`` — D1 / ADR-005: most-recent event per visitor wins.

    A visitor that appears across many events with different ip / country
    values (mobile roaming) gets the values from their newest event by
    ``received_at``.
    """
    window = Window.partitionBy("visitor_key").orderBy(F.col("received_at").desc())
    return (
        events.withColumn("_rn", F.row_number().over(window))
        .where(F.col("_rn") == 1)
        .select(
            F.col("visitor_key").alias("visitor_id"),
            F.col("ip").alias("ip_address"),
            F.col("country"),
        )
    )


def to_fact_media_engagement(events: DataFrame, by_date: DataFrame) -> DataFrame:
    """Build ``fact_media_engagement`` at the visitor x media x date grain.

    ``play_count`` and ``watched_percent`` are per-(visitor, media, day)
    aggregates of Events. ``play_rate`` and ``total_watch_time`` come from the
    media-level daily ``by_date`` data (left-joined on ``media_id + date``)
    and are intentionally denormalized — the same media+day values are
    repeated across every visitor row for that media+date (ADR-002).
    """
    fact = (
        events.withColumn("date", F.to_date("received_at"))
        .groupBy("media_id", "visitor_key", "date")
        .agg(
            F.count(F.lit(1)).alias("play_count"),
            F.avg("percent_viewed").alias("watched_percent"),
        )
        .withColumnRenamed("visitor_key", "visitor_id")
    )
    media_daily = by_date.select(
        "media_id",
        "date",
        (F.col("play_count") / F.col("load_count")).alias("play_rate"),
        F.col("hours_watched").alias("total_watch_time"),
    )
    return fact.join(media_daily, on=["media_id", "date"], how="left").select(
        "media_id",
        "visitor_id",
        "date",
        "play_count",
        "watched_percent",
        "play_rate",
        "total_watch_time",
    )


def read_silver(spark: SparkSession, endpoint: str, silver_root: str | Path) -> DataFrame:
    """Read Silver Parquet for ``endpoint``. ``silver_root`` may be a local path or s3:// URI."""
    return spark.read.parquet(config.join_layer_path(silver_root, endpoint))


def write_gold(df: DataFrame, table: str, gold_root: str | Path) -> None:
    """Write a Gold DataFrame to ``gold_root/table`` as Parquet (overwrite)."""
    path = config.join_layer_path(gold_root, table)
    df.write.mode("overwrite").parquet(path)
    logger.info("gold written table=%s path=%s", table, path)


def run_gold(
    spark: SparkSession,
    *,
    silver_root: str | Path = config.SILVER_ROOT,
    gold_root: str | Path = config.GOLD_ROOT,
) -> dict[str, int]:
    """Build the Gold star schema; return per-table row counts."""
    silver_events = read_silver(spark, config.EVENTS, silver_root).cache()
    silver_by_date = read_silver(spark, config.BY_DATE, silver_root)
    silver_media_meta = read_silver(spark, config.MEDIA_METADATA, silver_root)

    tables = {
        config.DIM_MEDIA: to_dim_media(silver_media_meta, silver_events),
        config.DIM_VISITOR: to_dim_visitor(silver_events),
        config.FACT_MEDIA_ENGAGEMENT: to_fact_media_engagement(silver_events, silver_by_date),
    }
    counts: dict[str, int] = {}
    for table, df in tables.items():
        gold = df.cache()
        counts[table] = gold.count()
        write_gold(gold, table, gold_root)
        gold.unpersist()
    silver_events.unpersist()
    logger.info("gold run complete counts=%s", counts)
    return counts
