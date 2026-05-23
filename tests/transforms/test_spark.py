"""Tests for transforms.spark."""

from pyspark.sql import SparkSession

from src.transforms.spark import build_spark


def test_build_spark_returns_usable_session(spark: SparkSession) -> None:
    # The `spark` fixture is constructed via build_spark(); confirm it works.
    assert isinstance(spark, SparkSession)
    assert spark.range(3).count() == 3


def test_build_spark_is_idempotent(spark: SparkSession) -> None:
    # getOrCreate() returns the active session instead of starting a new one.
    assert build_spark("another-name") is spark
