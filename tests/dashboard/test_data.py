"""Tests for src.dashboard.data."""

from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.data import (
    daily_trends,
    engagement_by_media,
    kpi_summary,
    load_gold,
    top_visitors,
)


@pytest.fixture
def fact() -> pd.DataFrame:
    # Two media; v1 has plays across both, v2 only on m2 (a different day).
    # play_rate / total_watch_time are denormalized per (media_id, date) —
    # repeated across visitor rows for the same group.
    return pd.DataFrame(
        {
            "media_id": ["m1", "m1", "m2"],
            "visitor_id": ["v1", "v2", "v1"],
            "date": ["2026-05-19", "2026-05-19", "2026-05-20"],
            "play_count": [2, 1, 3],
            "watched_percent": [0.6, 0.4, 0.7],
            "play_rate": [0.8, 0.8, 0.5],
            "total_watch_time": [1.5, 1.5, 0.9],
        }
    )


@pytest.fixture
def dim_media() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "media_id": ["m1", "m2"],
            "title": ["Vid A", "Vid B"],
            "url": ["https://x/m1", "https://x/m2"],
            "channel": ["Youtube", "Facebook"],
            "created_at": pd.to_datetime(["2025-01-01", "2025-02-01"]),
        }
    )


@pytest.fixture
def dim_visitor() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "visitor_id": ["v1", "v2"],
            "ip_address": ["10.0.0.1", "10.0.0.2"],
            "country": ["US", "DE"],
        }
    )


def test_kpi_summary(fact: pd.DataFrame) -> None:
    summary = kpi_summary(fact)
    assert summary["total_plays"] == 6  # 2 + 1 + 3
    assert summary["unique_visitors"] == 2
    assert summary["avg_watched_percent"] == pytest.approx((0.6 + 0.4 + 0.7) / 3)
    # total_watch_hours = sum of one value per (media, date), not per visitor row
    # m1/2026-05-19 contributes 1.5 once (not 3.0); m2/2026-05-20 contributes 0.9
    assert summary["total_watch_hours"] == pytest.approx(1.5 + 0.9)


def test_engagement_by_media(fact: pd.DataFrame, dim_media: pd.DataFrame) -> None:
    result = engagement_by_media(fact, dim_media).sort_values("media_id").reset_index(drop=True)
    assert list(result["media_id"]) == ["m1", "m2"]
    assert list(result["plays"]) == [3, 3]  # m1: 2+1; m2: 3
    assert list(result["title"]) == ["Vid A", "Vid B"]
    assert list(result["channel"]) == ["Youtube", "Facebook"]


def test_daily_trends_dedupes_denormalized_metrics(fact: pd.DataFrame) -> None:
    result = daily_trends(fact)
    assert len(result) == 2  # 2 distinct (media_id, date) groups
    m1_row = result.loc[result["media_id"] == "m1"].iloc[0]
    assert m1_row["plays"] == 3  # 2 + 1
    # play_rate / total_watch_time are denormalized -> "first" gives the single value
    assert m1_row["play_rate"] == 0.8
    assert m1_row["total_watch_time"] == 1.5


def test_top_visitors_ranks_and_enriches(fact: pd.DataFrame, dim_visitor: pd.DataFrame) -> None:
    result = top_visitors(fact, dim_visitor, n=10)
    # v1 played 2+3=5 times; v2 played 1 time
    assert list(result["visitor_id"]) == ["v1", "v2"]
    assert list(result["plays"]) == [5, 1]
    assert list(result["country"]) == ["US", "DE"]


def test_top_visitors_respects_n_limit(fact: pd.DataFrame, dim_visitor: pd.DataFrame) -> None:
    result = top_visitors(fact, dim_visitor, n=1)
    assert len(result) == 1
    assert result.iloc[0]["visitor_id"] == "v1"


def test_load_gold_reads_all_three_tables(
    tmp_path: Path,
    fact: pd.DataFrame,
    dim_media: pd.DataFrame,
    dim_visitor: pd.DataFrame,
) -> None:
    # Mimic Spark's directory-of-part-files Parquet layout.
    for table, df in (
        ("dim_media", dim_media),
        ("dim_visitor", dim_visitor),
        ("fact_media_engagement", fact),
    ):
        table_dir = tmp_path / table
        table_dir.mkdir()
        df.to_parquet(table_dir / "part-0.parquet")

    loaded = load_gold(tmp_path)

    assert set(loaded.keys()) == {"dim_media", "dim_visitor", "fact_media_engagement"}
    assert len(loaded["dim_media"]) == 2
    assert len(loaded["dim_visitor"]) == 2
    assert len(loaded["fact_media_engagement"]) == 3
