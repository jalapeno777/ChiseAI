---
title: Evidence-Validation Failure Triage Runbook
story_id: SWARM-HARDEN-001
version: 1.0.0
last_updated: 2026-03-19
---

## Quick Diagnosis Flowchart

Worker claims completion → Check file existence proof provided?

NO → REJECT completion, request: `git show <commit> --name-only`

YES → Verify each claimed file exists in commit output

File missing? → INCIDENT: False completion claim

All files present? → Check cross-branch verification

`git branch --contains <commit>` shows main? → PASS

Does NOT show main? → REJECT: Work not actually merged

## Common Failure Patterns

### Pattern 1: Missing File Existence Proof
**Symptom**: Worker reports completion but no `git show` output provided
**Root Cause**: Worker unaware of requirement or skipped verification
**Fix**: Request immediate proof with: `git show <sha> --name-only`
**Prevention**: Enforce in worker contracts; reject completions without proof

### Pattern 2: File Claimed But Not In Commit
**Symptom**: `git show` output doesn't list claimed file
**Root Cause**: File was staged but not committed; or wrong commit SHA
**Fix**: 
1. Check working tree: `git status`
2. If uncommitted changes: `git add . && git commit --amend`
3. Update completion report with new SHA
**Prevention**: Workers must run `git show` before claiming completion

### Pattern 3: False Merge Claim
**Symptom**: Worker claims "merged to main" but `git branch --contains` doesn't show main
**Root Cause**: PR merged locally but not pushed; or wrong commit SHA
**Fix**:
1. Verify with: `git branch -a --contains <sha>`
2. Check remote main: `git fetch origin && git branch -r --contains <sha>`
3. If not on origin/main: Re-merge or push
**Prevention**: Always verify with `git branch --contains` before claiming merge

### Pattern 4: Fabricated Test Coverage Claims
**Symptom**: Worker reports test results but test files don't exist or weren't run
**Root Cause**: Tests claimed but not actually executed; or wrong test count
**Fix**:
1. Verify test files exist: `git show <sha> --name-only | grep test_`
2. Re-run tests: `pytest tests/ --collect-only` to verify test inventory
3. Cross-reference claimed results with actual test output
**Prevention**: Always include test output in completion evidence; use CI test gates

### Pattern 5: Fabricated Command Proof
**Symptom**: Worker claims command ran with specific output but no verifiable proof
**Root Cause**: Command claimed but not actually executed; or output fabricated
**Fix**:
1. Re-run claimed command in clean environment
2. Compare output with claimed results
3. Check command exists in commit history
**Prevention**: Include full command output with timestamps in evidence

## Required Commands Reference

| Check | Command | Expected Output |
|-------|---------|-----------------|
| File existence in commit | `git show <sha> --name-only` | List includes claimed files |
| Branch containment | `git branch --contains <sha>` | Shows feature branch |
| Main merge verification | `git branch --contains <sha>` | Shows 'main' |
| Cross-branch check | `git branch -a --contains <sha>` | Shows origin/main |
| Change magnitude | `git diff --stat HEAD~N` | Shows +/- counts per file |
| File timestamp proof (alt) | `ls -la <file_path>` | Timestamp matches claim window |
| Automated validation | `python3 scripts/swarm/evidence_validator.py --files <files>` | JSON report with pass/fail |

## Incident Response

If file-existence-check failure detected:

1. **STOP** all dependent work immediately
2. **LOG** incident with: `.opencode/command/chise-incident-log.md`
3. **NOTIFY** Jarvis/Aria with evidence
4. **QUARANTINE** any work based on false completion claims
5. **REMEDIATE** before resuming dependent work

**Reference Incident**: docs/evidence/PARTY-MODE-TRUTH-AUDIT-BRAINEVAL-CI.md
