"""Tests for transforms.schemas."""

from pyspark.sql.types import ArrayType, StructType

from src.transforms import schemas


def test_envelope_schema_wraps_records() -> None:
    env = schemas.envelope_schema(schemas.BY_DATE_RECORD_SCHEMA)
    assert isinstance(env, StructType)
    assert env["ingestion_metadata"].dataType == schemas.INGESTION_METADATA_SCHEMA
    records = env["records"].dataType
    assert isinstance(records, ArrayType)
    assert records.elementType == schemas.BY_DATE_RECORD_SCHEMA


def test_envelope_schemas_cover_all_endpoints() -> None:
    assert set(schemas.ENVELOPE_SCHEMAS) == {"events", "by_date", "media_metadata"}
    for schema in schemas.ENVELOPE_SCHEMAS.values():
        assert isinstance(schema, StructType)
