"""Tests for the local entry point (``python -m src.ingestion``)."""

import json
import logging

import pytest

from src.ingestion.__main__ import _JsonFormatter, configure_logging, main
from src.ingestion.errors import WistiaAuthError


def test_json_formatter_renders_record_as_json() -> None:
    record = logging.LogRecord(
        name="src.ingestion.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="count=%d",
        args=(7,),
        exc_info=None,
    )
    parsed = json.loads(_JsonFormatter().format(record))
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "src.ingestion.demo"
    assert parsed["msg"] == "count=7"


def test_configure_logging_installs_json_formatter() -> None:
    configure_logging()
    handlers = logging.getLogger().handlers
    assert any(isinstance(h.formatter, _JsonFormatter) for h in handlers)


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
