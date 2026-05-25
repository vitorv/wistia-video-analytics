"""Streamlit dashboard — Wistia video engagement Gold model.

Run locally from the repo root::

    streamlit run src/dashboard/app.py

Reads the Gold Parquet directories under ``gold/`` (the default ``GOLD_ROOT``)
written by ``python -m src.transforms``.
"""

# Streamlit launches this file as a script (not as a package module), so the
# repo root is not on sys.path by default. Add it explicitly so the absolute
# ``from src.*`` imports below resolve regardless of cwd.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard import data  # noqa: E402
from src.transforms.config import GOLD_ROOT  # noqa: E402


@st.cache_data
def _load(gold_root_str: str) -> dict[str, pd.DataFrame]:
    return data.load_gold(Path(gold_root_str))


def main() -> None:
    st.set_page_config(page_title="Wistia Engagement", layout="wide")
    st.title("Wistia Video Engagement")
    st.caption(f"Reading Gold from `{GOLD_ROOT}`")

    gold = _load(str(GOLD_ROOT))
    fact = gold["fact_media_engagement"]
    dim_media = gold["dim_media"]
    dim_visitor = gold["dim_visitor"]

    summary = data.kpi_summary(fact)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total plays", f"{summary['total_plays']:,}")
    c2.metric("Unique visitors", f"{summary['unique_visitors']:,}")
    c3.metric("Avg watched %", f"{summary['avg_watched_percent']:.1%}")
    c4.metric("Total watch hours", f"{summary['total_watch_hours']:.2f}")

    # Shared column config: display avg_watched_percent as a one-decimal
    # percentage (the underlying column is a 0..1 fraction; the table-building
    # blocks below multiply by 100 before formatting).
    percent_col = st.column_config.NumberColumn(format="%.1f%%")

    st.subheader("Last 7 days")
    last_week = data.recent_engagement(fact, dim_media, days=7).assign(
        avg_watched_percent=lambda d: d["avg_watched_percent"] * 100
    )
    st.dataframe(
        last_week,
        width="stretch",
        column_config={"avg_watched_percent": percent_col},
    )

    st.subheader("Last 30 days")
    last_month = data.recent_engagement(fact, dim_media, days=30).assign(
        avg_watched_percent=lambda d: d["avg_watched_percent"] * 100
    )
    st.dataframe(
        last_month,
        width="stretch",
        column_config={"avg_watched_percent": percent_col},
    )

    st.subheader("Engagement by media")
    eng = data.engagement_by_media(fact, dim_media).assign(
        avg_watched_percent=lambda d: d["avg_watched_percent"] * 100
    )
    st.dataframe(
        eng,
        width="stretch",
        column_config={"avg_watched_percent": percent_col},
    )

    st.subheader("Daily trends")
    trends = data.daily_trends(fact).merge(
        dim_media[["media_id", "channel"]], on="media_id", how="left"
    )
    st.line_chart(trends, x="date", y="plays", color="channel")

    st.subheader("Monthly engagement")
    monthly = data.monthly_engagement(fact, dim_media).assign(
        avg_watched_percent=lambda d: d["avg_watched_percent"] * 100
    )
    st.dataframe(
        monthly,
        width="stretch",
        column_config={"avg_watched_percent": percent_col},
    )

    st.subheader("Top visitors")
    top = data.top_visitors(fact, dim_visitor, n=10).assign(
        avg_watched_percent=lambda d: d["avg_watched_percent"] * 100
    )
    st.dataframe(
        top,
        width="stretch",
        column_config={"avg_watched_percent": percent_col},
    )


main()
