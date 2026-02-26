# Troubleshooting Guide

## Overview

This guide provides solutions for common issues encountered when working in the ChiseAI Agent Swarm. If you encounter an issue not covered here, report it to Jarvis immediately.

## Quick Diagnostics

Run this diagnostic checklist first:

```bash
# 1. Check your environment
python3 --version  # Should be 3.11+
git --version      # Should be 2.40+
docker ps          # Should show running containers

# 2. Check connectivity
redis-cli -p 6380 ping  # Should return PONG
curl http://localhost:6334  # Qdrant should respond

# 3. Check git state
git status -sb
git branch --show-current
git log --oneline -3

# 4. Check session
python3 scripts/swarm/session.py verify \
  --story-id=ST-XXX \
  --branch=feature/ST-XXX-description
```

## Common Issues

### 1. Session Verification Failed

**Symptom**:
```
ERROR: Missing .swarm-session.json
```

**Root Cause**: Session not initialized or worktree not set up

**Resolution**:

```bash
# Option 1: Start a new session
python3 scripts/swarm/session.py start \
  --story-id=ST-XXX \
  --agent=your-agent \
  --branch=feature/ST-XXX-description \
  --worktree-root=/tmp/worktrees/ST-XXX-your-agent

# Option 2: If already on correct branch, verify without worktree
python3 scripts/swarm/session.py verify \
  --story-id=ST-XXX \
  --branch=feature/ST-XXX-description \
  --worktree-path=/home/tacopants/projects/ChiseAI
```

### 2. Scope Ownership Conflict

**Symptom**:
```
❌ CONFLICT: src:module:name owned by ST-OTHER-001/agent
```

**Root Cause**: Another story owns the scope you need to edit

**Resolution**:

1. **STOP immediately** - Do not proceed with edits
2. **Document the conflict**:
   ```python
   conflict_info = {
       "my_story": "ST-XXX",
       "my_scope": ["src/module/name"],
       "conflicting_owner": "ST-OTHER-001/agent",
       "conflicting_scope": "src:module:name",
       "detected_at": "2026-02-26T10:00:00Z"
   }
   ```
3. **Log incident**:
   ```python
   redis_state_rpush(
       name="bmad:chiseai:iterlog:story:ST-XXX:incidents",
       value=json.dumps({
           "type": "ownership_conflict",
           "severity": "P2",
           "details": conflict_info
       })
   )
   ```
4. **Report to Jarvis** with full context
5. **Await resolution** - Do not proceed until cleared

### 3. CI Failure Diagnosis

#### 3.1 Black Formatting Failure

**Symptom**:
```
black --check src/
would reformat src/module/file.py
Oh no! 💥 💔 💥
1 file would be reformatted.
```

**Resolution**:

```bash
# Auto-format the code
black src/

# Verify fix
black --check src/

# Commit the formatting changes
git add .
git commit -m "style: apply black formatting (ST-XXX)"
```

#### 3.2 Ruff Lint Failure

**Symptom**:
```
ruff check src/
src/module/file.py:42:5: E302 expected 2 blank lines
src/module/file.py:56:1: F401 imported but unused
```

**Resolution**:

```bash
# Auto-fix where possible
ruff check src/ --fix

# Check remaining issues
ruff check src/

# Manually fix remaining issues
# Then commit
git add .
git commit -m "fix: resolve lint issues (ST-XXX)"
```

#### 3.3 Bandit Security Finding

**Symptom**:
```
bandit -r src/
Issue: [B105:hardcoded_password_string]
Severity: Medium
Location: src/module/file.py:42
```

**Resolution**:

1. **Review the finding** - Determine if it's a real issue
2. **Fix if real**:
   ```python
   # BAD
   password = "hardcoded123"
   
   # GOOD
   password = os.environ.get("PASSWORD")
   ```
3. **Suppress if false positive** (with justification):
   ```python
   # nosec B105 - This is a test fixture, not a real password
   password = "test_password_123"
   ```
4. **Commit the fix**:
   ```bash
   git add .
   git commit -m "fix: resolve bandit security finding (ST-XXX)"
   ```

#### 3.4 Pytest Failure

**Symptom**:
```
pytest tests/
FAILED tests/test_module.py::test_function - AssertionError
```

**Resolution**:

```bash
# Run specific failing test with verbose output
pytest tests/test_module.py::test_function -v --tb=long

# Run with debugger
pytest tests/test_module.py::test_function --pdb

# Check test coverage for the failing module
pytest tests/test_module.py --cov=src/module --cov-report=term-missing
```

**Common Test Failure Causes**:

| Cause | Solution |
|-------|----------|
| Import error | Check PYTHONPATH, install missing dependencies |
| Fixture failure | Verify test fixtures are properly set up |
| Assertion failure | Check expected vs actual values in test |
| Timeout | Increase timeout or optimize test |
| Flaky test | Add retry logic or fix race condition |

### 4. Merge Conflict Resolution

**Symptom**:
```
git rebase origin/main
CONFLICT (content): Merge conflict in src/module/file.py
```

**Resolution**:

```bash
# 1. See conflict details
git status

# 2. Open conflicted file and resolve
# Look for <<<<<<< HEAD markers

# 3. Mark as resolved
git add src/module/file.py

# 4. Continue rebase
git rebase --continue

# 5. If rebase is too complex, abort and merge instead
git rebase --abort
git merge origin/main
```

**Conflict Resolution Best Practices**:

1. **Understand both changes** before resolving
2. **Keep both changes** if they address different concerns
3. **Test after resolution** - Run tests to ensure resolution is correct
4. **Document complex resolutions** in commit message

### 5. Redis Connection Issues

**Symptom**:
```
redis-cli -p 6380 ping
Could not connect to Redis at localhost:6380: Connection refused
```

**Resolution**:

```bash
# Check if Redis container is running
docker ps --filter name=chiseai-redis

# If not running, start it
docker start chiseai-redis

# If container doesn't exist, check infrastructure
# (May need to run terraform or docker-compose)

# Verify connection from within container (if in Docker)
redis-cli -h host.docker.internal -p 6380 ping
```

### 6. Qdrant Connection Issues

**Symptom**:
```
curl http://localhost:6334
curl: (7) Failed to connect
```

**Resolution**:

```bash
# Check if Qdrant container is running
docker ps --filter name=chiseai-qdrant

# If not running, start it
docker start chiseai-qdrant

# Verify connection
curl http://localhost:6334/collections
```

### 7. Git Push Rejected

**Symptom**:
```
git push
! [rejected]        feature/ST-XXX-description -> feature/ST-XXX-description
error: failed to push some refs
```

**Resolution**:

```bash
# Fetch latest changes
git fetch origin

# Rebase on latest main
git rebase origin/main

# Resolve any conflicts, then push
git push --force-with-lease origin feature/ST-XXX-description
```

**Note**: Always use `--force-with-lease` instead of `--force` to prevent overwriting others' work.

### 8. Worktree Issues

**Symptom**:
```
fatal: 'feature/ST-XXX-description' is already used by worktree
```

**Resolution**:

```bash
# List existing worktrees
git worktree list

# Remove stale worktree
git worktree remove /path/to/worktree

# Or force remove if dirty
git worktree remove --force /path/to/worktree

# Prune any stale worktree references
git worktree prune
```

### 9. Docker Container Issues

**Symptom**:
```
docker ps
# No containers running
```

**Resolution**:

```bash
# Check all containers (including stopped)
docker ps -a

# Start infrastructure containers
cd infrastructure/terraform
docker-compose up -d

# Or start specific containers
docker start chiseai-redis chiseai-postgres chiseai-qdrant

# Check logs if containers won't start
docker logs chiseai-redis
```

### 10. Import Errors

**Symptom**:
```
python -c "import src.module"
ModuleNotFoundError: No module named 'src'
```

**Resolution**:

```bash
# Set PYTHONPATH
export PYTHONPATH=/home/tacopants/projects/ChiseAI:$PYTHONPATH

# Or use python -m to run modules
python -m pytest tests/test_module.py

# Install package in editable mode
pip install -e .
```

## Emergency Procedures

### Emergency Stop Activation

If you discover a critical issue that requires stopping all automation:

```bash
# Activate emergency stop
redis-cli -p 6380 HSET bmad:chiseai:system emergency_stop enabled

# Verify activation
redis-cli -p 6380 HGET bmad:chiseai:system emergency_stop
# Should return: enabled
```

**Effects of Emergency Stop**:
- All SAFE path auto-merges are disabled
- All STANDARD path PRs are escalated to human review
- New PRs cannot be auto-approved
- Emergency stop state is logged to Redis

**To Deactivate**:

```bash
# Only authorized personnel (Jarvis or human) should deactivate
redis-cli -p 6380 HDEL bmad:chiseai:system emergency_stop
```

### Rollback Procedure

If you need to rollback a problematic change:

```bash
# 1. Identify the problematic commit
git log --oneline -10

# 2. Create rollback branch
git checkout -b rollback/ST-XXX-emergency

# 3. Revert the commit
git revert abc123def456 --no-edit

# 4. Push rollback branch
git push -u origin rollback/ST-XXX-emergency

# 5. Report to Jarvis for emergency PR creation
```

### Incident Reporting Template

When reporting an incident, use this template:

```yaml
INCIDENT:
  story_id: ST-XXX
  batch: 1
  scope_globs: ["src/module/"]
  
  symptom: |
    Describe what went wrong
    Include error messages
    
  root_cause: |
    Why it happened
    What conditions led to the issue
    
  missed_signal: |
    What we should have caught earlier
    What warning signs were ignored
    
  prevention_rule: |
    How to prevent this next time
    What process change is needed
    
  follow_up_tasks:
    - Task 1 to prevent recurrence
    - Task 2 to improve detection
```

## Debugging Tips

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Redis State

```python
# List all ownership keys
redis_state_hgetall(name="bmad:chiseai:ownership")

# Check system state
redis_state_hgetall(name="bmad:chiseai:system")

# View iteration log
redis_state_lrange(name="bmad:chiseai:iterlog:story:ST-XXX", start=0, stop=-1)
```

### Validate Status Sync

```bash
# Run status sync validation
python3 scripts/validate_status_sync.py

# With verbose output
python3 scripts/validate_status_sync.py --verbose
```

### Check Docker Network

```bash
# Verify containers are on correct network
docker network inspect chiseai

# Check container connectivity
docker exec chiseai-api-final ping chiseai-redis -c 3
```

## Getting Help

If you encounter an issue not covered here:

1. **Check the logs**:
   ```bash
   # Application logs
   docker logs chiseai-api-final
   
   # CI logs
   docker logs woodpecker-server
   
   # System logs
   journalctl -u docker
   ```

2. **Search Qdrant for similar issues**:
   ```python
   results = qdrant_qdrant-find(query="similar error message")
   ```

3. **Report to Jarvis** with:
   - Full error message
   - Steps to reproduce
   - What you've already tried
   - Relevant logs

4. **Escalate if critical**:
   - P0 (Critical): System down, data loss risk
   - P1 (High): Major feature blocked
   - P2 (Medium): Workaround exists
   - P3 (Low): Minor inconvenience

## See Also

- `quickstart.md` - Getting started guide
- `workflow-paths.md` - Workflow path documentation
- `best-practices.md` - Scope ownership and best practices
- `../runbooks/agent-autonomous-workflow.md` - Operational procedures
