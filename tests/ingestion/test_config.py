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
