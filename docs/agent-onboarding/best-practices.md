# Best Practices for Agent Swarm Collaboration

## Overview

This document outlines best practices for agents working in the ChiseAI swarm. Following these practices ensures smooth collaboration, minimizes conflicts, and maintains high code quality.

## Scope Ownership Guidelines

### What is Scope Ownership?

Scope ownership is a mechanism to prevent multiple agents from editing the same files simultaneously. It's tracked in Redis and enforced by all agents.

### Ownership Schema

```yaml
Redis Hash: bmad:chiseai:ownership
Key Format: <path_slug> (e.g., "src:strategy:dsl")
Value Format: <story_id>/<agent>/<timestamp>
TTL: 432000 seconds (5 days)
```

### Claiming Ownership

Always claim ownership before starting work:

```python
from datetime import datetime
from tools import redis_state_hset

# Claim ownership for your scope
redis_state_hset(
    name="bmad:chiseai:ownership",
    key="src:your:module",
    value=f"ST-XXX/{agent_name}/{datetime.now().isoformat()}",
    expire_seconds=432000  # 5 days
)
```

### Checking Ownership

Always verify ownership before making edits:

```python
from tools import redis_state_hget

# Check if scope is available
owner = redis_state_hget(name="bmad:chiseai:ownership", key="src:your:module")

if owner:
    story_id, agent, timestamp = owner.split("/")
    if story_id != "ST-XXX":  # Replace with your story ID
        print(f"❌ CONFLICT: Scope owned by {agent} for {story_id}")
        print("STOP and report to Jarvis immediately!")
        # Do NOT proceed
    else:
        print(f"✅ Ownership verified: You own this scope")
else:
    print(f"⚠️  Scope unclaimed - claim before editing")
```

### Releasing Ownership

Release ownership when your work is complete:

```python
from tools import redis_state_hdel

# Release ownership
redis_state_hdel(name="bmad:chiseai:ownership", key="src:your:module")
```

### Ownership Best Practices

1. **Claim Early**: Claim ownership as soon as you receive your worker contract
2. **Check Before Edit**: Always verify ownership before every editing session
3. **Release Promptly**: Release ownership when you hand off to Jarvis
4. **Don't Hog**: If you need extended time, refresh the TTL rather than letting it expire
5. **Report Conflicts**: If you find a conflict, STOP immediately and report to Jarvis

## Conflict Avoidance Strategies

### 1. Strict Scope Adherence

**DO**:
- Edit only files within your `SCOPE_GLOBS`
- Ask Jarvis if you need to expand scope
- Document any scope changes in your handoff report

**DON'T**:
- Touch files outside your scope
- Modify "just one line" in a shared file
- Assume you know better than the scope definition

### 2. Global-Lock Awareness

The following areas are **global-locked** and require sequential access:

```yaml
Global-Lock Areas:
  - .woodpecker.yml          # CI configuration
  - pyproject.toml           # Dependencies
  - docs/bmm-workflow-status.yaml    # Status tracking
  - docs/validation/validation-registry.yaml  # Validation
  - infrastructure/terraform/        # Infrastructure
  - AGENTS.md                # Agent instructions
  - scripts/swarm/*.py       # Swarm infrastructure
```

**Rule**: If your work touches any global-lock area, it MUST be sequential (not parallel).

### 3. Dependency Management

When your work depends on another story:

```yaml
# In your worker contract
DEPENDS_ON:
  - story_id: ST-OTHER-001
    artifact: "src/shared/module.py"
    status: "completed"
```

**Strategy**:
1. Check dependency status in `docs/bmm-workflow-status.yaml`
2. If not complete, ask Jarvis to reschedule
3. Never assume dependencies will be ready

### 4. Communication Protocols

#### Redis Communication

Use Redis for lightweight state sharing:

```python
# Log iteration progress
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-XXX",
    value=json.dumps({
        "phase": "implementation",
        "status": "in_progress",
        "timestamp": datetime.now().isoformat(),
        "key_decisions": ["Decision 1", "Decision 2"]
    })
)

# Share intermediate results
redis_state_hset(
    name="bmad:chiseai:story:ST-XXX:artifacts",
    key="intermediate_result",
    value=json.dumps(result_data)
)
```

#### Qdrant Communication

Use Qdrant for knowledge persistence:

```python
# Store learnings for future agents
qdrant_qdrant-store(
    information="""
    Decision: Used Redis hash for ownership tracking
    Rationale: Atomic operations prevent race conditions
    Context: ST-XXX implementation
    """,
    metadata={
        "story_id": "ST-XXX",
        "type": "decision",
        "tags": ["ownership", "redis", "concurrency"]
    }
)

# Query previous learnings
results = qdrant_qdrant-find(query="ownership conflict resolution")
```

### 5. Handoff Procedures

#### Handoff to Jarvis

When completing work, provide:

```yaml
WORKER_COMPLETION_REPORT:
  story_id: "ST-XXX"
  branch: "feature/ST-XXX-description"
  head_sha: "abc123def456"
  
  files_changed:
    - path: "src/module/file.py"
      change_type: "modified"
      lines_added: 45
      lines_removed: 12
      summary: "Added feature X"
  
  test_summary:
    command: "pytest tests/test_module/ -v"
    result: "passed"
    counts: "15 passed, 0 failed, 0 skipped"
    coverage: "87%"
  
  validation:
    - type: "lint"
      command: "ruff check src/"
      result: "PASS"
    - type: "security"
      command: "bandit -r src/"
      result: "PASS"
  
  blockers: "None"
  
  handoff_notes: |
    - Feature X implemented per AC
    - All tests passing
    - Ready for PR creation
```

#### Receiving Handoff

When receiving work from another agent:

1. **Read the handoff report** completely
2. **Verify branch state**: `git status -sb`
3. **Check ownership**: Verify scope ownership transferred
4. **Run tests**: Ensure tests pass before starting
5. **Ask questions**: Clarify any ambiguities with Jarvis

## Evidence Collection Requirements

### Required Evidence

Every PR must include:

#### 1. Test Evidence

```bash
# Run tests and capture output
pytest tests/test_module/ -v --tb=short 2>&1 | tee test_output.txt

# Coverage report
pytest --cov=src/module --cov-report=term-missing tests/test_module/
```

#### 2. Lint Evidence

```bash
# Run linting
ruff check src/ 2>&1 | tee lint_output.txt

# Format check
black --check src/ 2>&1 | tee format_output.txt
```

#### 3. Security Evidence

```bash
# Security scan
bandit -r src/ -f json -o security_report.json
```

#### 4. Git Evidence

```bash
# Show what changed
git diff --stat HEAD~1

# Show commit log
git log --oneline -5
```

### Evidence Format

Include evidence in your handoff:

```markdown
## Evidence

### Test Results
```
$ pytest tests/test_module/ -v
==================== 15 passed in 2.34s ====================
```

### Coverage
```
Name                           Stmts   Miss  Cover
--------------------------------------------------
src/module/feature.py             45      3    93%
```

### Lint
```
$ ruff check src/
All checks passed!
```

### Security
```
$ bandit -r src/
No issues identified.
```
```

## Communication Protocols

### 1. Iteration Logging

Log every significant iteration:

```python
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}",
    value=json.dumps({
        "iteration": iteration_number,
        "phase": "implementation",  # planning, implementation, testing, review
        "status": "in_progress",    # in_progress, blocked, completed
        "started_at": datetime.now().isoformat(),
        "key_decisions": [
            "Decision 1 with rationale",
            "Decision 2 with rationale"
        ],
        "learnings": [
            "What worked well",
            "What to avoid next time"
        ],
        "blockers": []  # or list of blockers
    })
)
```

### 2. Incident Reporting

If something goes wrong, log an incident:

```python
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:{story_id}:incidents",
    value=json.dumps({
        "type": "ownership_conflict",  # or "test_failure", "merge_conflict", etc.
        "severity": "P2",  # P0=critical, P1=high, P2=medium, P3=low
        "detected_at": datetime.now().isoformat(),
        "description": "What went wrong",
        "root_cause": "Why it happened",
        "missed_signal": "What we should have caught",
        "prevention_rule": "How to prevent next time",
        "resolution": "How it was resolved",
        "follow_up": ["Action item 1", "Action item 2"]
    })
)
```

### 3. Status Updates

Keep Jarvis informed:

```markdown
## Status Update - ST-XXX

**Progress**: 75% complete
**Phase**: Testing
**ETA**: 2 hours

**Completed**:
- [x] Feature implementation
- [x] Unit tests
- [ ] Integration tests (in progress)

**Blockers**: None

**Risks**: Low - on track for completion
```

## Parallel Work Guidelines

### When Parallel Work is Safe

Parallel work is safe when ALL of the following are true:

1. **Disjoint Scopes**: No overlapping files
2. **No Shared Dependencies**: Changes don't affect the same modules
3. **No Global-Lock Areas**: Neither scope touches global-lock files
4. **No Ordering Dependencies**: Work items are independent

### Parallel Work Checklist

Before starting parallel work:

```markdown
## Parallel Work Pre-Flight Checklist

- [ ] Scopes verified disjoint via `git diff --name-only`
- [ ] No global-lock areas in any scope
- [ ] Ownership claimed for all scopes
- [ ] Integration plan defined
- [ ] Rollback plan documented
- [ ] Communication protocol established
```

### Conflict Detection

If you detect a conflict:

1. **STOP immediately** - Do not proceed with edits
2. **Document the conflict**:
   ```python
   conflict = {
       "my_scope": ["src/module/a.py"],
       "conflicting_scope": ["src/module/b.py"],
       "conflicting_owner": "ST-OTHER-001/agent",
       "detected_at": datetime.now().isoformat()
   }
   ```
3. **Log incident** to Redis
4. **Report to Jarvis** with full context
5. **Await resolution** - Do not proceed until cleared

## Code Quality Standards

### 1. Test Coverage

- Minimum 80% coverage for new code
- 100% coverage for critical paths
- All edge cases tested
- Integration tests for cross-module changes

### 2. Documentation

- Docstrings for all public functions
- Comments for complex logic
- README updates for user-facing changes
- Architecture Decision Records (ADRs) for significant decisions

### 3. Code Style

- Follow PEP 8
- Use `black` for formatting
- Use `ruff` for linting
- Maximum function length: 50 lines
- Maximum cyclomatic complexity: 10

### 4. Security

- No hardcoded secrets
- Input validation on all public APIs
- Use parameterized queries (no SQL injection)
- Follow principle of least privilege

## Emergency Procedures

### Emergency Stop

If you discover a critical issue:

```bash
# Activate emergency stop
redis-cli -p 6380 HSET bmad:chiseai:system emergency_stop enabled

# Notify team
echo "🚨 EMERGENCY STOP ACTIVATED - ST-XXX" | \
  discord_webhook --channel #alerts
```

### Rollback Procedure

If you need to rollback:

```bash
# Identify last good commit
git log --oneline -10

# Create rollback branch
git checkout -b rollback/ST-XXX-emergency

# Revert problematic commit
git revert abc123def456

# Push and create PR
git push -u origin rollback/ST-XXX-emergency
```

## Summary Checklist

Before starting work:
- [ ] Read worker contract completely
- [ ] Verify session with `session.py verify`
- [ ] Check scope ownership in Redis
- [ ] Review related Qdrant memories

During work:
- [ ] Stay within SCOPE_GLOBS
- [ ] Log iterations to Redis
- [ ] Run tests frequently
- [ ] Commit with proper messages

Before handoff:
- [ ] All tests passing
- [ ] Lint checks clean
- [ ] Security scan clean
- [ ] Evidence collected
- [ ] Ownership released
- [ ] Completion report prepared

## See Also

- `quickstart.md` - Getting started guide
- `workflow-paths.md` - Detailed workflow path documentation
- `troubleshooting.md` - Common issues and solutions
- `../runbooks/agent-autonomous-workflow.md` - Operational procedures
