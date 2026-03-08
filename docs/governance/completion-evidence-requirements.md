# Completion Evidence Requirements

> **Incident**: GOV-BATCH-003-STATUS-FALSIFICATION
> **Created**: 2026-03-08
> **Purpose**: Prevent stories from being marked as "completed" without proper PR/merge evidence

## Overview

This document defines the **mandatory evidence requirements** for marking a story as "completed" or "merged" in the ChiseAI workflow status file (`docs/bmm-workflow-status.yaml`).

These requirements were established in response to **incident GOV-BATCH-003-STATUS-FALSIFICATION**, where stories were incorrectly marked as completed without any PR merge evidence.

## Required Evidence Fields

When marking a story with status `completed` or `merged`, the following fields are **mandatory**:

### 1. `pr_number` (Required)

The GitHub Pull Request number that was merged to complete the story.

**Example:**
```yaml
- id: ST-EXAMPLE-001
  status: completed
  pr_number: 383
```

**Alternative for multi-PR stories:**
```yaml
- id: ST-EXAMPLE-002
  status: completed
  remediation_pr_numbers:
    - 407
    - 408
    - 410
```

### 2. `merge_commit` (Required)

The SHA hash of the merge commit that integrated the PR into main.

**Example:**
```yaml
- id: ST-EXAMPLE-001
  status: completed
  pr_number: 383
  merge_commit: 8bf1c7b
```

**Alternative for multi-commit stories:**
```yaml
- id: ST-EXAMPLE-002
  status: completed
  merge_commits:
    - 48725e8068161d60222eaaf154a499781e00a268
    - 56fb76ee36cd9d900a5aec4870d47280334efe95
    - 0ce77cf31d9fde4ae207fd755992ad67b5cb16e9
```

### 3. Branch Verification (Automatic)

The validation script automatically verifies that the `merge_commit` exists on the `main` branch using:

```bash
git branch --contains <merge_commit>
```

This prevents false claims that a commit was merged when it only exists on a feature branch.

## Validation Process

### Automatic Validation

The pre-commit hook `.githooks/pre-commit-status-guardrail` automatically validates completion evidence when you commit changes to `docs/bmm-workflow-status.yaml`.

**Validation checks:**
1. Story has `pr_number` (or `remediation_pr_numbers`)
2. Story has `merge_commit` (or `merge_commits`)
3. Commit is verifiable on main branch via `git branch --contains`

### Manual Validation

You can manually validate the status file:

```bash
# Validate entire status file
python3 scripts/validate_completion_evidence.py

# Validate specific story
python3 scripts/validate_completion_evidence.py --story-id ST-EXAMPLE-001

# Verbose output (show valid completions)
python3 scripts/validate_completion_evidence.py --verbose

# JSON output
python3 scripts/validate_completion_evidence.py --json
```

## Examples

### ✅ Valid Completion (Single PR)

```yaml
- id: LLM-PROVIDER-FIX-001
  status: merged
  pr_number: 383
  merge_commit: 8bf1c7b
  branch: feature/LLM-PROVIDER-FIX-001-consolidation
  title: LLM Provider Infrastructure Remediation
  # ... other fields ...
```

**Validation:**
- ✅ Has `pr_number`: 383
- ✅ Has `merge_commit`: 8bf1c7b
- ✅ Commit verified on main (via `git branch --contains`)

### ✅ Valid Completion (Multi-PR)

```yaml
- id: AUDIT-DELTA-FIX-001
  status: completed
  remediation_pr_numbers:
    - 407
    - 408
    - 410
  merge_commits:
    - 48725e8068161d60222eaaf154a499781e00a268
    - 56fb76ee36cd9d900a5aec4870d47280334efe95
    - 0ce77cf31d9fde4ae207fd755992ad67b5cb16e9
  title: AUDIT-DELTA Remediation
  # ... other fields ...
```

**Validation:**
- ✅ Has `remediation_pr_numbers`: [407, 408, 410]
- ✅ Has `merge_commits`: [...]
- ✅ At least one commit verified on main

### ❌ Invalid Completion (Missing Evidence)

```yaml
- id: ST-EXAMPLE-003
  status: completed
  title: Example Story Without Evidence
  # Missing: pr_number
  # Missing: merge_commit
```

**Validation fails with:**
```
❌ ST-EXAMPLE-003: Missing required field: pr_number; Missing required field: merge_commit
```

### ❌ Invalid Completion (Commit Not on Main)

```yaml
- id: ST-EXAMPLE-004
  status: completed
  pr_number: 999
  merge_commit: abc123  # Only exists on feature branch
  title: Example Story With False Merge Claim
```

**Validation fails with:**
```
❌ ST-EXAMPLE-004: Commit abc123 not found on main/master branch. Branches containing commit: feature/ST-EXAMPLE-004
```

## Status Values Requiring Evidence

Only these status values require completion evidence:

- `completed`
- `merged`

Other status values do **not** require evidence:
- `in_progress`
- `planned`
- `blocked`
- `pending_manual_verification`
- `needs_verification`
- `implementation_complete_pending_merge`

## Emergency Bypass

In rare emergency situations, you can bypass the validation:

```bash
git commit --no-verify -m "Update status - BYPASS JUSTIFICATION: <reason>"
```

**Requirements for bypass:**
1. Must include justification in commit message
2. Must document reason in story notes
3. Must follow up with proper evidence within 24 hours
4. Incident must be logged if bypass was incorrect

## Integration with CI/CD

### Pre-Commit Hook Installation

To install the pre-commit hook:

```bash
# Option 1: Configure git to use .githooks directory
git config core.hooksPath .githooks

# Option 2: Symlink to standard .git/hooks
ln -s ../../.githooks/pre-commit-status-guardrail .git/hooks/pre-commit
```

### CI Pipeline Validation

Add to CI pipeline to validate on every push:

```yaml
# .woodpecker.yml or equivalent
pipeline:
  validate-completion-evidence:
    image: python:3.11
    commands:
      - pip install pyyaml
      - python3 scripts/validate_completion_evidence.py
    when:
      path: "docs/bmm-workflow-status.yaml"
```

## Troubleshooting

### Error: "Commit not found on main"

**Cause**: The `merge_commit` SHA only exists on a feature branch, not main.

**Solution**:
1. Verify the PR was actually merged: `gh pr view <pr_number>`
2. Get the correct merge commit SHA: `git log --oneline --merges main | head`
3. Update `merge_commit` field with correct SHA
4. Re-run validation

### Error: "Missing required field: pr_number"

**Cause**: Story marked as completed but no PR was created/merged.

**Solution**:
1. If work is complete but not merged: Create PR and get it merged first
2. If work is in progress: Change status to `in_progress` or `implementation_complete_pending_merge`
3. Never mark as `completed` until PR is merged to main

### Error: "Stories marked as completed without proper evidence"

**Cause**: The validation script found invalid completions.

**Solution**: Review the detailed error messages and fix each invalid story:
```bash
python3 scripts/validate_completion_evidence.py --verbose
```

## Related Documents

- **Incident Report**: `docs/incidents/GOV-BATCH-003-STATUS-FALSIFICATION.md`
- **Workflow Status**: `docs/bmm-workflow-status.yaml`
- **Git Workflow**: `.opencode/skills/chiseai-git-workflow/SKILL.md`
- **Cross-Branch Verification**: `docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md`

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-03-08 | Initial creation in response to GOV-BATCH-003 incident | Dev (Task 3) |

---

**Remember**: A story is not complete until it is merged to main. Implementation alone is not sufficient.
