"""Per-endpoint extraction functions for the Wistia Stats API.

Each function pulls raw records from one endpoint and returns them as plain
Python structures. No field-level transformation happens here — the landing
zone stores responses as received; cleaning and modeling are downstream
(Silver/Gold).
"""

import logging
from datetime import date, datetime
from typing import Any

from src.ingestion import config
from src.ingestion.client import WistiaClient

logger = logging.getLogger(__name__)


def extract_events(
    client: WistiaClient,
    media_id: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Pull Events for one media.

    Events are returned newest-first by ``received_at``. When ``since`` is given
    (a timezone-aware UTC datetime — typically the incremental watermark),
    pagination stops at the first event at or before that timestamp, since every
    event beyond it is older still. Returns events strictly newer than ``since``;
    with ``since=None`` returns the full available history.
    """
    url = f"{config.BASE_URL}/stats/events"
    collected: list[dict[str, Any]] = []
    for page in client.paginate(url, params={"media_id": media_id}):
        for event in page:
            if since is not None and _event_timestamp(event) <= since:
                logger.info(
                    "events watermark reached media_id=%s collected=%d",
                    media_id,
                    len(collected),
                )
                return collected
            collected.append(event)
    logger.info("events pulled media_id=%s total=%d", media_id, len(collected))
    return collected


def extract_by_date(
    client: WistiaClient,
    media_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Pull daily aggregate stats for one media over an inclusive date range."""
    url = f"{config.BASE_URL}/stats/medias/{media_id}/by_date"
    records: list[dict[str, Any]] = client.get(
        url,
        params={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    )
    logger.info(
        "by_date pulled media_id=%s range=%s..%s days=%d",
        media_id,
        start_date,
        end_date,
        len(records),
    )
    return records


def extract_media_metadata(client: WistiaClient, media_id: str) -> dict[str, Any]:
    """Pull media metadata (title, created date, section name) from the Data API."""
    url = f"{config.BASE_URL}/medias/{media_id}"
    metadata: dict[str, Any] = client.get(url)
    logger.info("media metadata pulled media_id=%s", media_id)
    return metadata


def _event_timestamp(event: dict[str, Any]) -> datetime:
    """Parse an event's ``received_at`` into a timezone-aware datetime."""
    return datetime.fromisoformat(event["received_at"])
