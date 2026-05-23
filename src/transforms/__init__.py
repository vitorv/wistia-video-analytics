"""PySpark medallion transforms: Landing JSON -> Bronze -> Silver -> Gold.

Phase 2 runs these locally; Phase 3 runs the same transform functions as AWS
Glue jobs. Each transform is a pure ``DataFrame -> DataFrame`` function plus a
thin IO wrapper, so the Glue entry points reuse the pure functions unchanged.
"""
