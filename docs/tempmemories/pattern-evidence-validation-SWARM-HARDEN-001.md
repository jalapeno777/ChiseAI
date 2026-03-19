---
type: pattern
story_id: SWARM-001
created: 2026-03-19T20:00:00Z
pattern_type: evidence-validation
status: documented
last_updated: 2026-03-19T20:00:00Z
---

# Evidence Validation Patterns - SWARM-HARDEN-001

## Overview
Pattern documentation for evidence-validation failure triage from SWARM-HARDEN-001 remediation.

## Common Failure Patterns

### Pattern 1: Missing Evidence Files
- **Symptom**: Claims of completion without supporting files
- **Detection**: File existence checks fail
- **Resolution**: Require file path verification before completion claims

### Pattern 2: Incorrect File References
- **Symptom**: Evidence files referenced with wrong names/paths
- **Detection**: Path mismatch between claim and actual file
- **Resolution**: Normalize naming conventions (hyphens vs underscores)

### Pattern 3: Uncommitted Changes
- **Symptom**: Evidence exists locally but not committed
- **Detection**: Git status shows modified/untracked files
- **Resolution**: Enforce pre-commit evidence verification

### Pattern 4: Cross-Branch Drift
- **Symptom**: Evidence on wrong branch or not merged
- **Detection**: git branch --contains shows different branch
- **Resolution**: Cross-branch verification before merge claims

### Pattern 5: Schema Violations
- **Symptom**: Evidence files don't match required schema
- **Detection**: Validation scripts fail
- **Resolution**: Schema validation in CI pipeline

## Quick Diagnosis Commands
```bash
# Verify file existence
ls -la <evidence_path>

# Check git containment
git branch --contains <commit>

# Verify commit content
git show <commit> --name-only
```

## Fallback Note
This pattern documentation was created as fallback memory since Redis/Qdrant persistence was unavailable during Phase 7 remediation.
