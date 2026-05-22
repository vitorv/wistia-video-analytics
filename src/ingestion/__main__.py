"""Local entry point — ``python -m src.ingestion``."""

import json
import logging
import sys

from src.ingestion.errors import WistiaError
from src.ingestion.pipeline import run

logger = logging.getLogger("src.ingestion")


class _JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON, ready for CloudWatch Logs Insights."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(payload)


def configure_logging() -> None:
    """Send INFO-and-above logs as JSON lines to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> int:
    """Run ingestion; return a process exit code (0 = clean, 1 = errors)."""
    configure_logging()
    try:
        summary = run()
    except WistiaError as exc:
        logger.error("ingestion aborted: %s", exc)
        return 1
    return 1 if summary["had_errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
