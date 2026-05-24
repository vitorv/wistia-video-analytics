"""Tests for the local entry point (``python -m src.ingestion``)."""

import pytest

from src.ingestion.__main__ import main
from src.ingestion.errors import WistiaAuthError


def test_main_returns_zero_on_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.ingestion.__main__.run", lambda: {"media": {}, "had_errors": False})
    assert main() == 0


def test_main_returns_one_when_a_media_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.ingestion.__main__.run", lambda: {"media": {}, "had_errors": True})
    assert main() == 1


def test_main_returns_one_on_auth_abort(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise() -> dict[str, object]:
        raise WistiaAuthError("bad token")

    monkeypatch.setattr("src.ingestion.__main__.run", _raise)
    assert main() == 1
