"""Bronze transform: landing-zone JSON -> Bronze Parquet.

Bronze is the first medallion layer. It reads the raw landing envelopes, explodes
them into one row per API record, applies the explicit schema, and stamps each
row with ingestion lineage. No cleaning, typing, or de-duplication happens here —
Bronze preserves the raw values; Silver does the cleaning.
"""

import logging
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src.transforms import config
from src.transforms.schemas import ENVELOPE_SCHEMAS

logger = logging.getLogger(__name__)


def to_bronze(envelopes: DataFrame) -> DataFrame:
    """Flatten landing envelopes into one Bronze row per raw record.

    Each input row is one landing envelope (an ``ingestion_metadata`` header plus
    a ``records`` array). The records are exploded to one row each, carrying two
    lineage columns copied from the header: ``ingest_timestamp`` and
    ``ingest_date``. Envelopes with an empty ``records`` array contribute no rows.
    """
    return envelopes.select(
        F.col("ingestion_metadata.ingest_timestamp").alias("ingest_timestamp"),
        F.col("ingestion_metadata.ingest_date").alias("ingest_date"),
        F.explode("records").alias("record"),
    ).select("record.*", "ingest_timestamp", "ingest_date")


def read_landing(spark: SparkSession, endpoint: str, landing_root: Path) -> DataFrame:
    """Read every landing JSON file for ``endpoint`` into an envelope DataFrame.

    ``recursiveFileLookup`` walks the ``media_id=`` / ``ingest_date=`` partition
    directories without treating their names as Spark partition columns; the
    explicit envelope schema keeps the read fast and stable across empty pulls.
    """
    path = str(landing_root / endpoint)
    return (
        spark.read.schema(ENVELOPE_SCHEMAS[endpoint])
        .option("multiLine", "true")
        .option("recursiveFileLookup", "true")
        .json(path)
    )


def write_bronze(df: DataFrame, endpoint: str, bronze_root: Path) -> None:
    """Write a Bronze DataFrame to ``bronze_root/endpoint`` as Parquet (overwrite)."""
    path = str(bronze_root / endpoint)
    df.write.mode("overwrite").parquet(path)
    logger.info("bronze written endpoint=%s path=%s", endpoint, path)


def run_bronze(
    spark: SparkSession,
    *,
    landing_root: Path = config.LANDING_ROOT,
    bronze_root: Path = config.BRONZE_ROOT,
) -> dict[str, int]:
    """Build the Bronze layer for every endpoint; return per-endpoint row counts."""
    counts: dict[str, int] = {}
    for endpoint in config.ENDPOINTS:
        bronze = to_bronze(read_landing(spark, endpoint, landing_root)).cache()
        counts[endpoint] = bronze.count()
        write_bronze(bronze, endpoint, bronze_root)
        bronze.unpersist()
    logger.info("bronze run complete counts=%s", counts)
    return counts
