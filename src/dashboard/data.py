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

    Days with zero engagement are filled with ``plays = 0`` so the dashboard's
    line chart shows real zeros instead of straight-line gaps across the dead
    stretches. ``play_rate`` and ``total_watch_time`` stay null on filled rows
    (they have no by_date contribution by definition).
    """
    media_day = fact.groupby(["media_id", "date"], as_index=False).agg(
        plays=("play_count", "sum"),
        play_rate=("play_rate", "first"),
        total_watch_time=("total_watch_time", "first"),
    )
    if media_day.empty:
        return media_day
    # Normalize date to ``datetime.date`` so reindex/merge keys align whether
    # the input came from Spark Parquet (date) or a test fixture (string).
    media_day["date"] = pd.to_datetime(media_day["date"]).dt.date
    full_grid = pd.MultiIndex.from_product(
        [
            media_day["media_id"].unique(),
            pd.date_range(media_day["date"].min(), media_day["date"].max(), freq="D").date,
        ],
        names=["media_id", "date"],
    ).to_frame(index=False)
    result = full_grid.merge(media_day, on=["media_id", "date"], how="left")
    result["plays"] = result["plays"].fillna(0).astype(int)
    return result.sort_values(["media_id", "date"]).reset_index(drop=True)


def monthly_engagement(fact: pd.DataFrame, dim_media: pd.DataFrame) -> pd.DataFrame:
    """Per-(media, month) summary — plays, unique visitors, avg watched %.

    Aggregates the fact to the calendar month for long-term trend tables.
    Joins ``dim_media`` so the table can show ``title`` and ``channel`` next
    to each media row.
    """
    monthly = (
        fact.assign(month=pd.to_datetime(fact["date"]).dt.to_period("M").astype(str))
        .groupby(["media_id", "month"], as_index=False)
        .agg(
            plays=("play_count", "sum"),
            unique_visitors=("visitor_id", "nunique"),
            avg_watched_percent=("watched_percent", "mean"),
        )
    )
    return monthly.merge(dim_media[["media_id", "title", "channel"]], on="media_id", how="left")


def recent_engagement(fact: pd.DataFrame, dim_media: pd.DataFrame, days: int) -> pd.DataFrame:
    """Per-media engagement summary for the most recent ``days`` of fact data.

    The window is anchored at ``max(fact.date)`` (the newest date in the data)
    rather than "today" so the table is meaningful even when the dataset is
    back-filled or stale. In a steady-state production run with daily
    ingestion the anchor equals today.
    """
    output_cols = [
        "media_id",
        "title",
        "channel",
        "plays",
        "unique_visitors",
        "active_days",
        "avg_watched_percent",
    ]
    if fact.empty:
        return pd.DataFrame(columns=output_cols)
    dates = pd.to_datetime(fact["date"])
    cutoff = dates.max() - pd.Timedelta(days=days - 1)
    recent = fact[dates >= cutoff]
    agg = recent.groupby("media_id", as_index=False).agg(
        plays=("play_count", "sum"),
        unique_visitors=("visitor_id", "nunique"),
        active_days=("date", "nunique"),
        avg_watched_percent=("watched_percent", "mean"),
    )
    return agg.merge(dim_media[["media_id", "title", "channel"]], on="media_id", how="left")[
        output_cols
    ]


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
