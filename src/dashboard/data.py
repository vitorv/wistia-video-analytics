"""Dashboard data access — read Gold Parquet and compute display aggregates.

Pure pandas / pyarrow — the Gold layer is small enough (one row per
media x visitor x date) that PySpark would be overkill, and keeping Spark out
of the dashboard means the Phase 3 Docker image stays small.

All functions are pure (no Streamlit imports, no caching) so they unit-test
cleanly; ``app.py`` is the thin UI layer that wires them into widgets.
"""

from pathlib import Path

import pandas as pd

from src.transforms import config


def load_gold(gold_root: Path) -> dict[str, pd.DataFrame]:
    """Load the three Gold tables from ``gold_root`` as a dict keyed by table."""
    return {
        config.DIM_MEDIA: pd.read_parquet(gold_root / config.DIM_MEDIA),
        config.DIM_VISITOR: pd.read_parquet(gold_root / config.DIM_VISITOR),
        config.FACT_MEDIA_ENGAGEMENT: pd.read_parquet(gold_root / config.FACT_MEDIA_ENGAGEMENT),
    }


def kpi_summary(fact: pd.DataFrame) -> dict[str, float]:
    """Top-level KPIs: total plays, unique visitors, avg watched %, total hours.

    ``total_watch_time`` is denormalized in the fact (the same value repeats
    across every visitor row for a given media+date — see ADR-002), so it is
    deduplicated to one value per ``(media_id, date)`` before being summed.
    """
    media_day_watch = fact.groupby(["media_id", "date"], as_index=False)["total_watch_time"].first()
    return {
        "total_plays": int(fact["play_count"].sum()),
        "unique_visitors": int(fact["visitor_id"].nunique()),
        "avg_watched_percent": float(fact["watched_percent"].mean()),
        "total_watch_hours": float(media_day_watch["total_watch_time"].sum()),
    }


def engagement_by_media(fact: pd.DataFrame, dim_media: pd.DataFrame) -> pd.DataFrame:
    """Per-media totals enriched with title + channel from ``dim_media``."""
    agg = fact.groupby("media_id", as_index=False).agg(
        plays=("play_count", "sum"),
        unique_visitors=("visitor_id", "nunique"),
        avg_watched_percent=("watched_percent", "mean"),
    )
    return agg.merge(dim_media[["media_id", "title", "channel"]], on="media_id", how="left")


def daily_trends(fact: pd.DataFrame) -> pd.DataFrame:
    """Per-(media, date) totals — plays summed; play_rate / total_watch_time taken once.

    ``play_rate`` and ``total_watch_time`` are denormalized at the media+date
    grain — they have the same value across every visitor row for that group.
    ``"first"`` returns that single value without averaging.
    """
    return (
        fact.groupby(["media_id", "date"], as_index=False)
        .agg(
            plays=("play_count", "sum"),
            play_rate=("play_rate", "first"),
            total_watch_time=("total_watch_time", "first"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def top_visitors(fact: pd.DataFrame, dim_visitor: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top ``n`` visitors by total plays, enriched with country."""
    agg = (
        fact.groupby("visitor_id", as_index=False)
        .agg(
            plays=("play_count", "sum"),
            avg_watched_percent=("watched_percent", "mean"),
        )
        .sort_values("plays", ascending=False)
        .head(n)
    )
    return agg.merge(dim_visitor[["visitor_id", "country"]], on="visitor_id", how="left")
