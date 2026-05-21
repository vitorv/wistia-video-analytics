"""Landing-zone writer: persists raw extractor output to a partitioned local tree.

The directory layout mirrors the future ``s3://<bucket>/landing/`` prefix, so the
Phase 2 move to S3 is a path swap rather than a rewrite. Each file is an
envelope — the raw records plus an ingestion-metadata header for Bronze-layer
traceability.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.ingestion import config

logger = logging.getLogger(__name__)


def write_landing(
    endpoint: str,
    media_id: str,
    records: list[dict[str, Any]],
    *,
    landing_root: Path = config.LANDING_ROOT,
    ingest_time: datetime | None = None,
) -> Path:
    """Write raw records to the partitioned landing zone; return the file path.

    Layout: ``<root>/<endpoint>/media_id=<id>/ingest_date=<YYYY-MM-DD>/data.json``.
    The file name is deterministic per partition, so re-running on the same day
    overwrites the file instead of accumulating duplicates — ingestion stays
    idempotent. ``ingest_time`` defaults to the current UTC time.
    """
    ingest_dt = ingest_time if ingest_time is not None else datetime.now(timezone.utc)
    ingest_date = ingest_dt.date().isoformat()

    partition = landing_root / endpoint / f"media_id={media_id}" / f"ingest_date={ingest_date}"
    partition.mkdir(parents=True, exist_ok=True)
    file_path = partition / "data.json"

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
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)

    logger.info(
        "landing write endpoint=%s media_id=%s records=%d path=%s",
        endpoint,
        media_id,
        len(records),
        file_path,
    )
    return file_path
