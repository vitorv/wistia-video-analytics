"""Local entry point — ``python -m src.transforms``.

Chains Bronze -> Silver -> Gold over the landing zone in one pass, mirroring
the structure of ``python -m src.ingestion``. The Spark session is built once
and stopped in a ``finally`` so it tears down cleanly even on transform errors.
"""

import logging
import sys

from src.common.logging import configure_logging
from src.transforms.bronze import run_bronze
from src.transforms.gold import run_gold
from src.transforms.silver import run_silver
from src.transforms.spark import build_spark

logger = logging.getLogger("src.transforms")


def main() -> int:
    """Build Spark, run Bronze -> Silver -> Gold; return a process exit code."""
    configure_logging()
    spark = build_spark()
    try:
        bronze_counts = run_bronze(spark)
        silver_counts = run_silver(spark)
        gold_counts = run_gold(spark)
    finally:
        spark.stop()
    logger.info(
        "transform run complete bronze=%s silver=%s gold=%s",
        bronze_counts,
        silver_counts,
        gold_counts,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
