"""Tests for the ingestion pipeline orchestration. API mocked with ``responses``."""

from pathlib import Path

import boto3
import pytest
import responses
from moto import mock_aws

from src.ingestion import config
from src.ingestion.errors import WistiaAuthError
from src.ingestion.pipeline import handler, run

EVENTS_URL = f"{config.BASE_URL}/stats/events"


@responses.activate
def test_run_ingests_media_successfully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_API_TOKEN", "test-token")
    responses.get(
        EVENTS_URL,
        json=[{"event_key": "e1", "received_at": "2026-05-19T10:00:00Z"}],
    )
    responses.get(EVENTS_URL, json=[])
    responses.get(
        f"{config.BASE_URL}/stats/medias/abc/by_date",
        json=[{"date": "2026-05-19", "play_count": 3}],
    )
    responses.get(f"{config.BASE_URL}/medias/abc", json={"hashed_id": "abc"})

    summary = run(
        media_ids=["abc"],
        landing_root=tmp_path / "landing",
        watermark_path=tmp_path / "_watermark.json",
    )

    assert summary["had_errors"] is False
    assert summary["media"]["abc"] == {"events": 1, "by_date": 1, "media_metadata": 1}
    for endpoint in ("events", "by_date", "media_metadata"):
        assert (tmp_path / "landing" / endpoint / "media_id=abc").exists()
    assert (tmp_path / "_watermark.json").exists()


@responses.activate
def test_run_aborts_on_auth_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_API_TOKEN", "test-token")
    responses.get(EVENTS_URL, status=401)
    with pytest.raises(WistiaAuthError):
        run(
            media_ids=["abc"],
            landing_root=tmp_path / "landing",
            watermark_path=tmp_path / "_watermark.json",
        )


@responses.activate
def test_run_skips_failed_media_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WISTIA_API_TOKEN", "test-token")
    # "good" is processed first and succeeds; "bad" 404s on its Events pull
    responses.get(
        EVENTS_URL,
        json=[{"event_key": "e1", "received_at": "2026-05-19T10:00:00Z"}],
    )
    responses.get(EVENTS_URL, json=[])
    responses.get(f"{config.BASE_URL}/stats/medias/good/by_date", json=[])
    responses.get(f"{config.BASE_URL}/medias/good", json={"hashed_id": "good"})
    responses.get(EVENTS_URL, status=404)

    summary = run(
        media_ids=["good", "bad"],
        landing_root=tmp_path / "landing",
        watermark_path=tmp_path / "_watermark.json",
    )

    assert summary["had_errors"] is True
    assert summary["media"]["good"]["events"] == 1
    assert "error" in summary["media"]["bad"]


@responses.activate
def test_handler_delegates_to_run_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``WISTIA_LANDING_BUCKET``, the handler routes to local paths."""
    monkeypatch.setenv("WISTIA_API_TOKEN", "test-token")
    monkeypatch.delenv("WISTIA_LANDING_BUCKET", raising=False)
    monkeypatch.setattr(config, "MEDIA_IDS", ["abc"])
    monkeypatch.setattr(config, "LANDING_ROOT", tmp_path / "landing")
    monkeypatch.setattr(config, "WATERMARK_PATH", tmp_path / "_watermark.json")
    responses.get(EVENTS_URL, json=[])  # empty pull → watermark not advanced
    responses.get(f"{config.BASE_URL}/stats/medias/abc/by_date", json=[])
    responses.get(f"{config.BASE_URL}/medias/abc", json={"hashed_id": "abc"})

    result = handler({}, None)

    assert result["had_errors"] is False
    assert result["media"]["abc"]["events"] == 0
    # Local landing files exist
    assert (tmp_path / "landing" / "events" / "media_id=abc").exists()


@responses.activate
def test_handler_writes_to_s3_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting ``WISTIA_LANDING_BUCKET`` flips landing + watermark to S3."""
    monkeypatch.setenv("WISTIA_API_TOKEN", "test-token")
    monkeypatch.setattr(config, "MEDIA_IDS", ["abc"])
    responses.get(EVENTS_URL, json=[])
    responses.get(f"{config.BASE_URL}/stats/medias/abc/by_date", json=[])
    responses.get(f"{config.BASE_URL}/medias/abc", json={"hashed_id": "abc"})

    with mock_aws():
        bucket = "test-handler-bucket"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        monkeypatch.setenv("WISTIA_LANDING_BUCKET", bucket)

        result = handler({}, None)

        assert result["had_errors"] is False

        # Each endpoint wrote at least one landing object under landing/<endpoint>/
        for endpoint in ("events", "by_date", "media_metadata"):
            listing = s3.list_objects_v2(Bucket=bucket, Prefix=f"landing/{endpoint}/")
            assert listing.get("KeyCount", 0) >= 1, f"no objects under landing/{endpoint}/"

        # Watermark JSON exists at the default state key
        head = s3.head_object(Bucket=bucket, Key="state/watermark.json")
        assert head["ContentType"] == "application/json"
