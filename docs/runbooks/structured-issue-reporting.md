---
title: Structured Issue Reporting Guide
category: workflow
severity: informational
estimated_time_to_complete: 5 minutes
last_updated: 2026-03-01
maintainers: platform-team
story_id: ST-ISSUE-ENFORCE-004
executable: false
---

# Structured Issue Reporting Guide

> **Story:** ST-ISSUE-ENFORCE-004  
> **Last Updated:** 2026-03-01  
> **Owner:** Platform Team  
> **Audience:** All workers completing tasks for Jarvis

---

## Overview

This runbook explains how to report issues at task completion using the structured format. Your issue reports drive framework improvements and help identify systemic problems.

---

## Purpose

Structured issue reporting serves four critical functions:

1. **Mini BrainEval Ingestion**: Issues are automatically scanned during evaluation cycles
2. **Pattern Detection**: Recurring issues are grouped to identify systemic problems
3. **Prioritization**: Framework improvements are ranked by impact and frequency
4. **Time Tracking**: Aggregates time lost to identify automation opportunities

---

## Schema Reference

Every issue entry MUST include all required fields:

```yaml
issue_type: string          # REQUIRED: Category of the issue
root_cause: string          # REQUIRED: Why did this happen?
fix_applied: string         # REQUIRED: What resolved it?
time_lost_minutes: integer  # REQUIRED: Time wasted (0 if minimal)
recurrence_hint: string     # REQUIRED: How to prevent next time?
impact_area: enum           # REQUIRED: throughput|efficiency|accuracy|reliability
resolved: boolean           # REQUIRED: Was it fully resolved?
```

### Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `issue_type` | string | Category of the issue | `ci_failure`, `merge_conflict`, `config_error` |
| `root_cause` | string | Technical reason the issue occurred | `missing dependency in requirements.txt` |
| `fix_applied` | string | Action taken to resolve | `added pytest-asyncio>=0.21.0` |
| `time_lost_minutes` | integer | Approximate time wasted | `45` |
| `recurrence_hint` | string | Actionable prevention tip | `run pip freeze after adding deps` |
| `impact_area` | enum | Which area was impacted | `efficiency` |
| `resolved` | boolean | Is the issue fully resolved? | `true` |

### Impact Area Options

| Value | When to Use | Priority |
|-------|-------------|----------|
| `throughput` | Work completely blocked, cannot proceed | Highest |
| `efficiency` | Work slowed but still progressing | High |
| `accuracy` | Results incorrect or misleading | Medium |
| `reliability` | Intermittent failures, flaky behavior | Medium |

### Common Issue Types

| Issue Type | Description |
|------------|-------------|
| `ci_failure` | CI pipeline failed (tests, lint, build) |
| `merge_conflict` | Git merge conflict with another branch |
| `config_error` | Configuration file incorrect or missing |
| `scope_conflict` | Overlapping work with another agent |
| `dependency_issue` | Missing or incompatible dependency |
| `permission_error` | Insufficient permissions to perform action |
| `timeout` | Operation exceeded time limit |
| `data_issue` | Missing, corrupt, or incorrect data |
| `network_error` | Network connectivity problem |
| `documentation_gap` | Missing or outdated documentation |

---

## Examples

### Example 1: CI Failure with Complete Issue Record

**Scenario**: Tests failed in CI due to missing async test dependency.

```yaml
## Structured Issues

issues:
  - issue_type: "ci_failure"
    root_cause: "pytest-asyncio missing from requirements.txt"
    fix_applied: "added pytest-asyncio>=0.21.0 to requirements.txt and re-ran tests"
    time_lost_minutes: 45
    recurrence_hint: "after adding new test imports, run pip freeze > requirements.txt"
    impact_area: "efficiency"
    resolved: true
```

**Why this is good**:
- Clear root cause identifies the exact missing dependency
- Fix is actionable and reproducible
- Recurrence hint provides a concrete prevention step
- Time lost helps quantify the impact

### Example 2: Merge Conflict with Complete Issue Record

**Scenario**: Two workers edited the same file without ownership coordination.

```yaml
## Structured Issues

issues:
  - issue_type: "merge_conflict"
    root_cause: "parallel work on src/strategy/dsl/parser.py without ownership check"
    fix_applied: "rebased branch, manually resolved conflicts, added file to FORBIDDEN_GLOBS"
    time_lost_minutes: 30
    recurrence_hint: "always claim ownership via chise-claim-ownership before editing shared files"
    impact_area: "throughput"
    resolved: true
```

**Why this is good**:
- Root cause identifies the process failure (no ownership check)
- Fix includes both immediate resolution and prevention (FORBIDDEN_GLOBS)
- Impact area correctly identified as `throughput` (work was blocked)

### Example 3: Empty Issues (No Problems Encountered)

**Scenario**: Task completed smoothly with no blockers.

```yaml
## Structured Issues

issues: []
```

**When to use**: Only when literally zero issues occurred during the iteration.

---

## How Issues Are Used

### Mini BrainEval Ingestion

Every iteration close triggers Mini BrainEval to scan all structured issues:

```
iterlog → Mini BrainEval → grouped_issues → prioritized_improvements
```

### Recurring Pattern Detection

Issues are fingerprinted by `issue_type + root_cause`:

```
Fingerprint: "ci_failure + missing dependency"
Occurrences: 12 times in last 30 days
Total time lost: 540 minutes (9 hours)
Priority: HIGH (throughput impact)
```

### Framework Improvement Prioritization

Improvements are ranked by:

1. **Frequency**: How often this issue type occurs
2. **Time Lost**: Total aggregate time wasted
3. **Impact Area**: `throughput` > `efficiency` > `accuracy` > `reliability`

**Example prioritization**:
| Rank | Issue Pattern | Frequency | Time Lost | Impact |
|------|---------------|-----------|-----------|--------|
| 1 | CI failures from missing deps | 12 | 540 min | efficiency |
| 2 | Merge conflicts on shared files | 8 | 240 min | throughput |
| 3 | Config errors in env files | 5 | 150 min | reliability |

### Your Reports Matter

When you report issues accurately:
- Patterns become visible across all workers
- High-impact automation targets are identified
- Framework improvements benefit everyone
- Time savings compound across the team

---

## Common Mistakes to Avoid

### ❌ Missing Fields

```yaml
# WRONG - missing required fields
issues:
  - issue_type: "ci_failure"
    root_cause: "tests failed"
```

**Problem**: Missing `fix_applied`, `time_lost_minutes`, `recurrence_hint`, `impact_area`, `resolved`.

### ❌ Vague Root Cause

```yaml
# WRONG - too vague
root_cause: "something went wrong"
```

**Better**:
```yaml
root_cause: "pytest-asyncio plugin not installed, async test functions not recognized"
```

### ❌ Non-Actionable Recurrence Hint

```yaml
# WRONG - not actionable
recurrence_hint: "be more careful"
```

**Better**:
```yaml
recurrence_hint: "run 'pip freeze > requirements.txt' after installing new test dependencies"
```

### ❌ Wrong Impact Area

```yaml
# WRONG - work was blocked, not just slow
impact_area: "efficiency"
```

**Correct**: If work could not proceed at all:
```yaml
impact_area: "throughput"
```

### ❌ Empty String Instead of Empty List

```yaml
# WRONG - empty string
issues: ""
```

**Correct**:
```yaml
issues: []
```

---

## Validation Checklist

Before submitting your completion report, verify:

- [ ] All issue entries have ALL 7 required fields
- [ ] `issue_type` is a recognized category
- [ ] `root_cause` is specific and technical
- [ ] `fix_applied` describes a concrete action
- [ ] `time_lost_minutes` is a realistic estimate
- [ ] `recurrence_hint` is actionable
- [ ] `impact_area` is one of: `throughput`, `efficiency`, `accuracy`, `reliability`
- [ ] `resolved` is `true` or `false` (not a string)
- [ ] If no issues: `issues: []` (empty list, not empty string)

### Validation Command

```bash
python3 scripts/validate_iterloop_compliance.py --require-structured-issues
```

Expected output:
```
✓ Structured issues section found
✓ All required fields present
✓ Impact area valid: efficiency
✓ YAML syntax valid
PASS: Structured issues validation complete
```

---

## Quick Reference

### Copy-Paste Template

```markdown
## Structured Issues

issues:
  - issue_type: ""
    root_cause: ""
    fix_applied: ""
    time_lost_minutes: 0
    recurrence_hint: ""
    impact_area: "efficiency"  # throughput|efficiency|accuracy|reliability
    resolved: true
```

### Empty Issues Template

```markdown
## Structured Issues

issues: []
```

---

## Related Documentation

- [chiseai-worker-contracts Skill](../.opencode/skills/chiseai-worker-contracts/SKILL.md)
- [chise-iterloop-close Command](../.opencode/command/chise-iterloop-close.md)
- [Mini BrainEval Runbook](mini-brain-eval.md)
- [Incident Response Runbook](incident_response.md)

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-01 | Platform Team | Initial creation for ST-ISSUE-ENFORCE-004 |
