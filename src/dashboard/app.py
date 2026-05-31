"""Streamlit dashboard — Wistia video engagement Gold model.

Run locally from the repo root::

    streamlit run src/dashboard/app.py

Reads the Gold Parquet directories under ``gold/`` (the default ``GOLD_ROOT``)
written by ``python -m src.transforms``.
"""

# Streamlit launches this file as a script (not as a package module), so the
# repo root is not on sys.path by default. Add it explicitly so the absolute
# ``from src.*`` imports below resolve regardless of cwd.
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.dashboard import data  # noqa: E402
from src.transforms.config import GOLD_ROOT  # noqa: E402


@st.cache_data
def _load(gold_root_str: str) -> dict[str, pd.DataFrame]:
    return data.load_gold(gold_root_str)


def main() -> None:
    st.set_page_config(page_title="Wistia Engagement", layout="wide")
    st.title("Wistia Video Engagement")
    # WISTIA_GOLD_URI is set on the ECS task in Phase 3 (s3://.../gold);
    # absent in local dev, where we fall back to the Phase 2 local root.
    gold_root = os.environ.get("WISTIA_GOLD_URI") or str(GOLD_ROOT)
    st.caption(f"Reading Gold from `{gold_root}`")

    # Opt-in S3 read-stack diagnostics. Default off; flip
    # WISTIA_DASHBOARD_DEBUG=1 on the ECS task (via CFN parameter override or
    # `aws ecs update-service`) when the dashboard renders empty or feels
    # wrong. Emits to container stdout, where ECS picks it up via the
    # awslogs driver. Only runs against S3-backed roots, so local dev is
    # silent regardless of the env var.
    if gold_root.startswith("s3://") and os.environ.get("WISTIA_DASHBOARD_DEBUG") == "1":
        import s3fs  # type: ignore[import-untyped]  # noqa: WPS433 — lazy import

        uri_noproto = gold_root.removeprefix("s3://")
        try:
            fs = s3fs.S3FileSystem(anon=False)
            print(f"DEBUG s3fs.ls({uri_noproto!r}) -> {fs.ls(uri_noproto)}", flush=True)
            print(
                f"DEBUG s3fs.ls(dim_media) -> {fs.ls(f'{uri_noproto}/dim_media')}",
                flush=True,
            )
        except Exception as e:
            print(f"DEBUG s3fs.ls error: {e!r}", flush=True)
        try:
            dm = pd.read_parquet(f"{gold_root}/dim_media")
            print(
                f"DEBUG pd.read_parquet dim_media shape={dm.shape} cols={list(dm.columns)}",
                flush=True,
            )
        except Exception as e:
            print(f"DEBUG read_parquet error: {e!r}", flush=True)

    gold = _load(gold_root)
    fact = gold["fact_media_engagement"]
    dim_media = gold["dim_media"]
    dim_visitor = gold["dim_visitor"]

    if fact.empty:
        st.info(
            "No play events have been ingested into Gold yet. The infrastructure is "
            "healthy; this banner will disappear once the next Lambda + Glue run picks "
            "up real viewer activity. Set `WISTIA_DASHBOARD_DEBUG=1` on the task to "
            "inspect the S3 read stack."
        )

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
