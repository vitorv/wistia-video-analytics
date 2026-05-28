"""Glue 5.0 ETL job: Silver Parquet -> Gold star schema (Parquet).

Executed by Glue, not imported. Reads from ``s3://<DATALAKE_BUCKET>/silver/``
and writes to ``s3://<DATALAKE_BUCKET>/gold/``. Triggered by the conditional
``silver-to-gold`` trigger in the Glue Workflow.
"""

import sys


def main() -> None:
    import os
    import zipfile

    import boto3
    from awsglue.context import GlueContext  # type: ignore[import-not-found]
    from awsglue.utils import getResolvedOptions  # type: ignore[import-not-found]
    from pyspark.context import SparkContext

    args = getResolvedOptions(sys.argv, ["DATALAKE_BUCKET", "TRANSFORMS_ZIP_S3"])
    bucket = args["DATALAKE_BUCKET"]

    s3_uri = args["TRANSFORMS_ZIP_S3"]
    src_bucket, src_key = s3_uri.removeprefix("s3://").split("/", 1)
    local_zip = "/tmp/transforms.zip"
    extract_dir = "/tmp/transforms_src"
    boto3.client("s3").download_file(src_bucket, src_key, local_zip)
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(local_zip) as zf:
        zf.extractall(extract_dir)
    sys.path.insert(0, extract_dir)

    sc = SparkContext.getOrCreate()
    sc.addPyFile(s3_uri)
    spark = GlueContext(sc).spark_session
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    from src.common.logging import configure_logging
    from src.transforms.gold import run_gold

    configure_logging()
    counts = run_gold(
        spark,
        silver_root=f"s3://{bucket}/silver",
        gold_root=f"s3://{bucket}/gold",
    )
    print(f"gold counts: {counts}")


if __name__ == "__main__":
    main()
