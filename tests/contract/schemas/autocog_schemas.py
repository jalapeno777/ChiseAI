"""JSON Schema definitions for AUTOCOG contracts.

This module provides JSON schemas for validating AUTOCOG artifacts and API responses.
These schemas can be used with jsonschema.validate() for runtime validation.
"""

from __future__ import annotations

# Schema for SelfAssessmentArtifact
SELF_ASSESSMENT_ARTIFACT_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "SelfAssessmentArtifact",
    "type": "object",
    "required": [
        "assessment_id",
        "assessment_date",
        "created_at",
        "schema_version",
        "status",
        "overall_score",
        "dimensions",
        "findings",
        "recommendations",
        "evidence",
        "run_metadata",
    ],
    "properties": {
        "assessment_id": {
            "type": "string",
            "description": "Unique identifier for the assessment",
            "minLength": 1,
        },
        "assessment_date": {
            "type": "string",
            "format": "date",
            "description": "Date of assessment (ISO 8601)",
        },
        "created_at": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp when artifact was created (ISO 8601)",
        },
        "schema_version": {
            "type": "string",
            "pattern": r"^\d+\.\d+\.\d+$",
            "description": "Schema version in semver format",
            "default": "1.0.0",
        },
        "status": {
            "type": "string",
            "enum": ["ok", "degraded", "failed"],
            "description": "Overall status of the assessment",
            "default": "ok",
        },
        "overall_score": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Overall health score (0.0-1.0)",
            "default": 0.0,
        },
        "dimensions": {
            "type": "object",
            "description": "Individual dimension scores",
            "additionalProperties": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "findings": {
            "type": "array",
            "description": "List of findings from assessment",
            "items": {"type": "string"},
            "default": [],
        },
        "recommendations": {
            "type": "array",
            "description": "List of recommendations",
            "items": {"type": "string"},
            "default": [],
        },
        "evidence": {
            "type": "object",
            "description": "Raw evidence data",
            "default": {},
        },
        "run_metadata": {
            "type": "object",
            "description": "Metadata about the run",
            "default": {},
        },
    },
    "additionalProperties": False,
}

# Schema for CycleResult
CYCLE_RESULT_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CycleResult",
    "type": "object",
    "required": [
        "run_id",
        "started_at",
        "completed_at",
        "status",
        "self_assessment_status",
    ],
    "properties": {
        "run_id": {
            "type": "string",
            "description": "Unique identifier for the cycle run",
        },
        "started_at": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp when cycle started",
        },
        "completed_at": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp when cycle completed",
        },
        "status": {
            "type": "string",
            "enum": ["running", "completed", "failed"],
            "description": "Status of the cycle",
        },
        "self_assessment_status": {
            "type": "string",
            "description": "Status from self-assessment phase",
        },
        "belief_conflicts": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of belief conflicts detected",
            "default": 0,
        },
        "belief_revisions": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of beliefs revised",
            "default": 0,
        },
        "experiments_run": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of experiments executed",
            "default": 0,
        },
        "promotions": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of promotions",
            "default": 0,
        },
        "rejections": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of rejections",
            "default": 0,
        },
        "autonomy_level_before": {
            "type": "string",
            "enum": ["supervised", "assisted", "autonomous"],
            "description": "Autonomy level before cycle",
            "default": "supervised",
        },
        "autonomy_level_after": {
            "type": "string",
            "enum": ["supervised", "assisted", "autonomous"],
            "description": "Autonomy level after cycle",
            "default": "supervised",
        },
        "constitution_violations": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of constitution violations",
            "default": 0,
        },
        "artifact_paths": {
            "type": "object",
            "description": "Paths to generated artifacts",
            "additionalProperties": {"type": "string"},
            "default": {},
        },
        "metrics": {
            "type": "object",
            "description": "Additional metrics from cycle",
            "default": {},
        },
    },
    "additionalProperties": False,
}

# Schema for PolicyResult
POLICY_RESULT_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "PolicyResult",
    "type": "object",
    "required": ["approved"],
    "properties": {
        "approved": {
            "type": "boolean",
            "description": "Whether the decision was approved",
        },
        "reason": {
            "type": "string",
            "description": "Explanation for the decision",
            "default": "",
        },
        "risk_level": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical", "unknown"],
            "description": "Risk level assessed",
            "default": "unknown",
        },
        "requires_approval": {
            "type": "boolean",
            "description": "Whether human approval is required",
            "default": False,
        },
        "approval_timeout": {
            "type": ["integer", "null"],
            "description": "Timeout in seconds for approval",
            "default": None,
        },
        "notify_immediately": {
            "type": "boolean",
            "description": "Whether to notify immediately",
            "default": False,
        },
        "blocked_files": {
            "type": "array",
            "description": "List of files that were blocked",
            "items": {"type": "string"},
            "default": [],
        },
    },
    "additionalProperties": False,
}

# Schema for Health API Response
HEALTH_RESPONSE_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "HealthResponse",
    "type": "object",
    "required": ["success"],
    "properties": {
        "success": {
            "type": "boolean",
            "description": "Whether the request was successful",
        },
        "data": {
            "type": "object",
            "description": "Health data (only if success=True)",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Overall health status",
                },
                "score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Health score (0-100)",
                },
                "components": {
                    "type": "array",
                    "description": "Component health details",
                    "items": {"type": "object"},
                },
            },
        },
        "error": {
            "type": "string",
            "description": "Error message (only if success=False)",
        },
    },
    "additionalProperties": False,
}

# Schema for Qdrant Point
QDRANT_POINT_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "QdrantPoint",
    "type": "object",
    "required": ["id", "vector", "payload"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique point identifier",
        },
        "vector": {
            "type": "array",
            "description": "Embedding vector (384 dimensions for ChiseAI)",
            "items": {"type": "number"},
            "minItems": 384,
            "maxItems": 384,
        },
        "payload": {
            "type": "object",
            "description": "Arbitrary JSON payload",
        },
    },
    "additionalProperties": False,
}

# Schema for Discord Webhook Payload
DISCORD_WEBHOOK_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "DiscordWebhookPayload",
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "maxLength": 2000,
            "description": "Message content (max 2000 chars)",
        },
        "username": {
            "type": "string",
            "description": "Override the webhook username",
        },
        "avatar_url": {
            "type": "string",
            "format": "uri",
            "description": "Override the webhook avatar",
        },
        "embeds": {
            "type": "array",
            "description": "List of embeds",
            "items": {"type": "object"},
        },
    },
    "additionalProperties": False,
}

# InfluxDB Measurement Schema
INFLUXDB_MEASUREMENT_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "InfluxDBMeasurement",
    "type": "object",
    "required": ["measurement", "tags", "fields", "time"],
    "properties": {
        "measurement": {
            "type": "string",
            "description": "Measurement name",
        },
        "tags": {
            "type": "object",
            "description": "Tag set (string key-value pairs)",
            "additionalProperties": {"type": "string"},
        },
        "fields": {
            "type": "object",
            "description": "Field set (numeric or boolean values)",
            "additionalProperties": {
                "anyOf": [
                    {"type": "number"},
                    {"type": "boolean"},
                ]
            },
        },
        "time": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp (ISO 8601)",
        },
    },
    "additionalProperties": False,
}

# Redis Key Pattern
REDIS_KEY_PATTERN_V1 = r"^bmad:chiseai:[a-z_]+(:[a-zA-Z0-9_-]+)*$"

# All schemas
ALL_SCHEMAS = {
    "self_assessment_artifact": SELF_ASSESSMENT_ARTIFACT_SCHEMA_V1,
    "cycle_result": CYCLE_RESULT_SCHEMA_V1,
    "policy_result": POLICY_RESULT_SCHEMA_V1,
    "health_response": HEALTH_RESPONSE_SCHEMA_V1,
    "qdrant_point": QDRANT_POINT_SCHEMA_V1,
    "discord_webhook": DISCORD_WEBHOOK_SCHEMA_V1,
    "influxdb_measurement": INFLUXDB_MEASUREMENT_SCHEMA_V1,
    "redis_key_pattern": REDIS_KEY_PATTERN_V1,
}


def get_schema(name: str) -> dict | str:
    """Get a schema by name.

    Args:
        name: Schema name (one of ALL_SCHEMAS keys)

    Returns:
        Schema dictionary or pattern string

    Raises:
        KeyError: If schema not found
    """
    if name not in ALL_SCHEMAS:
        raise KeyError(
            f"Schema '{name}' not found. Available: {list(ALL_SCHEMAS.keys())}"
        )
    return ALL_SCHEMAS[name]


def validate_with_schema(data: dict, schema_name: str) -> tuple[bool, list[str]]:
    """Validate data against a named schema.

    Args:
        data: Data to validate
        schema_name: Name of schema to validate against

    Returns:
        Tuple of (is_valid, error_messages)
    """
    try:
        from jsonschema import validate, ValidationError

        schema = get_schema(schema_name)
        if isinstance(schema, str):
            # It's a pattern, use regex
            import re

            if not re.match(schema, str(data)):
                return False, [f"Data does not match pattern: {schema}"]
            return True, []

        validate(instance=data, schema=schema)
        return True, []
    except ImportError:
        return False, ["jsonschema package not installed"]
    except ValidationError as e:
        return False, [str(e)]
