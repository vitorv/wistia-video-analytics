"""Configuration for the medallion transform layers (Bronze -> Silver -> Gold).

Phase 2 runs locally: each layer is a directory of Parquet under the repo root,
mirroring the future ``s3://<bucket>/<layer>/`` prefixes. The landing zone is
shared with ingestion, so its root is re-used from ``src.ingestion.config``.
"""

from pathlib import Path

from src.ingestion.config import LANDING_ROOT

# Medallion layer roots (Phase 2 local; -> s3://<bucket>/<layer>/ in Phase 3).
BRONZE_ROOT = Path("bronze")
SILVER_ROOT = Path("silver")
GOLD_ROOT = Path("gold")

# Endpoint names — the landing/Bronze sub-directory per source endpoint. These
# match the strings ingestion passes to ``write_landing`` (see src/ingestion).
EVENTS = "events"
BY_DATE = "by_date"
MEDIA_METADATA = "media_metadata"
ENDPOINTS = (EVENTS, BY_DATE, MEDIA_METADATA)

# Gold table names.
DIM_MEDIA = "dim_media"
DIM_VISITOR = "dim_visitor"
FACT_MEDIA_ENGAGEMENT = "fact_media_engagement"

__all__ = [
    "LANDING_ROOT",
    "BRONZE_ROOT",
    "SILVER_ROOT",
    "GOLD_ROOT",
    "EVENTS",
    "BY_DATE",
    "MEDIA_METADATA",
    "ENDPOINTS",
    "DIM_MEDIA",
    "DIM_VISITOR",
    "FACT_MEDIA_ENGAGEMENT",
]
