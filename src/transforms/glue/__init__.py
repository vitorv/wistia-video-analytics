"""Glue 5.0 entry-point scripts for the Bronze/Silver/Gold jobs.

Each ``*_job.py`` module is uploaded as a standalone Glue job script (not
imported by anything else in the project). The pure transform functions
they call live in ``src.transforms.bronze`` / ``silver`` / ``gold`` and
ship in the ``transforms.zip`` referenced via Glue's ``--extra-py-files``.

These modules import ``awsglue`` and ``pyspark.context`` (the latter is
SparkContext, not the SparkSession builder used locally), which only
exist in the Glue runtime — hence they are excluded from coverage. The
pure transforms are tested by ``tests/transforms/``.
"""
