"""Shared fixtures for the transform test suite."""

from collections.abc import Iterator

import pytest
from pyspark.sql import SparkSession

from src.transforms.spark import build_spark


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    """A single local SparkSession shared across all transform tests.

    Session-scoped because starting Spark costs several seconds; the transforms
    never mutate session state, so sharing one session is safe.
    """
    session = build_spark("wistia-transforms-tests")
    yield session
    session.stop()
