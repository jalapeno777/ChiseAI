---
name: chiseai-parallel-safety
description: Safety patterns for parallel agent execution (scope ownership, global locks, incident handling).
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
---

# chiseai-parallel-safety

## Goal

Prevent conflicts and ensure safe parallel execution across agent swarm workers.

## When To Use

- Delegating work to multiple agents
- Planning parallel execution batches
- Detecting and handling conflicts

## Scope Ownership

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

## Related Commands
- `.opencode/command/chise-claim-ownership.md`
- `.opencode/command/chise-check-ownership.md`
- `.opencode/command/chise-incident-log.md`
