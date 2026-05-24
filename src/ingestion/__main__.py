"""Local entry point — ``python -m src.ingestion``."""

import logging
import sys

from src.common.logging import configure_logging
from src.ingestion.errors import WistiaError
from src.ingestion.pipeline import run

logger = logging.getLogger("src.ingestion")


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
