"""Tests for src.common.logging."""

import json
import logging

from src.common.logging import JsonFormatter, configure_logging


def test_json_formatter_renders_record_as_json() -> None:
    record = logging.LogRecord(
        name="src.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="count=%d",
        args=(7,),
        exc_info=None,
    )

    parsed = json.loads(JsonFormatter().format(record))

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "src.demo"
    assert parsed["msg"] == "count=7"
    assert "ts" in parsed


def test_configure_logging_installs_json_formatter() -> None:
    configure_logging()
    handlers = logging.getLogger().handlers
    assert any(isinstance(h.formatter, JsonFormatter) for h in handlers)
