"""Tests for ingestion configuration."""

import pytest

from src.ingestion import config


def test_get_api_token_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_API_TOKEN", "abc123")
    assert config.get_api_token() == "abc123"


def test_get_api_token_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WISTIA_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="WISTIA_API_TOKEN"):
        config.get_api_token()


def test_get_landing_root_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WISTIA_LANDING_BUCKET", raising=False)
    assert config.get_landing_root() == config.LANDING_ROOT


def test_get_landing_root_s3_when_bucket_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_LANDING_BUCKET", "my-bucket")
    assert config.get_landing_root() == "s3://my-bucket/landing"


def test_get_watermark_path_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WISTIA_LANDING_BUCKET", raising=False)
    monkeypatch.delenv("WISTIA_STATE_KEY", raising=False)
    assert config.get_watermark_path() == config.WATERMARK_PATH


def test_get_watermark_path_s3_default_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_LANDING_BUCKET", "my-bucket")
    monkeypatch.delenv("WISTIA_STATE_KEY", raising=False)
    assert config.get_watermark_path() == "s3://my-bucket/state/watermark.json"


def test_get_watermark_path_s3_custom_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WISTIA_LANDING_BUCKET", "my-bucket")
    monkeypatch.setenv("WISTIA_STATE_KEY", "custom/wm.json")
    assert config.get_watermark_path() == "s3://my-bucket/custom/wm.json"
