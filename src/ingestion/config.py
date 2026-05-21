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

# Local landing-zone root (Phase 1); becomes s3://<bucket>/landing/ in Phase 2
LANDING_ROOT = Path("landing")


def get_api_token() -> str:
    token = os.environ.get("WISTIA_API_TOKEN")
    if not token:
        raise RuntimeError("WISTIA_API_TOKEN not set — add it to .env")
    return token
