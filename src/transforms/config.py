"""Configuration for the medallion transform layers (Bronze -> Silver -> Gold).

Phase 2 runs locally: each layer is a directory of Parquet under the repo root,
mirroring the future ``s3://<bucket>/<layer>/`` prefixes.

Phase 3 (Glue): the per-layer functions accept ``str | Path``, so callers can
pass ``s3://<bucket>/<layer>`` URIs unchanged. ``join_layer_path`` handles the
join uniformly — ``Path / str`` doesn't preserve the ``s3://`` scheme, so we
do the join as strings.

The Glue transforms zip ships only ``src/common`` + ``src/transforms`` to keep
the package lean and stand-alone — no ``src.ingestion`` dependency at import
time. The landing-root constant is duplicated below for the local default;
``src.ingestion.config.LANDING_ROOT`` (the original) and this constant are
both ``Path("landing")`` and must stay in sync.
"""

from pathlib import Path

# Mirrors src.ingestion.config.LANDING_ROOT — duplicated so the transforms
# package can import standalone in Glue (where src.ingestion isn't bundled).
LANDING_ROOT = Path("landing")

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


def join_layer_path(root: str | Path, leaf: str) -> str:
    """Join a layer root with a sub-path (endpoint or Gold table name).

    Works for both local ``Path`` roots and ``s3://...`` URI roots — Spark
    accepts the resulting string either way. Trailing slashes on ``root`` and
    leading slashes on ``leaf`` are stripped so the output never doubles up.
    """
    return f"{str(root).rstrip('/')}/{leaf.strip('/')}"


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
    "join_layer_path",
]
