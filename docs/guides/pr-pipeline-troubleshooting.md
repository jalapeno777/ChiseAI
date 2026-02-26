# PR Pipeline Troubleshooting

Common issues and solutions for the autonomous PR pipeline.

## Quick Diagnostics

### Check Current State

```bash
# Git status
git status -sb

# Current branch
git branch --show-current

# Worktree status
python3 scripts/pr_lifecycle/agent_cli.py worktree-status

# Session info
cat .swarm-session.json 2>/dev/null || echo "No active session"
```

### Validate Environment

```bash
# Check tools
python3 --version
git --version
redis-cli --version

# Check connectivity
redis-cli -h host.docker.internal -p 6380 PING

# Check pre-commit hooks
ls -la .git/hooks/pre-commit
```

## Common Errors

### Session Errors

#### "Missing .swarm-session.json"

**Cause:** Not in a worktree or session not started

**Solution:**
```bash
# Start a new session
python3 scripts/swarm/session.py start \
    --story-id=ST-XXX \
    --agent=<your-id> \
    --branch=feature/ST-XXX-description
```

#### "Branch mismatch"

**Cause:** Current branch doesn't match session

**Solution:**
```bash
# Check current branch
git branch --show-current

# Switch to correct branch
git checkout feature/ST-XXX-description

# Or update session (if intentional)
# Edit .swarm-session.json branch field
```

#### "Redis leases not found"

**Cause:** Redis unavailable during session start

**Solution:**
```bash
# Verify Redis connectivity
redis-cli -h host.docker.internal -p 6380 PING

# If Redis is down, continue without leases
# Document in handoff that Redis was unavailable
```

### Git Errors

#### "Working tree dirty"

**Cause:** Uncommitted changes when trying to switch branches

**Solution:**
```bash
# Option 1: Commit changes
git add .
git commit -m "wip: temporary commit"

# Option 2: Stash changes
git stash

# Option 3: Discard changes (careful!)
git checkout -- .
git clean -fd
```

#### "Merge conflict"

**Cause:** Changes conflict with target branch

**Solution:**
```bash
# See conflicting files
git status

# Open each file and resolve markers
# Look for <<<<<<<, =======, >>>>>>>

# Mark as resolved
git add <file>

# Complete rebase/merge
git rebase --continue
# or
git merge --continue
```

**Prevention:**
```bash
# Rebase frequently
git fetch origin
git rebase origin/main
```

#### "Permission denied"

**Cause:** SSH key or permissions issue

**Solution:**
```bash
# Check SSH key
ssh -T git@host.docker.internal

# Check remote URL
git remote -v

# Fix if needed
git remote set-url origin <correct-url>
```

### Scope Ownership Errors

#### "Scope already owned"

**Cause:** Another story/agent owns the scope

**Solution:**
```bash
# Check who owns it
redis-cli -h host.docker.internal -p 6380 \
    HGET bmad:chiseai:ownership src:module

# Options:
# 1. Wait for owner to complete
# 2. Request re-scope from Jarvis
# 3. Use --force (if you're the rightful owner)
```

#### "Cannot claim scope"

**Cause:** Redis connection issue

**Solution:**
```bash
# Test Redis
redis-cli -h host.docker.internal -p 6380 PING

# If fails, check:
# - Is Redis running?
# - Correct host/port?
# - Network connectivity?
```

### CI Failures

#### "pytest failed"

**Diagnosis:**
```bash
# Run locally to see details
pytest tests/ -v --tb=short

# Run specific failing test
pytest tests/test_file.py::test_function -v

# Check coverage
pytest tests/ --cov=src --cov-report=term-missing
```

**Common causes:**
- Missing test dependencies
- Environment differences
- Race conditions
- Resource leaks

**Solution:**
```bash
# Update dependencies
pip install -r requirements-dev.txt

# Run in clean environment
docker run --rm -v $(pwd):/app -w /app python:3.11 pytest tests/

# Debug specific test
pytest tests/test_file.py::test_function -v -s --tb=long
```

#### "ruff check failed"

**Solution:**
```bash
# See issues
ruff check src/ scripts/

# Auto-fix
ruff check --fix src/ scripts/

# Check specific file
ruff check src/module.py
```

#### "black check failed"

**Solution:**
```bash
# Format code
black src/ scripts/

# Check specific file
black src/module.py
```

#### "bandit security check failed"

**Diagnosis:**
```bash
# See security issues
bandit -r src/ -f txt

# Get more details
bandit -r src/ -f json -o bandit-report.json
```

**Common issues:**
- Hardcoded passwords
- Use of eval/exec
- Insecure temp files
- Weak cryptography

### Validation Errors

#### "Status sync validation failed"

**Cause:** docs/bmm-workflow-status.yaml out of sync

**Solution:**
```bash
# Update status file
# Edit docs/bmm-workflow-status.yaml
# Set your story status to "in_progress"

# Validate
python3 scripts/validate_status_sync.py
```

#### "Pre-commit gates failed"

**Diagnosis:**
```bash
# Run individual checks
black --check src/ scripts/
ruff check src/ scripts/
pytest tests/ -x

# See which one fails
```

## Path-Specific Issues

### SAFE Path Issues

#### "Auto-approval failed"

**Cause:** Change detected as higher risk

**Solution:**
```bash
# Check what triggered higher path
python3 scripts/pr_lifecycle/pr_path_selector.py \
    --story-id=ST-XXX \
    --files="src/"

# If truly safe, may need manual override
# Report to Jarvis
```

### STANDARD Path Issues

#### "Human approval delayed"

**Cause:** Reviewers busy or unclear PR

**Solution:**
- Ensure PR description is clear
- Add context in comments
- Ping reviewers politely
- Check if dependencies are clear

### COMPLEX Path Issues

#### "Extended validation failed"

**Cause:** Complex path has additional gates

**Solution:**
```bash
# Check all requirements
python3 scripts/pr_lifecycle/complex_path_gate.py --pr=<number>

# Address each failing gate
```

## Recovery Procedures

### Recovering from Failed Rebase

```bash
# If rebase goes wrong
git rebase --abort

# Reset to last known good state
git reset --hard HEAD@{1}

# Or use reflog to find good state
git reflog
git reset --hard <ref>
```

### Recovering Lost Commits

```bash
# See recent operations
git reflog

# Find your commits
# Look for your branch or commit messages

# Recover
git checkout -b recovery-branch <ref>

# Cherry-pick to main branch
git checkout feature/ST-XXX
git cherry-pick <commit>
```

### Recovering from Bad Merge

```bash
# If merge commit is bad
# Find parent commits
git log --oneline --graph

# Reset to before merge
git reset --hard <commit-before-merge>

# Redo merge carefully
git merge <branch>
```

## Docker Issues

### "Cannot connect to host.docker.internal"

**Cause:** Docker networking issue

**Solution:**
```bash
# For Linux Docker, add host mapping
docker run --add-host=host.docker.internal:host-gateway ...

# Or use container name if on same network
docker run --network chiseai ...
```

### "Container not found"

**Solution:**
```bash
# List running containers
docker ps

# Check all containers (including stopped)
docker ps -a

# Start if needed
docker start <container>
```

## Redis Issues

### "Redis connection refused"

**Diagnosis:**
```bash
# Check if Redis is running
docker ps | grep redis

# Check port
redis-cli -h host.docker.internal -p 6380 PING

# Check logs
docker logs chiseai-redis
```

**Solution:**
```bash
# Start Redis if not running
docker start chiseai-redis

# Or create if doesn't exist
docker run -d --name chiseai-redis -p 6380:6380 redis:7-alpine
```

### "Redis key not found"

**Cause:** Key expired or never set

**Solution:**
```bash
# Check if key exists
redis-cli -h host.docker.internal -p 6380 \
    EXISTS bmad:chiseai:ownership

# List all keys
redis-cli -h host.docker.internal -p 6380 \
    KEYS 'bmad:chiseai:*'

# Recreate if needed
redis-cli -h host.docker.internal -p 6380 \
    HSET bmad:chiseai:ownership src:module "value"
```

## Escalation Procedures

### When to Escalate

Escalate to Jarvis when:
- Ownership conflict cannot be resolved
- CI fails repeatedly with unclear cause
- Merge conflicts are complex
- System appears broken
- You've tried 3+ times without success

### How to Escalate

```markdown
**ESCALATION: [Brief description]**

**Story:** ST-XXX
**Agent:** your-id
**Issue:** [Clear description]

**What I've tried:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Current state:**
- Branch: feature/ST-XXX
- Last commit: abc123
- Error: [exact error message]

**Request:** [What help you need]
```

### Emergency Contacts

- **Jarvis**: Orchestrator for all issues
- **Merlin**: Merge authority for main
- **Captain Craig**: Infrastructure and governance

## Debugging Tools

### Verbose Mode

```bash
# Run with verbose output
python3 script.py --verbose
python3 script.py -v
python3 script.py --debug
```

### Logging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python3 script.py

# Or in Python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Tracing

```bash
# Trace system calls
strace -f python3 script.py 2>&1 | less

# Trace library calls
ltrace python3 script.py 2>&1 | less
```

### Network Debugging

```bash
# Test connectivity
curl -v http://host.docker.internal:3000/api/v1/version

# Check DNS
nslookup host.docker.internal

# Test port
telnet host.docker.internal 6380
```

## Prevention Checklist

Before starting work:

- [ ] Session started correctly
- [ ] Scope ownership claimed
- [ ] On correct branch
- [ ] Working tree clean
- [ ] Redis accessible
- [ ] Tests run locally

Before submitting:

- [ ] Pre-commit gates pass
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] No debug code
- [ ] Commit messages proper
- [ ] Rebased on latest main

## Common Command Reference

| Issue | Command |
|-------|---------|
| Check git status | `git status -sb` |
| Check branch | `git branch --show-current` |
| Check Redis | `redis-cli PING` |
| Check ownership | `redis-cli HGET bmad:chiseai:ownership <key>` |
| Run tests | `pytest tests/ -x` |
| Run linting | `ruff check src/` |
| Run formatting | `black src/` |
| Check session | `cat .swarm-session.json` |
| View logs | `docker logs <container>` |

## Getting More Help

1. **Check this guide first** - Search for your error
2. **Check the FAQ** - [PR Pipeline FAQ](pr-pipeline-faq.md)
3. **Check skills** - `.opencode/skills/` directory
4. **Ask Jarvis** - For orchestration issues
5. **Document solution** - Add to this guide

---

**Related Documents:**
- [Agent Onboarding Guide](agent-onboarding-guide.md)
- [PR Pipeline Quick Start](pr-pipeline-quickstart.md)
- [PR Pipeline Best Practices](pr-pipeline-best-practices.md)
- [PR Pipeline FAQ](pr-pipeline-faq.md)
