"""SparkSession construction for the local transform pipeline.

Phase 2 runs Spark locally on a developer machine. ``build_spark()`` returns a
session configured for a single-node run and, on Windows, wires up the bundled
Hadoop native binaries (``winutils.exe`` / ``hadoop.dll``) that Spark needs to
read and write the local filesystem.

Phase 3 (AWS Glue) supplies its own ``SparkSession`` / ``GlueContext``. The
transform functions take a DataFrame and never build a session themselves, so a
Glue entry point reuses the transforms unchanged.
"""

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

# Repo root: this file is src/transforms/spark.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDORED_HADOOP = _REPO_ROOT / "vendor" / "hadoop"


def _configure_windows_hadoop() -> None:  # pragma: no cover - Windows-only env glue
    """Point Spark at the vendored Hadoop binaries when running on Windows.

    Spark's local-filesystem access on Windows needs ``winutils.exe`` and
    ``hadoop.dll``. They are platform binaries and are not committed — see the
    README for the one-time download into ``vendor/hadoop/bin/``. This is a
    no-op on Linux/macOS and in CI, where Spark needs neither, and a no-op if
    ``HADOOP_HOME`` is already set.
    """
    if os.name != "nt" or "HADOOP_HOME" in os.environ:
        return
    bin_dir = _VENDORED_HADOOP / "bin"
    if not (bin_dir / "winutils.exe").exists():
        return
    os.environ["HADOOP_HOME"] = str(_VENDORED_HADOOP)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def build_spark(app_name: str = "wistia-transforms") -> SparkSession:
    """Return a local ``SparkSession`` for the transform pipeline.

    Pins the driver and worker Python interpreters to the current one (Windows
    has no ``python3`` on PATH by default), wires up the vendored Hadoop
    binaries on Windows, and fixes the session time zone to UTC so timestamp
    casts are deterministic regardless of the host's locale.
    """
    _configure_windows_hadoop()
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    # py4j's INFO-level connection logs are noise and trigger a harmless
    # "I/O operation on closed file" traceback at interpreter shutdown.
    logging.getLogger("py4j").setLevel(logging.WARNING)
    return (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
