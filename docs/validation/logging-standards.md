# Evidence Logging Standards

This document defines the structured JSON logging format for evidence files in the ChiseAI validation system.

## Overview

Evidence files provide structured proof of story completion, test results, and system validation. All evidence files MUST follow the JSON Schema defined in `docs/validation/evidence-schema.json`.

## Base Evidence Schema

All evidence files MUST include these required fields:

```json
{
  "story_id": "ST-XXX",
  "timestamp": "2026-03-17T10:00:00Z",
  "evidence_type": "test_results",
  "summary": "Brief description of what this evidence demonstrates"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `story_id` | string | Story identifier (pattern: `^[A-Z]+-[A-Z0-9-]+$`) |
| `timestamp` | string | ISO 8601 datetime (e.g., `2026-03-17T10:00:00Z`) |
| `evidence_type` | string | One of: `test_results`, `merge_verification`, `performance_benchmark`, `architecture_design`, `security_audit`, `code_review`, `validation_report`, `incident_response`, `manual_verification` |
| `summary` | string | Brief description (10-500 characters) |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Overall status: `SUCCESS`, `FAILURE`, `PARTIAL`, `PENDING`, `SKIPPED` |
| `data` | object | Evidence-specific data container |
| `metadata` | object | Additional metadata (see below) |
| `validation` | object | Validation results (see below) |

## Metadata Schema

```json
{
  "metadata": {
    "collector": "agent-name-or-system",
    "source": "source-system-or-component",
    "version": "1.0.0",
    "tags": ["tag1", "tag2", "tag3"]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `collector` | string | Name/ID of the agent or system that collected the evidence |
| `source` | string | Source system or component |
| `version` | string | Schema or evidence format version |
| `tags` | array | Tags for categorization and filtering |

## Validation Schema

```json
{
  "validation": {
    "validated_by": "validator-name",
    "validated_at": "2026-03-17T10:05:00Z",
    "result": "PASS"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `validated_by` | string | Name/ID of the validator |
| `validated_at` | string | ISO 8601 timestamp of validation |
| `result` | string | `PASS`, `FAIL`, or `WARNING` |

## Evidence Types

### 1. Test Results Evidence

For test execution results, use the `test_results` evidence type with the `test-evidence.json` schema extension.

**Required Additional Fields:**

```json
{
  "evidence_type": "test_results",
  "test_results": [
    {
      "test_name": "test_schema_validation",
      "status": "passed",
      "duration_ms": 45.2,
      "message": "Schema validates correctly",
      "file_path": "tests/unit/validation/test_schemas.py",
      "line_number": 42
    }
  ],
  "coverage": {
    "overall": 87.5,
    "by_module": {
      "validation": 92.0,
      "evidence": 85.5
    },
    "lines_covered": 420,
    "lines_total": 480,
    "branches_covered": 85,
    "branches_total": 100
  },
  "pass_rate": 100.0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `test_results` | array | Array of individual test results |
| `test_results[].test_name` | string | Name of the test |
| `test_results[].status` | string | `passed`, `failed`, `skipped`, `error` |
| `test_results[].duration_ms` | number | Test execution duration in milliseconds |
| `test_results[].message` | string | Test output or error details |
| `test_results[].file_path` | string | Path to test file |
| `test_results[].line_number` | integer | Line number in test file |
| `coverage` | object | Code coverage metrics |
| `coverage.overall` | number | Overall coverage percentage (0-100) |
| `coverage.by_module` | object | Coverage breakdown by module |
| `pass_rate` | number | Percentage of tests that passed (0-100) |

### 2. Merge Verification Evidence

For merge verification data:

```json
{
  "evidence_type": "merge_verification",
  "data": {
    "pr_number": 123,
    "merge_commit": "abc123def456",
    "target_branch": "main",
    "source_branch": "feature/ST-XXX-description",
    "merged_at": "2026-03-17T10:00:00Z",
    "merged_by": "merlin",
    "ci_status": "passed",
    "tests_passed": true,
    "review_approved": true
  }
}
```

### 3. Performance Benchmark Evidence

For performance benchmarks:

```json
{
  "evidence_type": "performance_benchmark",
  "data": {
    "benchmark_name": "signal_generation_latency",
    "metrics": {
      "mean_ms": 45.2,
      "p50_ms": 42.0,
      "p95_ms": 78.5,
      "p99_ms": 120.3,
      "min_ms": 35.1,
      "max_ms": 250.8
    },
    "iterations": 1000,
    "duration_sec": 60
  }
}
```

### 4. Architecture Design Evidence

For architecture design documents, use the `architecture-evidence.json` schema extension.

```json
{
  "evidence_type": "architecture_design",
  "data": {
    "design_id": "ARCH-001",
    "components": ["component1", "component2"],
    "diagrams": ["docs/diagrams/arch-001.svg"],
    "decisions": [
      {
        "id": "ADR-001",
        "title": "Decision title",
        "status": "accepted",
        "rationale": "Why this decision was made"
      }
    ]
  }
}
```

### 5. Security Audit Evidence

For security audit results:

```json
{
  "evidence_type": "security_audit",
  "data": {
    "scan_type": "bandit",
    "findings": [
      {
        "severity": "high",
        "category": "sql_injection",
        "file": "src/api/routes.py",
        "line": 42,
        "message": "Possible SQL injection vector"
      }
    ],
    "total_findings": 0,
    "critical_count": 0,
    "high_count": 0,
    "medium_count": 0,
    "low_count": 0
  }
}
```

### 6. Code Review Evidence

For code review documentation:

```json
{
  "evidence_type": "code_review",
  "data": {
    "reviewer": "senior-dev",
    "pr_number": 123,
    "comments_count": 5,
    "issues_found": [
      {
        "severity": "minor",
        "file": "src/module.py",
        "line": 42,
        "message": "Consider adding type hints"
      }
    ],
    "approved": true
  }
}
```

### 7. Validation Report Evidence

For general validation reports:

```json
{
  "evidence_type": "validation_report",
  "data": {
    "validation_type": "e2e",
    "checks": [
      {
        "name": "database_connection",
        "status": "passed",
        "duration_ms": 150
      }
    ],
    "summary": {
      "total": 10,
      "passed": 10,
      "failed": 0
    }
  }
}
```

### 8. Incident Response Evidence

For incident documentation:

```json
{
  "evidence_type": "incident_response",
  "data": {
    "incident_id": "INC-2026-001",
    "severity": "P1",
    "started_at": "2026-03-17T09:00:00Z",
    "resolved_at": "2026-03-17T09:30:00Z",
    "duration_min": 30,
    "root_cause": "Database connection pool exhausted",
    "resolution": "Increased connection pool size and added monitoring"
  }
}
```

### 9. Manual Verification Evidence

For manual verification results:

```json
{
  "evidence_type": "manual_verification",
  "data": {
    "verifier": "qa-team-member",
    "verification_steps": [
      {
        "step": 1,
        "description": "Log in to system",
        "status": "passed"
      }
    ],
    "environment": "staging",
    "notes": "All manual tests passed successfully"
  }
}
```

## File Naming Convention

Evidence files MUST follow this naming pattern:

```
docs/evidence/{STORY-ID}-{descriptor}.{ext}
```

- `{STORY-ID}`: Uppercase story identifier (e.g., `ST-CONTROL-001`)
- `{descriptor}`: Short hyphenated description (optional)
- `{ext}`: File extension (`.json` or `.md`)

Examples:
- `docs/evidence/ST-CONTROL-001-live-data-evidence.json`
- `docs/evidence/STRONG-001-A-S3-completion-evidence.json`

## Validation

Validate evidence files using the schema validator:

```bash
# Validate a single file
python3 scripts/validation/validate_evidence_schema.py --file docs/evidence/ST-XXX-evidence.json

# Validate all evidence for a story
python3 scripts/validation/validate_evidence_schema.py --story-id ST-XXX

# Validate all evidence files
python3 scripts/validation/validate_evidence_schema.py --all

# CI mode (warnings only)
python3 scripts/validation/validate_evidence_schema.py --all --ci-mode

# JSON output for programmatic use
python3 scripts/validation/validate_evidence_schema.py --all --json-output
```

## CI Integration

To integrate evidence validation into CI:

1. **Warning Mode (Initial Phase)**
   ```yaml
   - name: Validate Evidence Schema
     run: python3 scripts/validation/validate_evidence_schema.py --all --ci-mode
   ```

2. **Blocking Mode (After Stabilization)**
   ```yaml
   - name: Validate Evidence Schema
     run: python3 scripts/validation/validate_evidence_schema.py --all
   ```

## Best Practices

1. **Timestamps**: Use ISO 8601 format with timezone (e.g., `2026-03-17T10:00:00Z`)
2. **Story IDs**: Match the story ID exactly as defined in the workflow status
3. **Consistency**: Use consistent field naming (snake_case preferred)
4. **Completeness**: Include all required fields for the evidence type
5. **Validation**: Run the validator before committing evidence files
6. **Immutability**: Once created, evidence files should not be modified
7. **Versioning**: Use timestamps or version suffixes for updates

## Schema Evolution

When adding new evidence types:

1. Add the type to `evidence-schema.json` enum
2. Create a type-specific schema in `docs/validation/evidence-types/`
3. Update this document
4. Update the validator if needed
5. Provide sample evidence files

## Related Documents

- [Evidence Policy](./evidence-policy.md)
- [Validation Registry](./validation-registry.yaml)
- [Evidence Schema](../evidence-schema.json)
- [Evidence Types](../evidence-types/)
