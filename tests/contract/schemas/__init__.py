"""Schema definitions for AUTOCOG contract tests."""

from __future__ import annotations

from tests.contract.schemas.autocog_schemas import (
    ALL_SCHEMAS,
    CYCLE_RESULT_SCHEMA_V1,
    DISCORD_WEBHOOK_SCHEMA_V1,
    HEALTH_RESPONSE_SCHEMA_V1,
    INFLUXDB_MEASUREMENT_SCHEMA_V1,
    POLICY_RESULT_SCHEMA_V1,
    QDRANT_POINT_SCHEMA_V1,
    REDIS_KEY_PATTERN_V1,
    SELF_ASSESSMENT_ARTIFACT_SCHEMA_V1,
    get_schema,
    validate_with_schema,
)

__all__ = [
    "SELF_ASSESSMENT_ARTIFACT_SCHEMA_V1",
    "CYCLE_RESULT_SCHEMA_V1",
    "POLICY_RESULT_SCHEMA_V1",
    "HEALTH_RESPONSE_SCHEMA_V1",
    "QDRANT_POINT_SCHEMA_V1",
    "DISCORD_WEBHOOK_SCHEMA_V1",
    "INFLUXDB_MEASUREMENT_SCHEMA_V1",
    "REDIS_KEY_PATTERN_V1",
    "ALL_SCHEMAS",
    "get_schema",
    "validate_with_schema",
]
