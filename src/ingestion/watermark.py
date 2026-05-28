"""Incremental watermark store (FR7).

Tracks, per endpoint and media, the high-water mark of ingested data so each run
fetches only what is new.

FR7 reconciliation: the assignment specifies incremental loading on
``created_at`` / ``updated_at``, but the Wistia Stats API exposes neither on the
endpoints in use. The watermark instead tracks:
  - Events  -> ``received_at`` (event arrival timestamp), a UTC datetime
  - by_date -> ``date`` (the calendar day of the daily aggregate)

Timezone contract: the Events watermark round-trips as a timezone-aware UTC
datetime — stored as a full ISO-8601 string with offset, read back with
``datetime.fromisoformat()``. ``extract_events(since=...)`` compares it against
aware event timestamps, and Python raises ``TypeError`` on an aware-vs-naive
comparison, so a naive watermark is rejected at ``set_events_watermark``.

Phase 1 used a local JSON file; Phase 3 reads/writes the same JSON shape from
``s3://<bucket>/state/watermark.json``. ``WatermarkStore.load`` and ``save``
dispatch on the path argument's ``s3://`` prefix.
"""

import json
import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.ingestion import config
from src.ingestion.extractors import event_timestamp

logger = logging.getLogger(__name__)

_ENDPOINTS = ("events", "by_date")


class WatermarkStore:
    """Per-(endpoint, media) incremental watermarks, backed by JSON.

    The backing store is either a local file or an S3 object — chosen by the
    ``path`` argument to ``load`` (``s3://...`` → S3, otherwise local).
    """

    def __init__(self, path: str | Path, data: dict[str, dict[str, str]]) -> None:
        self._path = path
        self._data = data

    @classmethod
    def load(cls, path: str | Path | None = None) -> "WatermarkStore":
        """Load the watermark store from ``path``, or start empty if absent."""
        target = path if path is not None else config.get_watermark_path()
        data: dict[str, dict[str, str]] = {endpoint: {} for endpoint in _ENDPOINTS}
        raw = _read_json(target)
        if raw is not None:
            for endpoint in _ENDPOINTS:
                stored = raw.get(endpoint, {})
                if isinstance(stored, dict):
                    data[endpoint] = {str(k): str(v) for k, v in stored.items()}
        return cls(target, data)

    def events_since(self, media_id: str) -> datetime:
        """Events cutoff for ``media_id``: stored watermark, else the backfill floor.

        Always timezone-aware (UTC), as required by ``extract_events(since=...)``.
        """
        stored = self._data["events"].get(media_id)
        if stored is not None:
            return datetime.fromisoformat(stored)
        return datetime.combine(config.BACKFILL_FLOOR_DATE, time.min, tzinfo=timezone.utc)

    def by_date_start(self, media_id: str) -> date:
        """by_date start date for ``media_id``: stored watermark, else the floor."""
        stored = self._data["by_date"].get(media_id)
        if stored is not None:
            return date.fromisoformat(stored)
        return config.BACKFILL_FLOOR_DATE

    def set_events_watermark(self, media_id: str, watermark: datetime) -> None:
        """Record the Events watermark for ``media_id``. Rejects a naive datetime."""
        if watermark.utcoffset() is None:
            raise ValueError(f"events watermark must be timezone-aware; got naive {watermark!r}")
        self._data["events"][media_id] = watermark.isoformat()

    def set_by_date_watermark(self, media_id: str, watermark: date) -> None:
        """Record the by_date watermark (last ingested date) for ``media_id``."""
        self._data["by_date"][media_id] = watermark.isoformat()

    def save(self) -> None:
        """Persist the store as JSON to its configured location."""
        _write_json(self._path, self._data)
        logger.info("watermark store saved location=%s", self._path)


def newest_received_at(events: list[dict[str, Any]]) -> datetime | None:
    """Return the latest ``received_at`` among ``events``, or None if empty.

    Used to advance the Events watermark to the newest record actually ingested,
    so the next run never skips data the API surfaced behind the watermark.
    """
    if not events:
        return None
    return max(event_timestamp(event) for event in events)


def _read_json(path: str | Path) -> dict[str, Any] | None:
    """Read JSON from a local Path or an ``s3://...`` URI. Returns None if absent."""
    path_str = str(path)
    if path_str.startswith("s3://"):
        bucket, key = _parse_s3_uri(path_str)
        try:
            response = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)
    local_path = Path(path)
    if not local_path.exists():
        return None
    return json.loads(local_path.read_text(encoding="utf-8"))


def _write_json(path: str | Path, data: dict[str, Any]) -> None:
    """Write JSON to a local Path (creating parent dirs) or an ``s3://...`` URI."""
    content = json.dumps(data, indent=2, sort_keys=True)
    path_str = str(path)
    if path_str.startswith("s3://"):
        bucket, key = _parse_s3_uri(path_str)
        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="application/json",
        )
        return
    local_path = Path(path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(content, encoding="utf-8")


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split ``s3://bucket/key/path`` into ``(bucket, key)``."""
    without_scheme = uri[len("s3://") :]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key
