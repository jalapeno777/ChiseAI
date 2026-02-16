---
name: chiseai-worker-contracts
description: Standardized worker task contracts for Jarvis-to-subagent delegation with safety guards and evidence requirements.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
---

# chiseai-worker-contracts

## Goal

Ensure every Jarvis delegation to sub-agents includes all required safety guards, scope definitions, and evidence requirements.

## When To Use

- **Every time** Jarvis delegates to dev/quickdev/senior-dev/merlin
- Before any parallel work delegation
- When re-planning after incidents

## Why This Matters

Inconsistent delegation leads to:
- Scope creep (workers touching wrong files)
- Merge conflicts (overlapping edits)
- Missing evidence (can't verify what was done)
- Stuck work (unclear exit conditions)

## Standard Worker Contract Template

Every delegation MUST include:

### 1. Scope Definition
SCOPE_GLOBS:
  - List repo-relative paths the worker may edit
  - Example: ["src/neuro_symbolic/evolution/", "tests/test_evolution/"]
  
FORBIDDEN_GLOBS:
  - List paths they must NOT touch
  - Example: [".woodpecker.yml", "docs/bmm-workflow-status.yaml", "infrastructure/terraform/"]

### 2. Locking & Ownership
LOCKS_REQUIRED:
  - GLOBAL (if touching global-lock areas)
  - OR specific scope locks: ["src:neuro_symbolic:evolution"]
  
OWNERSHIP_CHECK:
  - Check: bmad:chiseai:ownership for scope conflicts
  - On conflict: STOP and report to Jarvis immediately

### 3. Session Management
BRANCH:
  - Explicit branch name (never use HEAD/current-branch inference)
  - Example: "feature/ST-NS-001-neuro-evolution"
  
WORKTREE_PATH:
  - Isolated git worktree path for this worker
  - Example: "/tmp/worktrees/ST-NS-001-dev"
  
SESSION_VERIFY:
  - Command to run before any git actions
  - Example: "python3 scripts/swarm/session.py verify --story-id=ST-NS-001 --branch=feature/ST-NS-001-neuro-evolution --worktree-path=/tmp/worktrees/ST-NS-001-dev"

### 4. Memory Context
MEMORY_CONTEXT:
  - Qdrant findings: 5-10 relevant decisions/patterns for the area
  - Redis iterlog: Current story progress
  - Example: "Prior decision ST-NS-003: Use Redis caching for evolution states"

### 5. Exit Conditions
EXIT_CONDITIONS:
  "Stop and report back to Jarvis if you need to:
   - Edit outside SCOPE_GLOBS
   - Touch a FORBIDDEN_GLOBS path
   - Find an upstream blocker (dependency not ready)
   - Encounter 3+ failed attempts on same issue"

### 6. Evidence Requirements
EVIDENCE_REQUIRED:
  Files changed:
    - List with before/after summaries
  
  Commands run:
    - With actual results/output
    - Example: "pytest tests/test_evolution/ -v (passed: 15, failed: 0)"
  
  Verification:
    - How to verify the work is correct
    - Example: "Run: python3 -c 'from src.neuro_symbolic import Evolution; e = Evolution(); assert e.validate()'"

### 7. Incident Template
INCIDENT_TEMPLATE:
  If conflict/regression occurs, fill and report:
  
  INCIDENT:
    story_id: [STORY_ID]
    batch: [BATCH_NUMBER]
    scope_globs: [SCOPE_GLOBS_USED]
    symptom: [What went wrong]
    root_cause: [Why it happened]
    missed_signal: [What we should have caught]
    prevention_rule: [How to prevent next time]
    follow_up_tasks: [Action items]

## Delegation Checklist for Jarvis

Before hitting "delegate", verify:
- [ ] SCOPE_GLOBS is specific (not just "src/")
- [ ] FORBIDDEN_GLOBS includes global-lock areas
- [ ] BRANCH is explicit with story ID
- [ ] WORKTREE_PATH is isolated
- [ ] MEMORY_CONTEXT has actual Qdrant findings
- [ ] EXIT_CONDITIONS are clear
- [ ] INCIDENT_TEMPLATE is copy-paste ready

## Related Commands
- `.opencode/command/chise-claim-ownership.md`
- `.opencode/command/chise-check-ownership.md`
- `.opencode/command/chise-append-incident.md`
