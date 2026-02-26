---
name: chiseai-worker-contracts
description: Standardized worker task contracts for Jarvis-to-subagent delegation with safety guards and evidence requirements.
metadata:
  version: "2.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-02-23"
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
- [ ] Completion evidence template included
- [ ] Worker understands handoff payload requirements

## Templates

### Template 1: Standard Delegation Contract

```markdown
## WORKER CONTRACT

SCOPE_GLOBS:
  - src/[module]/
  - tests/test_[module]/

FORBIDDEN_GLOBS:
  - .woodpecker.yml
  - pyproject.toml
  - docs/bmm-workflow-status.yaml
  - infrastructure/terraform/
  - AGENTS.md

LOCKS_REQUIRED:
  - src:[module]

OWNERSHIP_CHECK:
  - Check Redis: bmad:chiseai:ownership for src:[module]
  - If held by another story, STOP and report

BRANCH: feature/[STORY-ID]-[slug]
WORKTREE_PATH: /tmp/worktrees/[STORY-ID]-[agent]

SESSION_VERIFY: python3 scripts/swarm/session.py verify --story-id=[STORY-ID] --branch=feature/[STORY-ID]-[slug] --worktree-path=/tmp/worktrees/[STORY-ID]-[agent]

MEMORY_CONTEXT:
  - Qdrant search "[topic]" found:
    - Decision [ST-XXX]: [brief summary]
    - Pattern: [brief summary]
  - Redis iterlog shows: [current progress]

EXIT_CONDITIONS:
  Stop and report back to Jarvis if:
  - Need to edit outside SCOPE_GLOBS
  - Encounter FORBIDDEN_GLOBS requirement
  - Find upstream blocker
  - 3+ failed attempts on same issue

EVIDENCE_REQUIRED:
  Files changed: [list with summaries]
  Commands run: [with actual output]
  Verification: [how to verify correctness]

INCIDENT_TEMPLATE:
  Copy from chiseai-incident-response skill
```

### Template 2: Parallel Batch Delegation

```markdown
## PARALLEL BATCH CONTRACT

BATCH_ID: Batch-[N]-[topic]
COORDINATOR: Jarvis
WORKERS: [agent1], [agent2], [agent3]

### Work Item 1 (assigned to: [agent1])
SCOPE_GLOBS: [specific paths]
LOCKS_REQUIRED: [lock-name]
DEPENDENCIES: none

### Work Item 2 (assigned to: [agent2])
SCOPE_GLOBS: [specific paths]
LOCKS_REQUIRED: [lock-name]
DEPENDENCIES: none

### Work Item 3 (assigned to: [agent3])
SCOPE_GLOBS: [specific paths]
LOCKS_REQUIRED: [lock-name]
DEPENDENCIES: none

## Parallel Safety Rules
1. Each worker MUST check ownership before edits
2. Workers MUST NOT communicate directly during execution
3. All results reported back to Jarvis only
4. If conflict detected, STOP immediately and log incident

## Integration Protocol
After all workers complete:
1. Jarvis reviews all results
2. Sequential merge planning
3. Integration tests run by single designated worker
```

### Template 3: Sequential Delegation (with Dependencies)

```markdown
## SEQUENTIAL DELEGATION CONTRACT

CHAIN_ID: Chain-[topic]
TOTAL_STEPS: [N]

### Step 1: [description]
ASSIGNED_TO: [agent]
SCOPE_GLOBS: [paths]
COMPLETION_CRITERIA: [what defines done]
HANDS_OFF_TO: [next agent]

### Step 2: [description]
ASSIGNED_TO: [agent]
SCOPE_GLOBS: [paths]
DEPENDS_ON: Step 1 completion + [specific artifact]
COMPLETION_CRITERIA: [what defines done]
HANDS_OFF_TO: [next agent]

### Step 3: [description]
ASSIGNED_TO: [agent]
SCOPE_GLOBS: [paths]
DEPENDS_ON: Step 2 completion + [specific artifact]
COMPLETION_CRITERIA: [what defines done]
HANDS_OFF_TO: merlin (for PR)

## Handoff Protocol
Between each step:
1. Current worker reports completion to Jarvis
2. Jarvis verifies completion criteria met
3. Jarvis updates ownership for next step
4. Jarvis delegates to next worker with handoff context
```

### Template 4: Emergency Delegation

```markdown
## EMERGENCY DELEGATION CONTRACT

INCIDENT_ID: [ID]
SEVERITY: P0/P1
AUTHORIZATION: [Who authorized bypass]

SCOPE_GLOBS:
  - [minimal scope for fix]

FORBIDDEN_GLOBS:
  - [standard forbidden list still applies unless explicitly overridden]

BYPASS_JUSTIFICATION:
  - [Why normal process bypassed]
  - [Risk accepted]
  - [Follow-up required]

BRANCH: safety/[incident-id]-[date]
WORKTREE_PATH: /tmp/worktrees/emergency-[id]

EXIT_CONDITIONS:
  - Fix the immediate issue
  - Add incident log entry
  - Schedule post-mortem
  - DO NOT make non-essential changes

EVIDENCE_REQUIRED:
  - Before/after state of affected system
  - Root cause analysis (preliminary)
  - Incident log entry created

POST-EMERGENCY:
  - [ ] Post-mortem scheduled
  - [ ] Normal process review
  - [ ] Prevention measures documented
```

### Template 5: Mandatory Completion Evidence

```markdown
## MANDATORY COMPLETION EVIDENCE

### Handoff Payload (REQUIRED)
- **Story ID**: [ST-XXX]
- **Branch**: [feature/ST-XXX-slug]
- **Head SHA**: [full commit hash]
- **Test Summary**: [N tests passed, X failed, coverage %]
- **Status-Sync Proof**: [validation output or link]
- **Blockers**: [None | list of blockers]

### Work Evidence
- Files changed: [list with +/-/modified counts]
- Commands run: [with actual output]
- Verification steps: [how to confirm correctness]

### Completion Checklist
- [ ] Local CI passed
- [ ] Status sync validated
- [ ] Working tree clean (or documented exception)
- [ ] Ownership released (via chise-release-ownership)
- [ ] Worktree cleanup completed (or scheduled)
```

## Examples

### Example 1: Feature Implementation Delegation

**Context**: Jarvis needs to delegate a new feature implementation to senior-dev

**Contract Used**:

```markdown
## WORKER CONTRACT

SCOPE_GLOBS:
  - src/strategy/dsl/
  - tests/unit/strategy/test_dsl.py

FORBIDDEN_GLOBS:
  - .woodpecker.yml
  - pyproject.toml
  - infrastructure/terraform/
  - AGENTS.md
  - docs/bmm-workflow-status.yaml

LOCKS_REQUIRED:
  - src:strategy:dsl

OWNERSHIP_CHECK:
  - Check: bmad:chiseai:ownership for src:strategy:dsl
  - On conflict: STOP

BRANCH: feature/ST-DSL-042-grammar-extensions
WORKTREE_PATH: /tmp/worktrees/ST-DSL-042-senior-dev

SESSION_VERIFY: python3 scripts/swarm/session.py verify --story-id=ST-DSL-042 --branch=feature/ST-DSL-042-grammar-extensions --worktree-path=/tmp/worktrees/ST-DSL-042-senior-dev

MEMORY_CONTEXT:
  - Qdrant "DSL grammar" found:
    - Decision ST-DSL-031: Use ANTLR4 for parsing
    - Pattern: Grammar rules in separate .g4 files
  - Redis iterlog: Phase 0 data gathering complete

EXIT_CONDITIONS:
  Stop if: need to touch parser infrastructure (outside scope)

EVIDENCE_REQUIRED:
  Files: grammar_extensions.py (new), test_grammar_extensions.py (new)
  Commands: pytest tests/unit/strategy/test_dsl.py -v
  Verification: python3 -c "from src.strategy.dsl import parse; assert parse('new_syntax')"

## TASK
Add support for 'trailing_stop' syntax to DSL grammar.
```

**Outcome**: Worker completed successfully, reported:
- Files changed: grammar_extensions.py (+150 lines), test_grammar_extensions.py (+80 lines)
- Commands run: pytest passed (12 tests)
- Verification: parse() handles new syntax correctly

### Example 2: Parallel Feature Work

**Context**: Two independent features can be developed in parallel

**Batch Contract**:

```markdown
## PARALLEL BATCH CONTRACT

BATCH_ID: Batch-5-dsl-extensions
COORDINATOR: Jarvis

### Work Item 1: Trailing Stop Syntax
ASSIGNED_TO: senior-dev-A
SCOPE_GLOBS: src/strategy/dsl/trailing_stop/
LOCKS_REQUIRED: src:strategy:dsl:trailing_stop
DEPENDENCIES: none

### Work Item 2: Position Sizing Syntax
ASSIGNED_TO: senior-dev-B
SCOPE_GLOBS: src/strategy/dsl/position_sizing/
LOCKS_REQUIRED: src:strategy:dsl:position_sizing
DEPENDENCIES: none

## Safety Rules
- Disjoint scopes verified ✓
- Ownership claimed for each ✓
- No shared files ✓
```

**Outcome**: Both workers completed in parallel. Jarvis coordinated merge (sequential to avoid CI queue issues).

### Example 3: Incident-Driven Re-delegation

**Context**: Initial delegation failed due to scope overlap

**First Contract (FAILED)**:

```markdown
SCOPE_GLOBS:
  - src/strategy/  # TOO BROAD
  - tests/
```

**Incident Logged**:
- Symptom: Worker touched shared module causing merge conflict
- Root cause: Scope too broad, overlapped with other work
- Prevention: Use specific subdirectory scopes

**Revised Contract**:

```markdown
SCOPE_GLOBS:
  - src/strategy/dsl/trailing_stop/  # SPECIFIC
  - tests/unit/strategy/test_trailing_stop.py

FORBIDDEN_GLOBS:
  - src/strategy/dsl/grammar.py  # Shared file
  - src/strategy/dsl/parser.py   # Shared file
```

**Outcome**: Revised contract succeeded without conflicts.

## When Not To Use

- Single-agent work (no delegation needed)
- Read-only research tasks
- External tool invocations
- Non-repo operations

## Exit Conditions

- Contract includes all 7 required sections.
- Scope is specific and bounded.
- Evidence requirements are verifiable.
- Worker acknowledges and follows contract.

## Troubleshooting/Safety

- **Scope drift**: Worker must report immediately; do not self-expand scope.
- **Missing context**: Request clarification from Jarvis before proceeding.
- **Evidence incomplete**: Re-run verification steps; document gaps.
- **Contract violation**: Stop work, report to Jarvis, await re-delegation.

## Related Skills

- `chiseai-parallel-safety` - Ownership and conflict handling
- `chiseai-incident-response` - Incident template usage
- `chiseai-git-workflow` - Session and branch management

## Mandatory Completion Evidence

Workers MUST provide the following evidence before reporting completion to Jarvis:

### Required Payload Fields
```yaml
WORKER_COMPLETION_REPORT:
  story_id: "ST-XXX"           # Story identifier
  branch: "feature/ST-XXX-slug" # Exact branch name worked on
  head_sha: "abc123"            # Git SHA of branch tip at completion
  test_summary:                 # Test execution results
    command: "pytest tests/..."
    result: "passed|failed"
    counts: "N passed, M failed, X skipped"
    duration: "2.34s"
  status_sync_proof:            # Validation output
    command: "python3 scripts/validate_status_sync.py --pr N"
    result: "PASS|FAIL"
    details: "..."
  blockers: "None"              # Or list of blocking issues
```

### Command Evidence Requirements
For each claim in the report, provide:

1. **Files Changed**: List with before/after line counts
   - Command: `git diff --stat HEAD~N`
   - Required: Show all modified files with `+/-` counts

2. **Tests Passed**: Actual command output
   - Command: `pytest tests/... -v`
   - Required: Full output showing test names and pass/fail status

3. **Status Sync Validated**: Proof of sync check
   - Command: `python3 scripts/validate_status_sync.py --pr N`
   - Required: Output showing "PASS" or specific failures

4. **Branch State**: Current position
   - Command: `git log --oneline -3 && git status -sb`
   - Required: Show HEAD commit and working tree state

### Handoff Protocol
Before marking work complete:
1. Run all verification commands and capture output
2. Populate WORKER_COMPLETION_REPORT with exact values
3. Include raw command output as evidence in handoff message
4. Wait for Jarvis acknowledgment before releasing ownership

## Related Commands

- `.opencode/command/chise-claim-ownership.md`
- `.opencode/command/chise-check-ownership.md`
- `.opencode/command/chise-append-incident.md`
- `.opencode/command/chise-swarm-session.md`
