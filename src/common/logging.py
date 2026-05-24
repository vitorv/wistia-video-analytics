"""Shared logging configuration — JSON lines for CloudWatch.

Both ``python -m src.ingestion`` and ``python -m src.transforms`` use this so
their logs share a single line format wherever they run (locally, or in
Phase 3 from Lambda / Glue into CloudWatch Logs Insights).
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line, with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, tz=timezone.utc)
        payload = {
            "ts": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Route ``level``-and-above logs as JSON lines to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
