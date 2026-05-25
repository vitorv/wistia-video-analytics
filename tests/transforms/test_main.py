"""Tests for the transforms local entry point (``python -m src.transforms``)."""

from unittest.mock import MagicMock

import pytest


def _stub_spark() -> MagicMock:
    return MagicMock(name="SparkSession")


def test_main_returns_zero_on_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.transforms.__main__ import main

    spark = _stub_spark()
    monkeypatch.setattr("src.transforms.__main__.build_spark", lambda: spark)
    monkeypatch.setattr("src.transforms.__main__.run_bronze", lambda s: {"events": 1})
    monkeypatch.setattr("src.transforms.__main__.run_silver", lambda s: {"events": 1})
    monkeypatch.setattr("src.transforms.__main__.run_gold", lambda s: {"dim_media": 1})

    assert main() == 0
    spark.stop.assert_called_once()


def test_main_stops_spark_even_when_a_transform_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.transforms.__main__ import main

    spark = _stub_spark()
    monkeypatch.setattr("src.transforms.__main__.build_spark", lambda: spark)

    def _fail(_spark: object) -> dict[str, int]:
        raise RuntimeError("bronze blew up")

    monkeypatch.setattr("src.transforms.__main__.run_bronze", _fail)

    with pytest.raises(RuntimeError, match="bronze blew up"):
        main()
    spark.stop.assert_called_once()
