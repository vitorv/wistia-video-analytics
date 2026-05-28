"""Glue 5.0 ETL job: Bronze Parquet -> Silver Parquet.

Executed by Glue, not imported. Reads from ``s3://<DATALAKE_BUCKET>/bronze/``
and writes to ``s3://<DATALAKE_BUCKET>/silver/``. Triggered by the
conditional ``bronze-to-silver`` trigger in the Glue Workflow.
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
    from src.transforms.silver import run_silver

    configure_logging()
    counts = run_silver(
        spark,
        bronze_root=f"s3://{bucket}/bronze",
        silver_root=f"s3://{bucket}/silver",
    )
    print(f"silver counts: {counts}")


if __name__ == "__main__":
    main()
