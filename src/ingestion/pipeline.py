"""Ingestion pipeline orchestration.

``run()`` wires the client, extractors, landing writer, and watermark store into
one pass over the configured media. Two entry points share it:
  - ``python -m src.ingestion`` (see ``__main__.py``) — local runs
  - ``handler()`` — AWS Lambda (Phase 3)

Phase 3 deployment: the Lambda package bundles ``src/ingestion/`` plus the
``requirements.txt`` dependencies; the handler is ``src.ingestion.pipeline.handler``.
The landing zone and watermark store dispatch on whether
``WISTIA_LANDING_BUCKET`` is set in the environment — set in Lambda (S3 mode),
unset in local development (writes to ``./landing/``).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.logging import configure_logging
from src.ingestion import config
from src.ingestion.client import WistiaClient
from src.ingestion.errors import WistiaAuthError, WistiaError
from src.ingestion.extractors import extract_by_date, extract_events, extract_media_metadata
from src.ingestion.landing import write_landing
from src.ingestion.watermark import WatermarkStore, newest_received_at

logger = logging.getLogger(__name__)


def run(
    media_ids: list[str] | None = None,
    *,
    landing_root: str | Path | None = None,
    watermark_path: str | Path | None = None,
) -> dict[str, Any]:
    """Ingest every endpoint for each media into the landing zone.

    Pulls Events, by_date, and media metadata for each media ID, writes each raw
    response to the landing zone, and advances the incremental watermarks. A
    ``WistiaAuthError`` aborts the whole run (a bad token affects every media);
    any other per-media failure is logged and skipped so the rest still ingest.

    ``landing_root`` and ``watermark_path`` accept a local path or an
    ``s3://...`` URI. When unset, ``config.get_landing_root()`` /
    ``get_watermark_path()`` decide based on the ``WISTIA_LANDING_BUCKET``
    environment variable.

    Returns a summary dict: ``{"media": {id: {...}}, "had_errors": bool}``.
    """
    media_ids = media_ids if media_ids is not None else config.MEDIA_IDS
    landing_root = landing_root if landing_root is not None else config.get_landing_root()
    watermark_path = watermark_path if watermark_path is not None else config.get_watermark_path()

    logger.info(
        "ingestion run starting media_ids=%s landing_root=%s watermark=%s",
        media_ids,
        landing_root,
        watermark_path,
    )
    store = WatermarkStore.load(watermark_path)
    summary: dict[str, Any] = {"media": {}, "had_errors": False}

    with WistiaClient(config.get_api_token()) as client:
        for media_id in media_ids:
            try:
                summary["media"][media_id] = _ingest_media(client, store, media_id, landing_root)
            except WistiaAuthError:
                logger.error("auth failure — aborting run media_id=%s", media_id)
                raise
            except WistiaError as exc:
                logger.error("media ingestion failed media_id=%s error=%s", media_id, exc)
                summary["media"][media_id] = {"error": str(exc)}
                summary["had_errors"] = True

    store.save()
    logger.info("ingestion run complete summary=%s", summary)
    return summary


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """AWS Lambda entry point. Configures structured logging and delegates to ``run()``.

    The Lambda runtime sets ``WISTIA_LANDING_BUCKET`` (and optionally
    ``WISTIA_STATE_KEY``) via the function's environment variables, which
    flips both the landing zone and watermark to S3. Stdout is captured by
    the Lambda runtime and routed to CloudWatch Logs.
    """
    configure_logging()
    return run()


def _ingest_media(
    client: WistiaClient,
    store: WatermarkStore,
    media_id: str,
    landing_root: str | Path,
) -> dict[str, int]:
    """Pull every endpoint for one media, write landing files, advance watermarks."""
    logger.info("ingesting media_id=%s", media_id)
    today = datetime.now(timezone.utc).date()

    events = extract_events(client, media_id, since=store.events_since(media_id))
    write_landing("events", media_id, events, landing_root=landing_root)
    newest = newest_received_at(events)
    if newest is not None:
        store.set_events_watermark(media_id, newest)

    rows = extract_by_date(client, media_id, store.by_date_start(media_id), today)
    write_landing("by_date", media_id, rows, landing_root=landing_root)
    store.set_by_date_watermark(media_id, today)

    metadata = extract_media_metadata(client, media_id)
    write_landing("media_metadata", media_id, [metadata], landing_root=landing_root)

    return {"events": len(events), "by_date": len(rows), "media_metadata": 1}
