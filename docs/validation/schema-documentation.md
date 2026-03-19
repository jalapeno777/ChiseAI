# Evidence Schema Documentation

## Overview

The ChiseAI Evidence Schema defines the structure for all evidence files in the validation system. This schema ensures consistency, traceability, and automated validation across all verification activities.

**Schema Version:** 1.0.0  
**JSON Schema Draft:** Draft 7  
**Schema File:** `docs/validation/evidence-schema.json`

## Purpose

Evidence files provide structured proof that:
- Acceptance criteria have been met
- Quality gates have passed
- Decisions have been validated
- Risks have been assessed

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `story_id` | string | The story ID this evidence supports. Format: XXX-YYY-N or XXX-N |
| `timestamp` | string (ISO 8601) | When the evidence was generated |
| `evidence_type` | string | Classification: unit_test, integration_test, e2e_test, validation_run, audit, review, manual_verification, metrics_snapshot, kpi_report |
| `validation_results` | object | Container for all validation checks |

## Field Descriptions

### `story_id`
- **Type:** `string`
- **Pattern:** `^[A-Z]+-[0-9A-Z]+-[0-9A-Z]+$|^[A-Z]+-[0-9]+$`
- **Examples:** `GOV-002-A`, `ST-123`, `CH-456`
- **Description:** Links the evidence to a specific story. The story ID format allows for hierarchical categorization (e.g., GOV for governance, ST for stories).

### `timestamp`
- **Type:** `string`
- **Format:** ISO 8601 date-time
- **Examples:** `2026-03-16T12:00:00Z`, `2026-03-16T12:00:00+00:00`
- **Description:** When the evidence was generated. Should be set when the evidence file is created, not when the validation occurred (use individual check timestamps for that).

### `evidence_type`
- **Type:** `string`
- **Enum:**
  - `unit_test` - Automated unit test results
  - `integration_test` - Integration test results
  - `e2e_test` - End-to-end test results
  - `validation_run` - Formal validation execution
  - `audit` - Audit trail evidence
  - `review` - Code or design review outcomes
  - `manual_verification` - Human-verified results
  - `metrics_snapshot` - Performance or metrics capture
  - `kpi_report` - Key performance indicator measurements
- **Description:** Classifies the evidence for filtering, routing, and reporting purposes.

### `validation_results`
- **Type:** `object`
- **Description:** Contains all validation checks. Each key is a check name, and the value is an object describing the result.

#### Validation Check Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `passed` | boolean | Yes | Whether this check passed |
| `description` | string | No | Human-readable description |
| `rationale` | string | No | Explanation, especially for failures |
| `severity` | string | No | `critical`, `high`, `medium`, `low`, `info` |
| `timestamp` | string | No | ISO 8601 timestamp for this specific check |
| `metadata` | object | No | Additional context (structure varies by check) |

## Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `all_passed` | boolean | Convenience flag: true if all validation_results passed |
| `agent` | string | Name of the agent/system that generated evidence |
| `environment` | string | Where validation was performed: local, ci, staging, paper, live |
| `version` | string | Schema version (default: "1.0.0") |
| `metadata` | object | Additional context (branch, commit, duration_ms, tags) |

## Example Evidence File

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "story_id": "GOV-002-A",
  "timestamp": "2026-03-16T12:00:00Z",
  "evidence_type": "validation_run",
  "agent": "dev",
  "environment": "local",
  "version": "1.0.0",
  "all_passed": true,
  "validation_results": {
    "schema_validity": {
      "passed": true,
      "description": "Schema validates against JSON Schema Draft 7",
      "severity": "critical",
      "timestamp": "2026-03-16T12:00:00Z"
    },
    "required_fields_present": {
      "passed": true,
      "description": "All required fields are present and valid",
      "severity": "critical"
    },
    "type_constraints": {
      "passed": true,
      "description": "All fields have correct types",
      "severity": "high"
    }
  },
  "metadata": {
    "branch": "feature/GOV-002-A-evidence-schema-base",
    "commit": "abc123def456",
    "duration_ms": 150,
    "tags": ["schema", "validation", "governance"]
  }
}
```

## Validation Instructions

### 1. Validate Against Meta-Schema

To validate that the schema itself is valid JSON Schema Draft 7:

```bash
python3 -c "
import json
import jsonschema

# Load the schema
with open('docs/validation/evidence-schema.json', 'r') as f:
    schema = json.load(f)

# Validate against Draft 7 meta-schema
jsonschema.Draft7Validator.check_schema(schema)
print('Schema is valid JSON Schema Draft 7')
"
```

### 2. Validate Evidence Files

To validate an evidence file against the schema:

```bash
python3 -c "
import json
import jsonschema

# Load the schema
with open('docs/validation/evidence-schema.json', 'r') as f:
    schema = json.load(f)

# Load the evidence
with open('docs/validation/evidence/my-evidence.json', 'r') as f:
    evidence = json.load(f)

# Validate
validator = jsonschema.Draft7Validator(schema)
errors = list(validator.iter_errors(evidence))

if errors:
    for error in errors:
        print(f'Error: {error.message}')
        print(f'Path: {list(error.path)}')
        print()
else:
    print('Evidence file is valid!')
"
```

### 3. Programmatic Validation

```python
import json
import jsonschema
from jsonschema import Draft7Validator

def validate_evidence(evidence_path: str, schema_path: str = "docs/validation/evidence-schema.json") -> tuple[bool, list]:
    """
    Validate an evidence file against the schema.
    
    Returns:
        (is_valid, list_of_errors)
    """
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    with open(evidence_path, 'r') as f:
        evidence = json.load(f)
    
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(evidence))
    
    return len(errors) == 0, errors

# Usage
is_valid, errors = validate_evidence("docs/validation/evidence/my-evidence.json")
if not is_valid:
    for error in errors:
        print(f"{error.message} at {list(error.path)}")
```

## Schema Versioning

- **Current:** 1.0.0
- **Format:** Semantic versioning (MAJOR.MINOR.PATCH)
- **MAJOR:** Breaking changes to required fields
- **MINOR:** New optional fields, non-breaking changes
- **PATCH:** Bug fixes, clarifications

## Extension Guidelines

To create a specialized evidence schema:

1. **Inherit from base:** Reference the base schema and extend
2. **Add story-specific fields:** Under `metadata` or as top-level optional fields
3. **Document:** Update this documentation with your extensions
4. **Version:** Use a higher minor version number

### Example Extension

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "allOf": [
    { "$ref": "https://chise.ai/schemas/evidence-base.json" }
  ],
  "properties": {
    "test_results": {
      "type": "array",
      "description": "Detailed test results (e2e-specific)"
    }
  }
}
```

## Related Files

- `docs/validation/evidence-schema.json` - The schema definition
- `docs/validation/validation-registry.yaml` - Central validation tracking
- `docs/validation/evidence-policy.md` - Evidence management policies
- `docs/validation/evidence/` - Evidence file storage directory

## Compliance

All evidence files must:
- Validate against this schema
- Be stored in `docs/validation/evidence/`
- Follow the naming convention: `{STORY-ID}-{timestamp}-{type}.json`
- Be committed to version control
- Be referenced in the validation registry (for formal validations)
