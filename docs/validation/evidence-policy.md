# Per-Story Evidence File Policy

## Overview

This document defines the conventions and requirements for evidence files that accompany stories in the ChiseAI workflow system.

## Naming Convention

Evidence files MUST follow this naming pattern:

```
docs/evidence/{STORY-ID}-{descriptor}.{ext}
```

Where:
- `{STORY-ID}`: The uppercase story identifier (e.g., `ST-CONTROL-001`, `STRONG-001-A-S3`)
- `{descriptor}`: A short hyphenated description of the evidence content (optional for single evidence files)
- `{ext}`: File extension, must be one of:
  - `.json` - Structured evidence data
  - `.md` - Markdown documentation/evidence

### Examples

✅ **Valid evidence files:**
- `docs/evidence/ST-CONTROL-001-live-data-evidence.json`
- `docs/evidence/STRONG-001-A-S3-completion-evidence.json`
- `docs/evidence/STABILIZE-001-health-endpoint.json`
- `docs/evidence/PARTY-MODE-AUDIT-REPORT-BRAINEVAL-CI.md`

❌ **Invalid evidence files:**
- `docs/evidence/control-001.json` (missing ST- prefix in ID)
- `docs/evidence/ST-CONTROL-001-evidence.txt` (unsupported extension)
- `docs/evidence/evidence-for-ST-CONTROL-001.json` (wrong order)
- `docs/evidence/001-ST-CONTROL.json` (ID not at start)

## Requirements

### Minimum Evidence

Each story MUST have at least one evidence file in `docs/evidence/`.

### Evidence Content Guidelines

#### JSON Evidence Files

JSON evidence files should include:

```json
{
  "story_id": "ST-XXX",
  "timestamp": "2026-03-16T00:00:00Z",
  "evidence_type": "test_results|merge_verification|performance_benchmark",
  "summary": "Brief description of what this evidence demonstrates",
  "data": {
    // Evidence-specific data
  }
}
```

#### Markdown Evidence Files

Markdown evidence files should include:

```markdown
# Evidence: {STORY-ID} - {Title}

**Story ID:** {STORY-ID}  
**Timestamp:** 2026-03-16T00:00:00Z  
**Evidence Type:** {type}

## Summary

Brief description of what this evidence demonstrates.

## Details

...
```

## Validation

Use the validation script to check evidence file compliance:

```bash
# Validate a single story
python3 scripts/validation/validate_story_evidence.py --story-id ST-CONTROL-001

# Validate all stories
python3 scripts/validation/validate_story_evidence.py --all

# Verbose output
python3 scripts/validation/validate_story_evidence.py --all --verbose
```

### Exit Codes

- `0` - All stories have required evidence files
- `1` - One or more stories lack evidence files
- `2` - Configuration or parsing errors

## Directory Structure

```
docs/evidence/
├── {STORY-ID}-*.json          # JSON evidence files
├── {STORY-ID}-*.md            # Markdown evidence files
├── {STORY-ID}/                # Optional: Story-specific subdirectory
│   └── additional-evidence.json
└── EVIDENCE-INDEX.md          # Optional: Index of all evidence files
```

## Evidence Types

Common evidence types include:

| Type | Description | Example Filename |
|------|-------------|------------------|
| `completion-evidence` | Proof of story completion | `ST-XXX-completion-evidence.json` |
| `test-results` | Test execution results | `ST-XXX-test-results.json` |
| `merge-evidence` | Merge verification data | `ST-XXX-merge-evidence.json` |
| `live-data` | Live system validation | `ST-XXX-live-data-evidence.json` |
| `audit-report` | Audit findings | `ST-XXX-audit-report.md` |
| `benchmark` | Performance benchmarks | `ST-XXX-benchmark-results.json` |
| `validation` | Validation reports | `ST-XXX-validation-report.md` |

## Integration with Workflow Status

Evidence files complement the workflow status file (`docs/bmm-workflow-status.yaml`).
Stories in the `completed` or `merged` status should reference their evidence files:

```yaml
completed:
  - id: ST-CONTROL-001
    status: completed
    evidence_file: docs/evidence/ST-CONTROL-001-live-data-evidence.json
    # or
    evidence_files:
      - docs/evidence/ST-CONTROL-001-live-data-evidence.json
      - docs/evidence/ST-CONTROL-001-test-results.json
```

## Best Practices

1. **Use descriptive filenames** - Include what the evidence demonstrates
2. **Include timestamps** - Evidence should indicate when it was collected
3. **Keep evidence immutable** - Once created, evidence files should not be modified
4. **Version evidence if needed** - Use timestamps or version suffixes for updates
5. **Reference in workflow status** - Link evidence files in the workflow status YAML

## Enforcement

This policy is enforced by:

1. **Pre-commit hooks** - Validate evidence files before commit
2. **CI pipeline** - Run `validate_story_evidence.py --all` in CI
3. **PR review** - Reviewers should verify evidence files exist

## Exceptions

Exceptions to this policy require:
1. Written justification in the PR description
2. Approval from a senior team member
3. Documentation in `docs/validation/evidence-exceptions.md`

## Related Documents

- [Workflow Status File](../bmm-workflow-status.yaml)
- [Validation Registry](./validation-registry.yaml)
- `scripts/validation/validate_story_evidence.py`
