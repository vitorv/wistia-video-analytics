"""Central configuration — constants only. Secrets come from .env, never here."""

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.wistia.com/modern"
REQUEST_TIMEOUT = 60  # seconds; 30s timed out under load during initial API verification
PAGE_SIZE = 10  # Wistia's fixed page size — cannot be overridden via query param

MEDIA_IDS: list[str] = ["gskhw4w4lm", "v08dlrgr7v"]

# Hard floor for initial backfill; prevents pulling thousands of pages of history
# Set one month before oldest media (v08dlrgr7v created 2024-03-21)
BACKFILL_FLOOR_DATE = date(2024, 3, 1)

# Local landing-zone root (default — Phase 1 / dev). In Lambda (Phase 3),
# WISTIA_LANDING_BUCKET is set and get_landing_root() returns an s3:// URI.
LANDING_ROOT = Path("landing")

# Incremental watermark store (local default).
WATERMARK_PATH = LANDING_ROOT / "_watermark.json"

# Default S3 key for the watermark when running against an S3 bucket.
DEFAULT_WATERMARK_S3_KEY = "state/watermark.json"


def get_api_token() -> str:
    token = os.environ.get("WISTIA_API_TOKEN")
    if not token:
        raise RuntimeError("WISTIA_API_TOKEN not set — add it to .env")
    return token


def get_landing_root() -> str | Path:
    """Return the landing-zone root — an s3:// URI in Lambda, a local Path otherwise.

    Set ``WISTIA_LANDING_BUCKET`` to switch to S3 mode (Phase 3 Lambda runtime
    does this). Local development leaves it unset and writes to ``landing/``.
    """
    bucket = os.environ.get("WISTIA_LANDING_BUCKET")
    if bucket:
        return f"s3://{bucket}/landing"
    return LANDING_ROOT


def get_watermark_path() -> str | Path:
    """Return the watermark location — an s3:// URI in Lambda, a local Path otherwise.

    In S3 mode, the key defaults to ``state/watermark.json`` and can be
    overridden with ``WISTIA_STATE_KEY``.
    """
    bucket = os.environ.get("WISTIA_LANDING_BUCKET")
    if bucket:
        key = os.environ.get("WISTIA_STATE_KEY", DEFAULT_WATERMARK_S3_KEY)
        return f"s3://{bucket}/{key}"
    return WATERMARK_PATH
