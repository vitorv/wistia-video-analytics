"""Landing-zone writer: persists raw extractor output to a partitioned tree.

Phase 1 wrote to a local directory; Phase 3 writes to ``s3://<bucket>/landing/``
in Lambda. The directory layout is identical between the two — the only
difference is the I/O backend. ``write_landing`` dispatches on the
``landing_root`` argument: a plain path (or string) writes locally, an
``s3://`` URI writes via boto3.

Each file is an envelope — the raw records plus an ingestion-metadata header
for Bronze-layer traceability.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3

from src.ingestion import config

logger = logging.getLogger(__name__)


def write_landing(
    endpoint: str,
    media_id: str,
    records: list[dict[str, Any]],
    *,
    landing_root: str | Path | None = None,
    ingest_time: datetime | None = None,
) -> str:
    """Write raw records to the partitioned landing zone; return the location.

    Layout (under ``landing_root``):
    ``<endpoint>/media_id=<id>/ingest_date=<YYYY-MM-DD>/data_<ts>.json``.

    ``landing_root`` accepts either a local path (str or ``Path``) or an
    ``s3://bucket/prefix`` URI; the return value is a path string for local
    writes and an ``s3://bucket/key`` URI for S3 writes. The run's UTC
    timestamp goes into the file name, so every run writes its own immutable
    file — re-running (even within the same UTC day) never overwrites a prior
    capture; downstream Bronze deduplicates. ``ingest_time`` defaults to now.
    """
    root = landing_root if landing_root is not None else config.get_landing_root()
    ingest_dt = ingest_time if ingest_time is not None else datetime.now(timezone.utc)
    ingest_date = ingest_dt.date().isoformat()
    run_stamp = ingest_dt.strftime("%Y%m%dT%H%M%S%fZ")

    relative_key = f"{endpoint}/media_id={media_id}/ingest_date={ingest_date}/data_{run_stamp}.json"
    envelope = {
        "ingestion_metadata": {
            "endpoint": endpoint,
            "media_id": media_id,
            "ingest_timestamp": ingest_dt.isoformat(),
            "ingest_date": ingest_date,
            "record_count": len(records),
        },
        "records": records,
    }
    envelope_text = json.dumps(envelope, indent=2, ensure_ascii=False)

    root_str = str(root)
    if root_str.startswith("s3://"):
        location = _write_s3(root_str, relative_key, envelope_text)
    else:
        location = _write_local(Path(root), relative_key, envelope_text)

    logger.info(
        "landing write endpoint=%s media_id=%s records=%d location=%s",
        endpoint,
        media_id,
        len(records),
        location,
    )
    return location


def _write_local(root: Path, relative_key: str, content: str) -> str:
    """Local-filesystem backend — creates parent dirs and writes the file."""
    file_path = root / relative_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def _write_s3(root_uri: str, relative_key: str, content: str) -> str:
    """S3 backend — PutObject under the URI's bucket/prefix."""
    bucket, prefix = _parse_s3_uri(root_uri)
    key = f"{prefix}/{relative_key}" if prefix else relative_key
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="application/json",
    )
    return f"s3://{bucket}/{key}"


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split ``s3://bucket/optional/prefix`` into ``(bucket, prefix)``.

    The prefix is returned without leading or trailing slashes.
    """
    without_scheme = uri[len("s3://") :]
    bucket, _, prefix = without_scheme.partition("/")
    return bucket, prefix.strip("/")
