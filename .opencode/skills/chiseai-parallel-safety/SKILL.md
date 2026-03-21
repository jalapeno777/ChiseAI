---
name: chiseai-parallel-safety
description: Safety patterns for parallel agent execution including scope ownership, scope overlap analysis, global locks, conflict detection, batch planning, incident handling, and recovery procedures for accidental global-lock touches.
metadata:
  version: "1.2"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-11"
---

# chiseai-parallel-safety

## Goal

Prevent conflicts and ensure safe parallel execution across agent swarm workers.

## When To Use

- Delegating work to multiple agents
- Planning parallel execution batches
- Detecting and handling conflicts
- Setting up multi-worker stories

## When Not To Use

- Single-agent sequential work
- Read-only operations
- Non-repo parallel tasks
- External service coordination

## Scope Ownership

### Aria/Jarvis Concurrency Boundary
- Aria may have only one active Jarvis/JarvisRuntime session at a time.
- Aria-level parallel Jarvis invocations are prohibited.
- Parallelism is executed within a single Jarvis session via worker batches.

### Before Delegating
Jarvis must claim ownership for each work item:
- Use `.opencode/command/chise-claim-ownership.md`
- Define `SCOPE_GLOBS` (repo-relative paths)
- Set TTL (default: 5 days)

### Executor Requirement
Workers must check ownership before edits:
- Use `.opencode/command/chise-check-ownership.md`
- If conflict detected, STOP and report to Jarvis

### Ownership Schema
```
Redis hash: bmad:chiseai:ownership
key: <path_slug> (e.g., "src:neuro_symbolic:evolution")
value: <story_id>/<agent>/<timestamp>
```

## Global-Lock Areas (Sequential-by-Default)

These areas require sequential execution:
- `.woodpecker.yml`, `pyproject.toml`, `scripts/`
- `infrastructure/terraform/`
- Risk limits, execution safety modules
- `AGENTS.md`, `.opencode/agent/`
- `docs/bmm-workflow-status.yaml`, `docs/validation/validation-registry.yaml`

## Parallel-Safe Criteria

Work items may run in parallel only when ALL true:
- Disjoint `scope_globs`
- No shared global-lock areas
- No ordering dependency (`depends_on` empty)
- No shared integration choke point

## Incident Handling

When conflict/regression occurs:
1. STOP work immediately
2. Use `.opencode/command/chise-incident-log.md` to log
3. Report to Jarvis for re-planning

### Required Incident Fields
- story_id
- batch
- scope_globs
- symptom
- root_cause
- missed_signal
- prevention_rule

## Exit Conditions

- Ownership claimed before parallel work begins.
- Workers verify ownership before edits.
- Conflicts detected and reported immediately.
- No global-lock area violations.

## Troubleshooting/Safety

- **Ownership conflict**: STOP immediately; report to Jarvis for re-planning.
- **Global-lock touched**: Roll back if possible; escalate to Jarvis.
- **Stale ownership**: Check TTL; refresh or re-claim if expired.
- **Undetected overlap**: Add to incident log; improve scope definition.

## Related Skills

- `chiseai-worker-contracts` - Delegation contract structure
- `chiseai-incident-response` - Incident handling process
- `chiseai-memory-ops` - Redis ownership tracking

## Templates

### Template 1: Ownership Claim Check

```python
# Pre-edit ownership verification
import json

def check_ownership(scope_globs):
    """
    Check if all scope paths are available for editing.
    Returns (can_proceed, conflicts)
    """
    conflicts = []
    
    for glob_path in scope_globs:
        # Convert glob to slug (e.g., "src/strategy/dsl/" -> "src:strategy:dsl")
        slug = glob_path.strip("/").replace("/", ":")
        
        # Check Redis ownership
        owner = redis_state_hget(
            name="bmad:chiseai:ownership",
            key=slug
        )
        
        if owner:
            # Check if we own it
            if story_id not in owner:
                conflicts.append({
                    "path": glob_path,
                    "slug": slug,
                    "owner": owner
                })
    
    can_proceed = len(conflicts) == 0
    return can_proceed, conflicts

# Usage
can_proceed, conflicts = check_ownership([
    "src/strategy/dsl/",
    "tests/unit/strategy/"
])

if not can_proceed:
    print("OWNERSHIP CONFLICT DETECTED!")
    for c in conflicts:
        print(f"  {c['path']} owned by: {c['owner']}")
    print("STOP and report to Jarvis")
    sys.exit(1)
```

### Template 2: Parallel Batch Plan

```markdown
# Parallel Batch Plan

## Batch Information
- **Batch ID**: Batch-5-dsl-extensions
- **Planned By**: Jarvis
- **Created**: 2026-02-23T09:00:00Z

## Pre-Flight Checks

### Scope Overlap Analysis
| Work Item | Scope | Overlap Check |
|-----------|-------|---------------|
| Item 1 | src/dsl/trailing/ | ✓ No overlap |
| Item 2 | src/dsl/position/ | ✓ No overlap |
| Item 3 | src/dsl/risk/ | ✓ No overlap |

### Global-Lock Check
- [ ] No work item touches global-lock areas
- [ ] pyproject.toml unchanged
- [ ] CI config unchanged
- [ ] Status files unchanged

## Work Items

### Item 1: Trailing Stop
- **Agent**: senior-dev-A
- **Scope**: src/strategy/dsl/trailing_stop/, tests/test_trailing_stop.py
- **Ownership Key**: src:strategy:dsl:trailing_stop
- **Depends On**: none
- **Status**: PENDING

### Item 2: Position Sizing
- **Agent**: senior-dev-B
- **Scope**: src/strategy/dsl/position_sizing/, tests/test_position_sizing.py
- **Ownership Key**: src:strategy:dsl:position_sizing
- **Depends On**: none
- **Status**: PENDING

### Item 3: Risk Management
- **Agent**: senior-dev-C
- **Scope**: src/strategy/dsl/risk_management/, tests/test_risk_management.py
- **Ownership Key**: src:strategy:dsl:risk_management
- **Depends On**: none
- **Status**: PENDING

## Integration Plan
After all items complete:
1. Collect results from all workers
2. Run integration tests
3. Single worker handles PR creation
4. Sequential merge to avoid CI queue issues

## Emergency Protocol
If any worker reports conflict:
1. HALT all parallel work
2. Log incident
3. Re-plan as sequential
```

### Template 3: Conflict Resolution Procedure

```markdown
# Conflict Resolution Procedure

## Detection
When ownership check or git operation reveals conflict:

### Step 1: Stop
```bash
# Do NOT proceed with edits
# Do NOT force operations
```

### Step 2: Document
```python
conflict = {
    "detected_at": datetime.now().isoformat(),
    "my_scope": ["src/strategy/dsl/"],
    "conflicting_owner": "ST-OTHER-001/senior-dev",
    "conflicting_path": "src/strategy/dsl/grammar.py"
}
```

### Step 3: Log Incident
```python
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}:incidents",
    value=json.dumps({
        "type": "ownership_conflict",
        "severity": "P2",
        "details": conflict
    })
)
```

### Step 4: Report to Jarvis
```markdown
## Conflict Report

I cannot proceed with [ST-XXX] due to ownership conflict:

- **My Scope**: src/strategy/dsl/
- **Conflict**: src:strategy:dsl owned by ST-OTHER-001/senior-dev
- **Recommendation**: 
  - Option A: Wait for ST-OTHER-001 to complete
  - Option B: Re-scope to avoid conflict
  - Option C: Sequential execution

Awaiting your decision.
```

### Step 5: Await Resolution
Do NOT proceed until Jarvis provides resolution.
```

### Template 4: Sequential Conversion Plan

```markdown
# Sequential Conversion Plan

## Context
Originally planned as parallel batch, converted to sequential due to:
[Reason: scope overlap discovered / dependency found / resource constraint]

## Original Parallel Plan
- Item 1: [description] - [agent]
- Item 2: [description] - [agent]
- Item 3: [description] - [agent]

## New Sequential Plan

### Phase 1: Foundation
- **Item**: [description]
- **Agent**: [agent]
- **Scope**: [paths]
- **Delivers**: [what's handed off]

### Phase 2: Build
- **Item**: [description]
- **Agent**: [agent]
- **Depends On**: Phase 1
- **Scope**: [paths]
- **Delivers**: [what's handed off]

### Phase 3: Integration
- **Item**: [description]
- **Agent**: [agent]
- **Depends On**: Phase 2
- **Scope**: [paths]
- **Delivers**: Final integration

## Timeline Impact
- Original parallel estimate: [time]
- New sequential estimate: [time]
- Delay: [delta]

## Lessons Learned
- [What caused the conversion]
- [How to prevent in future]
```

## Examples

### Example 1: Successful Parallel Execution

**Context**: Three independent DSL features to implement

**Pre-Flight Analysis**:

```python
# Check for scope overlap
scopes = {
    "Item 1": ["src/strategy/dsl/trailing_stop/"],
    "Item 2": ["src/strategy/dsl/position_sizing/"],
    "Item 3": ["src/strategy/dsl/risk_management/"]
}

# Verify no overlap
all_paths = []
for item, paths in scopes.items():
    for p in paths:
        assert p not in all_paths, f"Overlap detected: {p}"
        all_paths.append(p)

# Check global-lock areas
forbidden = [".woodpecker.yml", "pyproject.toml", "AGENTS.md"]
for item, paths in scopes.items():
    for p in paths:
        assert not any(f in p for f in forbidden), f"Global-lock violation: {p}"

print("✓ All checks passed, safe for parallel execution")
```

**Outcome**: All three workers completed successfully in parallel. Total time: 4 hours (vs 12 hours sequential).

### Example 2: Ownership Conflict Detection

**Context**: Worker attempts to edit file owned by another

**Conflict Detection**:

```python
# Worker B attempts to start work
scope_globs = ["src/strategy/dsl/"]

# Check ownership
slug = "src:strategy:dsl"
owner = redis_state_hget(name="bmad:chiseai:ownership", key=slug)

if owner and "ST-DSL-042" not in owner:
    # Conflict!
    print(f"❌ OWNERSHIP CONFLICT")
    print(f"   Path: {slug}")
    print(f"   Owner: {owner}")
    print(f"   Action: STOP and report to Jarvis")
    
    # Log incident
    redis_state_rpush(
        name="bmad:chiseai:iterlog:story:ST-DSL-043:incidents",
        value=json.dumps({
            "type": "ownership_conflict",
            "severity": "P2",
            "path": slug,
            "conflicting_owner": owner
        })
    )
else:
    # Safe to proceed
    print("✓ Ownership verified, proceeding with work")
```

**Outcome**: Worker stopped before making changes. Jarvis re-planned as sequential execution.

### Example 3: Global-Lock Violation Recovery

**Context**: Worker accidentally touched CI config

**Detection**:

```bash
$ git diff --name-only origin/main
src/strategy/dsl/trailing_stop.py
.woodpecker.yml  # ❌ This is a global-lock file!
```

**Recovery**:

```bash
# Step 1: Revert the global-lock change
$ git checkout origin/main -- .woodpecker.yml

# Step 2: Verify only scope files remain
$ git diff --name-only origin/main
src/strategy/dsl/trailing_stop.py  # ✓ Only scope file

# Step 3: Commit the fix
$ git add .woodpecker.yml
$ git commit -m "fix: revert accidental CI config change (ST-DSL-042)"

# Step 4: Log incident
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-DSL-042:incidents",
    value=json.dumps({
        "type": "global_lock_violation",
        "severity": "P2",
        "file": ".woodpecker.yml",
        "resolution": "Reverted change, added to FORBIDDEN_GLOBS reminder"
    })
)
```

**Outcome**: Change reverted, incident logged, no impact on other work.

## Quick Reference

### Parallel-Safe Checklist

```markdown
Before parallel delegation:
- [ ] Scopes are disjoint (no shared paths)
- [ ] No global-lock areas in any scope
- [ ] No dependencies between items
- [ ] Ownership claimed for each scope
- [ ] Integration plan defined
```

### Ownership Commands

```python
# Claim
redis_state_hset("bmad:chiseai:ownership", "src:module", "ST-XXX/agent/timestamp")

# Check
owner = redis_state_hget("bmad:chiseai:ownership", "src:module")

# Release
redis_state_hdel("bmad:chiseai:ownership", "src:module")
```

### Global-Lock Files

```
Always Sequential:
- .woodpecker.yml
- pyproject.toml
- AGENTS.md
- infrastructure/terraform/
- docs/bmm-workflow-status.yaml
- docs/validation/validation-registry.yaml
```

### Conflict Resolution Flow

```
1. Detect conflict → STOP
2. Document details
3. Log incident
4. Report to Jarvis
5. Await resolution
6. Do NOT proceed until cleared
```

## Related Commands

- `.opencode/command/chise-claim-ownership.md`
- `.opencode/command/chise-check-ownership.md`
- `.opencode/command/chise-incident-log.md`
