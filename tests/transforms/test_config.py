"""Tests for transforms.config."""

from pathlib import Path

from src.transforms import config


def test_layer_roots_are_paths() -> None:
    assert isinstance(config.LANDING_ROOT, Path)
    assert isinstance(config.BRONZE_ROOT, Path)
    assert isinstance(config.SILVER_ROOT, Path)
    assert isinstance(config.GOLD_ROOT, Path)


def test_endpoints_match_landing_writer_names() -> None:
    # These strings must match what ingestion passes to write_landing().
    assert config.ENDPOINTS == ("events", "by_date", "media_metadata")


def test_gold_table_names() -> None:
    assert config.DIM_MEDIA == "dim_media"
    assert config.DIM_VISITOR == "dim_visitor"
    assert config.FACT_MEDIA_ENGAGEMENT == "fact_media_engagement"


def test_join_layer_path_with_local_path() -> None:
    assert config.join_layer_path(Path("bronze"), "events") == "bronze/events"


def test_join_layer_path_with_s3_uri() -> None:
    assert (
        config.join_layer_path("s3://my-bucket/bronze", "events") == "s3://my-bucket/bronze/events"
    )


def test_join_layer_path_strips_extra_slashes() -> None:
    # Trailing slash on root + leading slash on leaf → still single-slashed.
    assert (
        config.join_layer_path("s3://my-bucket/bronze/", "/events")
        == "s3://my-bucket/bronze/events"
    )
