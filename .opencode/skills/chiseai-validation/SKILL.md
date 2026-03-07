---
name: chiseai-validation
description: Validation patterns and gates for ChiseAI workflows (status sync, compliance, CI).
metadata:
  version: "2.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
---

# chiseai-validation

## Goal

Ensure all changes meet ChiseAI quality and compliance standards before merge.

## When To Use

- Before committing changes
- Before PR creation
- Before merging to main
- CI failure diagnosis

## Validation Layers

### 1. Pre-Commit (Local)
Run via `.opencode/command/chise-precommit-gates.md`:
- Git sanity checks
- Local CI (if available)
- Status sync validation
- Iterloop compliance
- Insight governance compliance
- Metacognition compliance (prediction/outcome/calibration artifacts)

### 2. CI Gates (Woodpecker)
Server-side validation:
- Full test suite
- Security scans
- Status sync (required)
- Required contexts must pass

### 3. Pre-Merge (Merlin)
Final authority checks:
- Green CI verification
- Status file sync confirmed
- PR review completed (if required)

## Status Sync Validation

Every PR adding story implementations MUST:
1. Update `docs/bmm-workflow-status.yaml`
2. Run `python3 scripts/validate_status_sync.py`
3. Pass before merge

## CI Failure Diagnosis

When CI fails:
1. Use `.opencode/command/chise-ci-pr-status.md` - identify failed pipeline
2. Use `.opencode/command/chise-ci-root-cause.md` - extract exact root cause
3. If unresolved, use `.opencode/command/chise-ci-failure-bundle.md`

## Required Evidence

CI failure reports must include:
- `tool` that failed
- `message` (exact error)
- One of: `file:line`, `rule`, or `test`

## Templates

### Template 1: Pre-Commit Validation Checklist

```markdown
# Pre-Commit Validation Checklist

## Story Information
- **Story ID**: [ST-XXX]
- **Branch**: [branch-name]
- **Validator**: [agent-name]
- **Date**: [timestamp]

## Git Sanity Checks
- [ ] `git status -sb` shows clean working tree
- [ ] `git branch --show-current` matches expected branch
- [ ] No unintended files staged
- [ ] Commit messages follow convention

## Code Quality Checks
- [ ] `black --check src/` passes
- [ ] `ruff check src/` passes
- [ ] `mypy src/` passes (or documented exceptions)
- [ ] No new linting errors introduced

## Test Validation
- [ ] `pytest tests/unit/ -v` passes
- [ ] `pytest tests/integration/ -v` passes (if applicable)
- [ ] Coverage maintained or improved
- [ ] No skipped tests without justification

## Status Sync
- [ ] `docs/bmm-workflow-status.yaml` updated
- [ ] `python3 scripts/validate_status_sync.py` passes
- [ ] Story status reflects actual progress

## Iterloop Compliance
- [ ] Iteration started with `chise-iterloop-start`
- [ ] Decisions logged in Redis iterlog
- [ ] Phase 0 completed (if data-dependent)

## Documentation
- [ ] Docstrings added/updated for new functions
- [ ] README updated (if applicable)
- [ ] Changelog updated (if applicable)

## Final Gate
- [ ] All checks passed
- [ ] Ready for commit
- [ ] Ready for PR handoff
```

### Template 2: CI Failure Report

```markdown
# CI Failure Report

## Pipeline Information
- **PR Number**: [#XXX]
- **Branch**: [branch-name]
- **Pipeline ID**: [woodpecker-build-id]
- **Failed At**: [timestamp]

## Failure Summary
- **Stage**: [lint/test/build/deploy]
- **Tool**: [pytest/black/ruff/docker/etc]
- **Exit Code**: [code]

## Root Cause
```
[Paste exact error message here]
```

## Analysis
- **What failed**: [description]
- **Why it failed**: [root cause analysis]
- **First occurrence**: [is this new or recurring?]

## Affected Files
| File | Issue | Line |
|------|-------|------|
| [path] | [issue] | [line#] |

## Resolution Steps
1. [Step 1]
2. [Step 2]
3. [Step 3]

## Verification
- [ ] Fix applied
- [ ] Local reproduction confirmed fix
- [ ] CI re-run passed

## Prevention
- **Pattern**: [What pattern does this follow?]
- **Prevention**: [How to prevent in future]
```

### Template 3: Status Sync Validation Report

```markdown
# Status Sync Validation Report

## Validation Run
- **Story ID**: [ST-XXX]
- **Validator**: [agent-name]
- **Timestamp**: [ISO timestamp]
- **Script Version**: [version]

## Checks Performed

### 1. Workflow Status File
- [ ] File exists: `docs/bmm-workflow-status.yaml`
- [ ] Valid YAML syntax
- [ ] Required fields present

### 2. Story Entry
- [ ] Story entry exists in file
- [ ] Story ID matches PR/branch
- [ ] Status value is valid enum

### 3. Status Consistency
- [ ] Git branch status matches file
- [ ] Implementation status accurate
- [ ] No stale entries

### 4. Cross-References
- [ ] Linked stories exist
- [ ] Dependencies satisfied
- [ ] Epic reference valid

## Discrepancies Found
| Expected | Actual | File | Line |
|----------|--------|------|------|
| [value] | [value] | [path] | [line] |

## Resolution Required
1. [Action item 1]
2. [Action item 2]

## Gate Decision
- [ ] PASS - Status sync valid
- [ ] FAIL - Requires updates listed above
```

### Template 4: Pre-Merge Authorization

```markdown
# Pre-Merge Authorization

## PR Information
- **PR Number**: [#XXX]
- **Title**: [title]
- **Author**: [agent]
- **Target Branch**: main
- **Source Branch**: [feature/branch]

## Validation Summary

### CI Status
- [ ] All CI checks passed
- [ ] No failing contexts
- [ ] Pipeline duration: [time]

### Code Review
- [ ] Review completed
- [ ] All comments addressed
- [ ] Approval received (if required)

### Quality Gates
- [ ] Tests: [passed/total]
- [ ] Coverage: [percentage]
- [ ] Linting: clean
- [ ] Security scan: clean

### Status Sync
- [ ] `docs/bmm-workflow-status.yaml` updated
- [ ] Validation script passed
- [ ] Story marked complete

### Documentation
- [ ] Docstrings complete
- [ ] Changelog updated
- [ ] Breaking changes documented

## Merge Authorization
- **Authorized By**: [merlin]
- **Authorization Time**: [timestamp]
- **Merge Method**: [squash/merge/rebase]

## Post-Merge Tasks
- [ ] Delete source branch
- [ ] Update story status to 'merged'
- [ ] Notify stakeholders
```

## Examples

### Example 1: Successful Pre-Commit Validation

**Context**: Senior-dev completing feature ST-DSL-042

**Validation Run**:

```markdown
# Pre-Commit Validation Checklist

## Story Information
- Story ID: ST-DSL-042
- Branch: feature/ST-DSL-042-grammar-extensions
- Validator: senior-dev
- Date: 2026-02-23T14:30:00Z

## Git Sanity Checks
- [x] git status -sb shows clean working tree
- [x] git branch --show-current: feature/ST-DSL-042-grammar-extensions
- [x] Only intended files staged
- [x] Commit message: "feat(dsl): add trailing_stop syntax support (ST-DSL-042)"

## Code Quality Checks
- [x] black --check src/ passed
- [x] ruff check src/ passed (0 errors)
- [x] mypy src/ passed (strict mode)

## Test Validation
- [x] pytest tests/unit/ -v: 45 passed, 0 failed
- [x] Coverage: 87% (maintained)
- [x] No skipped tests

## Status Sync
- [x] docs/bmm-workflow-status.yaml updated
- [x] python3 scripts/validate_status_sync.py: PASS

## Gate Decision: PASS - Ready for PR handoff
```

**Outcome**: Handed off to Jarvis for merlin delegation. PR created and merged successfully.

### Example 2: CI Failure Diagnosis

**Context**: CI failed on PR #234 for linting

**Failure Report**:

```markdown
# CI Failure Report

## Pipeline Information
- PR Number: #234
- Branch: feature/ST-EVOLUTION-001
- Pipeline ID: woodpecker-1234
- Failed At: 2026-02-23T10:15:00Z

## Failure Summary
- Stage: lint
- Tool: ruff
- Exit Code: 1

## Root Cause
```
src/neuro_symbolic/evolution/engine.py:45:9: F821 Undefined name 'mutation_rate'
src/neuro_symbolic/evolution/engine.py:52:14: F841 Local variable 'fitness' assigned but never used
```

## Analysis
- **What failed**: Undefined variable and unused variable
- **Why it failed**: Refactoring removed variable definition but kept usage
- **First occurrence**: New failure

## Affected Files
| File | Issue | Line |
|------|-------|------|
| src/neuro_symbolic/evolution/engine.py | Undefined name 'mutation_rate' | 45 |
| src/neuro_symbolic/evolution/engine.py | Unused variable 'fitness' | 52 |

## Resolution Steps
1. Add `mutation_rate` parameter to function signature
2. Remove or use `fitness` variable

## Verification
- [x] Fix applied
- [x] Local ruff check passed
- [x] CI re-run passed

## Prevention
- Pattern: Incomplete refactoring
- Prevention: Run linter before commit
```

**Outcome**: Fix applied, CI passed on re-run.

### Example 3: Status Sync Validation Failure

**Context**: PR ready but status sync validation failing

**Validation Report**:

```markdown
# Status Sync Validation Report

## Validation Run
- Story ID: ST-DSL-042
- Validator: merlin
- Timestamp: 2026-02-23T15:00:00Z

## Checks Performed

### 2. Story Entry
- [x] Story entry exists in file
- [x] Story ID matches PR/branch
- [ ] Status value is valid enum ❌

## Discrepancies Found
| Expected | Actual | File | Line |
|----------|--------|------|------|
| 'in_progress' or 'complete' | 'wip' | bmm-workflow-status.yaml | 42 |

## Resolution Required
1. Change status from 'wip' to 'in_progress' or 'complete'
2. Re-run validation script

## Gate Decision: FAIL - Requires status update
```

**Resolution**: Updated status to 'complete', re-ran validation, passed.

## Quick Reference

### Validation Command Sequence

```bash
# Pre-commit validation
git status -sb
black --check src/
ruff check src/
pytest tests/unit/ -v
python3 scripts/validate_status_sync.py

# If CI fails
python3 scripts/swarm/ci_pr_status.py --pr [number]
python3 scripts/swarm/ci_root_cause.py --pr [number]
```

### Common CI Failures & Fixes

| Failure | Cause | Fix |
|---------|-------|-----|
| Black failed | Formatting | `black src/` |
| Ruff failed | Lint error | Fix specific issues |
| Pytest failed | Test failure | Fix test or code |
| Status sync failed | Missing update | Update workflow-status.yaml |
| Mypy failed | Type error | Add types or ignore |

### Validation Gate Flow

```
[Code Changes]
     ↓
[Local Pre-Commit] → Fix if needed
     ↓
[Push to Branch]
     ↓
[CI Pipeline] → Diagnose if fails
     ↓
[Status Sync] → Update if needed
     ↓
[Pre-Merge Auth] → Merlin only
     ↓
[Merge to Main]
```

## When Not To Use

- Read-only operations with no state changes
- External system validation (use appropriate tools)
- Non-repo file validation
- Performance testing (use dedicated performance tools)

## Exit Conditions

- Pre-commit gates passed locally.
- CI green on remote.
- Status sync validated.
- All required contexts passing.

## Troubleshooting/Safety

- **Pre-commit fails**: Fix locally before pushing; do not bypass.
- **CI timeout**: Check for infinite loops or resource issues.
- **Status sync mismatch**: Update workflow status file to match actual state.
- **Flaky tests**: Isolate and fix; do not mark as passing without resolution.

## Related Skills

- `chiseai-git-workflow` - Git operations and PR workflow
- `chiseai-branch-hygiene` - Branch state validation
- `chiseai-incident-response` - Handle validation failures

## Related Commands

- `.opencode/command/chise-precommit-gates.md`
- `.opencode/command/chise-ci-pr-status.md`
- `.opencode/command/chise-ci-root-cause.md`
- `.opencode/command/chise-ci-failure-bundle.md`
