# 10-Agent Parallel Support Runbook

## Overview

This runbook documents the 10-agent parallel execution support system for the ChiseAI swarm. It covers how parallel execution works, scope ownership guidelines, and troubleshooting procedures for conflicts.

## Table of Contents

1. [Architecture](#architecture)
2. [Scope Ownership](#scope-ownership)
3. [Conflict Detection](#conflict-detection)
4. [Batch Coordination](#batch-coordination)
5. [Deadlock Resolution](#deadlock-resolution)
6. [Troubleshooting](#troubleshooting)
7. [API Reference](#api-reference)

---

## Architecture

### Components

The parallel execution system consists of three main components:

#### 1. Scope Registry (`scripts/pr_lifecycle/scope_registry.py`)

Tracks which files each agent is working on using Redis-based storage.

**Key Features:**
- Redis-based scope ownership tracking
- Conflict detection algorithm
- Scope reservation and release
- Scope access validation

#### 2. Agent Coordinator (`scripts/pr_lifecycle/agent_coordinator.py`)

Manages agent registration, heartbeat monitoring, and work assignment.

**Key Features:**
- Agent registration and heartbeat
- Work assignment and load balancing
- Failure detection and recovery
- Priority-based work queue
- Max 10 concurrent agents enforcement

#### 3. Parallel Execution Coordinator (`scripts/pr_lifecycle/parallel_execution.py`)

Coordinates multi-agent work with dependency resolution and deadlock detection.

**Key Features:**
- Batch coordination for multi-agent work
- Dependency resolution
- Priority queue management
- Deadlock detection and resolution
- Sequential fallback for conflicts

### Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Jarvis        │────▶│  Agent Coordinator│────▶│  Redis Store    │
│  (Orchestrator) │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         │              ┌────────┴────────┐
         │              │                 │
         ▼              ▼                 ▼
┌─────────────────┐  ┌──────────────┐  ┌─────────────────────┐
│  Scope Registry │  │  Work Queue  │  │  Parallel Execution │
│                 │  │  (Priority)  │  │  Coordinator        │
└─────────────────┘  └──────────────┘  └─────────────────────┘
```

---

## Scope Ownership

### Claiming Scopes

Before an agent can edit files, it must claim ownership of the relevant scopes:

```python
from scripts.pr_lifecycle.scope_registry import get_scope_registry

registry = get_scope_registry()
success, conflicts = registry.reserve_scopes(
    scopes=["src/module/", "tests/test_module/"],
    story_id="ST-001",
    agent="agent-1",
    ttl_seconds=432000,  # 5 days
)

if not success:
    print("Conflicts detected:", conflicts)
    # Handle conflicts
```

### Releasing Scopes

When work is complete, release the scopes:

```python
registry.release_scopes(story_id="ST-001", agent="agent-1")
```

### Validating Access

Before editing a file, validate access:

```python
has_access, reason = registry.validate_scope_access(
    file_path="src/module/file.py",
    story_id="ST-001",
    agent="agent-1"
)

if not has_access:
    raise PermissionError(f"Access denied: {reason}")
```

### Scope Patterns

Scopes can be specified as:

- **Exact paths**: `src/module/file.py`
- **Directory globs**: `src/module/`
- **File globs**: `src/module/*.py`
- **Recursive globs**: `src/module/**/*.py`

### Best Practices

1. **Claim minimal scopes**: Only claim the files/directories you need
2. **Release promptly**: Release scopes when work is complete
3. **Use specific paths**: Prefer specific paths over broad globs
4. **Check conflicts early**: Check for conflicts before starting work
5. **Extend if needed**: Extend reservation TTL if work takes longer

---

## Conflict Detection

### Conflict Types

The system detects several types of conflicts:

| Conflict Type | Description | Example |
|--------------|-------------|---------|
| `EXACT_OVERLAP` | Same scope claimed by two agents | Both claim `src/test/` |
| `SUBSCOPE` | New scope is within existing scope | Claim `src/test/file.py` when `src/test/` is taken |
| `SUPERSCOPE` | New scope contains existing scope | Claim `src/` when `src/test/` is taken |
| `PARTIAL_OVERLAP` | Scopes partially overlap | `src/a/` and `src/a/b/` |
| `GLOB_OVERLAP` | Glob patterns match same files | `src/*.py` and `src/test.py` |

### Conflict Resolution

When conflicts are detected:

1. **STOP**: Do not proceed with edits
2. **LOG**: Log the conflict for analysis
3. **REPORT**: Report to Jarvis for re-planning
4. **WAIT**: Wait for conflicting work to complete, or
5. **RE-SCOPE**: Adjust scopes to avoid conflict

### Example: Handling Conflicts

```python
from scripts.pr_lifecycle.scope_registry import get_scope_registry

registry = get_scope_registry()
success, conflicts = registry.reserve_scopes(
    scopes=["src/module/"],
    story_id="ST-001",
    agent="agent-1"
)

if not success:
    for conflict in conflicts:
        print(f"Conflict with {conflict.story_id}/{conflict.agent}")
        print(f"  Type: {conflict.conflict_type.value}")
        print(f"  My scope: {conflict.my_scope}")
        print(f"  Their scope: {conflict.conflicting_scope}")
    
    # Report to Jarvis
    raise RuntimeError("Scope conflicts detected - re-planning required")
```

---

## Batch Coordination

### Creating a Batch

```python
from scripts.pr_lifecycle.parallel_execution import (
    get_parallel_execution_coordinator,
    DeadlockResolution,
)

coordinator = get_parallel_execution_coordinator()
batch = coordinator.create_batch(
    description="Implement feature X",
    max_parallel=5,
    deadlock_resolution=DeadlockResolution.ABORT_YOUNGEST,
)
```

### Adding Items

```python
from scripts.pr_lifecycle.agent_coordinator import AgentPriority

item1 = coordinator.add_item_to_batch(
    batch_id=batch.batch_id,
    story_id="ST-001",
    scope_globs=["src/module1/"],
    description="Implement module 1",
    priority=AgentPriority.HIGH,
)

item2 = coordinator.add_item_to_batch(
    batch_id=batch.batch_id,
    story_id="ST-002",
    scope_globs=["src/module2/"],
    description="Implement module 2",
    priority=AgentPriority.NORMAL,
    dependencies=[item1.item_id],  # Depends on item1
)
```

### Starting Execution

```python
# Validate first
is_valid, errors = coordinator.validate_batch(batch.batch_id)
if not is_valid:
    print("Validation failed:", errors)
    return

# Start batch
success = coordinator.start_batch(batch.batch_id)
```

### Executing Steps

```python
# Execute one step (assigns ready items to agents)
results = coordinator.execute_batch_step(batch.batch_id)
print(f"Assigned: {len(results['assigned'])}")
print(f"Failed: {len(results['failed'])}")
print(f"Skipped: {len(results['skipped'])}")
```

### Monitoring Progress

```python
summary = coordinator.get_batch_summary(batch.batch_id)
print(f"Status: {summary['status']}")
print(f"Progress: {summary['progress_percentage']:.1f}%")
print(f"Completed: {summary['completed']}/{summary['total_items']}")
```

---

## Deadlock Resolution

### Detecting Deadlocks

The system automatically detects circular dependencies:

```python
deadlock = coordinator.detect_deadlock(batch.batch_id)
if deadlock:
    print(f"Deadlock detected: {' -> '.join(deadlock.cycle)}")
```

### Resolution Strategies

| Strategy | Description | When to Use |
|----------|-------------|-------------|
| `ABORT_ALL` | Mark all items in cycle as failed | When cycle is unresolvable |
| `ABORT_YOUNGEST` | Abort the most recently created item | Default - minimal disruption |
| `ABORT_LOWEST_PRIORITY` | Abort the lowest priority item | When priorities matter |
| `SEQUENTIAL_FALLBACK` | Convert to sequential execution | When dependencies can be linearized |

### Resolving Deadlocks

```python
from scripts.pr_lifecycle.parallel_execution import DeadlockResolution

# Auto-resolve using batch default
coordinator.resolve_deadlock(batch.batch_id)

# Or specify strategy
coordinator.resolve_deadlock(
    batch.batch_id,
    strategy=DeadlockResolution.SEQUENTIAL_FALLBACK
)
```

---

## Troubleshooting

### Common Issues

#### Issue: "Scope conflicts detected"

**Symptoms:**
- `reserve_scopes()` returns `success=False`
- Conflicts list is populated

**Resolution:**
1. Review conflicting scopes
2. Check if work can be re-scoped
3. Wait for conflicting work to complete
4. Report to Jarvis for re-planning

```python
# Check existing reservations
all_reservations = registry.get_all_reservations()
for key, reservation in all_reservations.items():
    print(f"{key}: {reservation.scopes}")
```

#### Issue: "Maximum concurrent agents reached"

**Symptoms:**
- `register_agent()` raises `RuntimeError`

**Resolution:**
1. Check current agent count
2. Wait for agents to complete
3. Check for failed agents that need cleanup

```python
stats = agent_coordinator.get_queue_stats()
print(f"Total agents: {stats['total_agents']}")
print(f"Healthy agents: {stats['healthy_agents']}")
print(f"Available agents: {stats['available_agents']}")
```

#### Issue: "Agent marked as failed"

**Symptoms:**
- Agent status changed to `FAILED`
- Heartbeat timeout exceeded

**Resolution:**
1. Check agent logs
2. Verify agent is still running
3. Re-register agent if needed
4. Re-assign work from failed agent

```python
# Check for failed agents
failed = agent_coordinator.check_for_failures()
for agent in failed:
    print(f"Agent {agent.agent_id} failed")
    # Handle failure (e.g., re-assign work)
```

#### Issue: "Deadlock detected"

**Symptoms:**
- `detect_deadlock()` returns non-None
- Batch execution stalls

**Resolution:**
1. Review dependency graph
2. Check for circular dependencies
3. Apply deadlock resolution strategy
4. Re-plan work to avoid cycles

```python
# Visualize dependencies
batch = coordinator.get_batch(batch_id)
for item_id, item in batch.items.items():
    deps = " -> ".join(item.dependencies) if item.dependencies else "None"
    print(f"{item_id} depends on: {deps}")
```

### Debug Commands

```python
# Get all active reservations
from scripts.pr_lifecycle.scope_registry import get_scope_registry
registry = get_scope_registry()
reservations = registry.get_all_reservations()

# Get all agents
from scripts.pr_lifecycle.agent_coordinator import get_agent_coordinator
coordinator = get_agent_coordinator()
agents = coordinator.get_all_agents()

# Get queue stats
stats = coordinator.get_queue_stats()
print(json.dumps(stats, indent=2))

# Get all batches
from scripts.pr_lifecycle.parallel_execution import get_parallel_execution_coordinator
exec_coordinator = get_parallel_execution_coordinator()
batches = exec_coordinator.get_all_batches()
```

### Redis Keys

The system uses the following Redis keys:

| Key | Type | Description |
|-----|------|-------------|
| `bmad:chiseai:scope_registry` | Hash | Scope reservations |
| `bmad:chiseai:agents` | Hash | Agent information |
| `bmad:chiseai:work_queue` | Hash | Pending work items |
| `bmad:chiseai:work_queue:priority` | Sorted Set | Work priorities |
| `bmad:chiseai:active_work` | Hash | In-progress work |
| `bmad:chiseai:completed_work` | Hash | Completed work |
| `bmad:chiseai:execution_batches` | Hash | Execution batches |
| `bmad:chiseai:deadlock_log` | List | Deadlock history |

---

## API Reference

### ScopeRegistry

#### Methods

- `reserve_scopes(scopes, story_id, agent, ttl_seconds, metadata)` → `(bool, list[ScopeConflict])`
- `release_scopes(story_id, agent)` → `bool`
- `check_conflicts(scopes, story_id, agent)` → `list[ScopeConflict]`
- `validate_scope_access(file_path, story_id, agent)` → `(bool, str)`
- `get_reservation(story_id, agent)` → `ScopeReservation | None`
- `get_all_reservations()` → `dict[str, ScopeReservation]`
- `extend_reservation(story_id, agent, additional_seconds)` → `bool`
- `cleanup_expired()` → `int`

### AgentCoordinator

#### Methods

- `register_agent(story_id, agent_type, capabilities, metadata)` → `AgentInfo`
- `heartbeat(agent_id, status)` → `bool`
- `update_agent_status(agent_id, status)` → `bool`
- `get_agent(agent_id)` → `AgentInfo | None`
- `get_all_agents()` → `dict[str, AgentInfo]`
- `get_healthy_agents()` → `dict[str, AgentInfo]`
- `get_available_agents()` → `dict[str, AgentInfo]`
- `submit_work(story_id, scope_globs, description, priority, dependencies)` → `WorkAssignment`
- `assign_work(work_id, agent_id)` → `bool`
- `complete_work(work_id, result, error)` → `bool`
- `get_pending_work()` → `list[WorkAssignment]`
- `get_active_work()` → `dict[str, WorkAssignment]`
- `check_for_failures()` → `list[AgentInfo]`
- `get_queue_stats()` → `dict[str, Any]`

### ParallelExecutionCoordinator

#### Methods

- `create_batch(description, max_parallel, deadlock_resolution, metadata)` → `ExecutionBatch`
- `add_item_to_batch(batch_id, story_id, scope_globs, description, priority, dependencies)` → `BatchItem | None`
- `get_batch(batch_id)` → `ExecutionBatch | None`
- `get_all_batches()` → `dict[str, ExecutionBatch]`
- `detect_deadlock(batch_id)` → `DeadlockInfo | None`
- `resolve_deadlock(batch_id, strategy)` → `bool`
- `validate_batch(batch_id)` → `(bool, list[str])`
- `start_batch(batch_id)` → `bool`
- `execute_batch_step(batch_id)` → `dict[str, Any]`
- `update_batch_status(batch_id)` → `BatchStatus`
- `get_batch_summary(batch_id)` → `dict[str, Any] | None`

---

## Best Practices

### For Jarvis (Orchestrator)

1. **Always validate before starting**: Run `validate_batch()` before `start_batch()`
2. **Monitor agent health**: Regularly call `check_for_failures()`
3. **Handle deadlocks promptly**: Detect and resolve deadlocks quickly
4. **Clean up completed work**: Remove completed batches to free resources

### For Agents (Workers)

1. **Claim scopes before editing**: Always reserve scopes before making changes
2. **Send heartbeats regularly**: Heartbeat every 30 seconds minimum
3. **Release scopes when done**: Don't hold scopes longer than necessary
4. **Report failures immediately**: Don't let failed work hang

### For System Administrators

1. **Monitor Redis storage**: Watch for memory usage growth
2. **Clean up expired data**: Run `cleanup_expired()` periodically
3. **Review deadlock logs**: Analyze patterns to prevent future deadlocks
4. **Scale agents appropriately**: Monitor queue depth and agent utilization

---

## Related Documentation

- [AGENTS.md](../../AGENTS.md) - Agent swarm overview
- [chiseai-parallel-safety](../../.opencode/skills/chiseai-parallel-safety/SKILL.md) - Parallel safety patterns
- [chiseai-git-workflow](../../.opencode/skills/chiseai-git-workflow/SKILL.md) - Git workflow guidelines

---

## Changelog

### v1.0.0 (2026-02-25)

- Initial implementation of 10-agent parallel support
- Scope registry with conflict detection
- Agent coordinator with heartbeat monitoring
- Parallel execution coordinator with deadlock detection
- Batch coordination and dependency resolution
