"""Glue 5.0 ETL job: landing JSON -> Bronze Parquet.

Executed by Glue, not imported. Reads from ``s3://<DATALAKE_BUCKET>/landing/``
and writes to ``s3://<DATALAKE_BUCKET>/bronze/``.

The pure ``run_bronze`` function lives in ``src.transforms.bronze``, shipped
via ``transforms.zip``. Glue's ``--extra-py-files`` doesn't reliably make a
zip importable from the driver in Glue 5.0, so we download the zip with
boto3, extract it to a directory, and add that directory to ``sys.path``.
All ``src.*`` imports are deferred to inside ``main()`` so they happen after
the extraction completes.

Note: ``transforms.zip`` must have **forward-slash** entry names — Python's
``zipfile`` module produces those; PowerShell's ``Compress-Archive`` does
not (it embeds Windows-style backslashes). ``infra/scripts/package-transforms.ps1``
shells out to Python's ``zipfile`` for this reason.
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
    from src.transforms.bronze import run_bronze

    configure_logging()
    counts = run_bronze(
        spark,
        landing_root=f"s3://{bucket}/landing",
        bronze_root=f"s3://{bucket}/bronze",
    )
    print(f"bronze counts: {counts}")


if __name__ == "__main__":
    main()
