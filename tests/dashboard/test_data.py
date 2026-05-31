"""Tests for src.dashboard.data."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.data import (
    daily_trends,
    engagement_by_media,
    kpi_summary,
    load_gold,
    monthly_engagement,
    recent_engagement,
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


def test_daily_trends_fills_missing_dates_and_dedupes(fact: pd.DataFrame) -> None:
    result = daily_trends(fact)
    # Fixture: m1 had events only on 2026-05-19; m2 only on 2026-05-20.
    # daily_trends fills the full (media x date) grid with plays=0 for the
    # missing combos and dedupes the denormalized play_rate / total_watch_time
    # via "first".
    assert len(result) == 4  # 2 media x 2 dates in range
    m1_19 = result[(result["media_id"] == "m1") & (result["date"] == date(2026, 5, 19))].iloc[0]
    assert m1_19["plays"] == 3  # 2 + 1
    assert m1_19["play_rate"] == 0.8
    assert m1_19["total_watch_time"] == 1.5
    # m1 had no events on 2026-05-20 -> filled with plays=0; denormalized
    # fields stay null (no by_date contribution for the filled day)
    m1_20 = result[(result["media_id"] == "m1") & (result["date"] == date(2026, 5, 20))].iloc[0]
    assert m1_20["plays"] == 0
    assert pd.isna(m1_20["play_rate"])


def test_daily_trends_empty_fact_returns_empty() -> None:
    empty = pd.DataFrame(
        columns=["media_id", "date", "play_count", "play_rate", "total_watch_time"]
    )
    assert daily_trends(empty).empty


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


def test_load_gold_dispatches_s3_uri_to_read_parquet(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Phase 3 ECS task passes ``s3://<bucket>/gold`` via the
    # ``WISTIA_GOLD_URI`` env var. Verify ``load_gold`` joins it correctly
    # for each of the three tables and hands the URIs unchanged to
    # ``pandas.read_parquet`` (which delegates to ``s3fs`` at runtime).
    seen: list[str] = []

    def fake_read_parquet(path: str) -> pd.DataFrame:
        seen.append(path)
        return pd.DataFrame()

    monkeypatch.setattr("src.dashboard.data.pd.read_parquet", fake_read_parquet)
    load_gold("s3://my-bucket/gold")

    assert seen == [
        "s3://my-bucket/gold/dim_media",
        "s3://my-bucket/gold/dim_visitor",
        "s3://my-bucket/gold/fact_media_engagement",
    ]


def test_monthly_engagement_aggregates_per_month(
    fact: pd.DataFrame, dim_media: pd.DataFrame
) -> None:
    result = monthly_engagement(fact, dim_media)
    # Fixture dates all in May 2026 -> one (media, month) group per media.
    assert len(result) == 2
    by_key = {(r["media_id"], r["month"]): r for r in result.to_dict("records")}
    assert by_key[("m1", "2026-05")]["plays"] == 3  # 2 + 1
    assert by_key[("m1", "2026-05")]["unique_visitors"] == 2
    assert by_key[("m1", "2026-05")]["channel"] == "Youtube"
    assert by_key[("m2", "2026-05")]["plays"] == 3
    assert by_key[("m2", "2026-05")]["unique_visitors"] == 1
    assert by_key[("m2", "2026-05")]["channel"] == "Facebook"


def test_recent_engagement_filters_to_anchor_window(
    fact: pd.DataFrame, dim_media: pd.DataFrame
) -> None:
    # Fixture: m1 on 2026-05-19, m2 on 2026-05-20. Anchor = max = 2026-05-20.
    # days=1 -> only 2026-05-20 in window -> only m2 in result.
    result = recent_engagement(fact, dim_media, days=1)
    assert list(result["media_id"]) == ["m2"]
    assert result.iloc[0]["plays"] == 3
    assert result.iloc[0]["active_days"] == 1
    assert result.iloc[0]["channel"] == "Facebook"
    # days=2 -> both dates in window -> both media.
    result2 = recent_engagement(fact, dim_media, days=2)
    assert set(result2["media_id"]) == {"m1", "m2"}


def test_recent_engagement_empty_fact_returns_empty_with_schema() -> None:
    empty_fact = pd.DataFrame(
        columns=[
            "media_id",
            "visitor_id",
            "date",
            "play_count",
            "watched_percent",
            "play_rate",
            "total_watch_time",
        ]
    )
    empty_dim = pd.DataFrame(columns=["media_id", "title", "channel"])
    result = recent_engagement(empty_fact, empty_dim, days=7)
    assert result.empty
    assert set(result.columns) == {
        "media_id",
        "title",
        "channel",
        "plays",
        "unique_visitors",
        "active_days",
        "avg_watched_percent",
    }
