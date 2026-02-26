# Agent Quick Start Guide

Welcome to the ChiseAI Agent Swarm! This guide will get you up and running with the autonomous PR pipeline in minutes.

## Overview

The ChiseAI Agent Swarm is a tiered automation system that enables 10+ AI agents to work autonomously on software development tasks. The system uses three workflow paths:

- **SAFE Path**: Auto-approve for low-risk changes
- **STANDARD Path**: GitReviewBot review for medium-risk changes
- **COMPLEX Path**: Human escalation for high-risk changes

## Prerequisites

Before you start, ensure you have:

1. **Environment Access**
   - Docker daemon access
   - Redis (port 6380) and Qdrant (port 6334) connectivity
   - Gitea repository access
   - Git configured with your credentials

2. **Required Tools**
   - Python 3.11+
   - Git 2.40+
   - Docker 24.0+
   - `ruff`, `black`, `bandit`, `pytest` installed

3. **Knowledge Prerequisites**
   - Read `AGENTS.md` for role definitions
   - Read `.opencode/agent/<YourRole>.md` for your specific instructions
   - Familiarity with the tiered workflow paths (see `workflow-paths.md`)

## First PR Workflow Walkthrough

### Step 1: Claim Your Story

When Jarvis assigns you a story, you'll receive a **Worker Contract** containing:

```yaml
SCOPE_GLOBS:
  - src/your-module/
  - tests/test_your_module/

FORBIDDEN_GLOBS:
  - .woodpecker.yml
  - pyproject.toml
  - docs/bmm-workflow-status.yaml

BRANCH: feature/ST-XXX-your-story
WORKTREE_PATH: /tmp/worktrees/ST-XXX-your-agent
```

### Step 2: Start Your Session

```bash
# Verify your session
python3 scripts/swarm/session.py verify \
  --story-id=ST-XXX \
  --branch=feature/ST-XXX-your-story \
  --worktree-path=/tmp/worktrees/ST-XXX-your-agent

# If session doesn't exist, start it
python3 scripts/swarm/session.py start \
  --story-id=ST-XXX \
  --agent=your-agent-name \
  --branch=feature/ST-XXX-your-story \
  --worktree-root=/tmp/worktrees/ST-XXX-your-agent
```

### Step 3: Check Ownership

Before making any edits, verify scope ownership:

```python
# Check Redis ownership
import json
from tools import redis_state_hget

scope_slug = "src:your:module"
owner = redis_state_hget(name="bmad:chiseai:ownership", key=scope_slug)

if owner and "ST-XXX" not in owner:
    print(f"❌ CONFLICT: {scope_slug} owned by {owner}")
    print("STOP and report to Jarvis immediately!")
else:
    print(f"✅ Ownership verified: {owner}")
```

### Step 4: Implement Your Changes

1. **Write code** following the project's style guidelines
2. **Add tests** for new functionality
3. **Run local validation**:

```bash
# Format check
black --check src/

# Lint check
ruff check src/

# Security scan
bandit -r src/

# Run tests
pytest tests/ -v --tb=short
```

### Step 5: Gather Evidence

Document your work with:

```bash
# Files changed
git diff --stat HEAD~1

# Test results
pytest tests/test_your_module/ -v > test_results.txt

# Coverage report
pytest --cov=src/your_module tests/test_your_module/
```

### Step 6: Commit and Push

```bash
# Stage changes
git add .

# Commit with proper format
git commit -m "feat(module): description of changes (ST-XXX)

- Change 1
- Change 2
- Change 3

Refs: ST-XXX"

# Push to origin
git push -u origin feature/ST-XXX-your-story
```

### Step 7: Report Completion

Provide Jarvis with your **Worker Completion Report**:

```yaml
WORKER_COMPLETION_REPORT:
  story_id: "ST-XXX"
  branch: "feature/ST-XXX-your-story"
  head_sha: "abc123def456"
  test_summary:
    command: "pytest tests/test_your_module/ -v"
    result: "passed"
    counts: "15 passed, 0 failed, 0 skipped"
    duration: "2.34s"
  status_sync_proof:
    command: "python3 scripts/validate_status_sync.py"
    result: "PASS"
  blockers: "None"
```

## Common Commands Cheat Sheet

### Git Commands

```bash
# Check status
git status -sb

# Create feature branch
git checkout -b feature/ST-XXX-description

# Sync with main
git fetch origin
git rebase origin/main

# View changes
git diff --stat

# Safe force push after rebase
git push --force-with-lease origin feature/ST-XXX-description
```

### Validation Commands

```bash
# Run all checks
black --check src/ && ruff check src/ && bandit -r src/

# Run tests with coverage
pytest tests/ --cov=src/ --cov-report=term-missing

# Validate status sync
python3 scripts/validate_status_sync.py
```

### Redis Commands

```python
# Claim ownership
redis_state_hset(
    name="bmad:chiseai:ownership",
    key="src:your:module",
    value="ST-XXX/agent/timestamp",
    expire_seconds=432000  # 5 days
)

# Check ownership
owner = redis_state_hget(name="bmad:chiseai:ownership", key="src:your:module")

# Release ownership
redis_state_hdel(name="bmad:chiseai:ownership", key="src:your:module")

# Log iteration
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:ST-XXX",
    value=json.dumps({
        "phase": "implementation",
        "status": "in_progress",
        "timestamp": datetime.now().isoformat()
    })
)
```

### Session Commands

```bash
# Start session
python3 scripts/swarm/session.py start \
  --story-id=ST-XXX \
  --agent=your-agent \
  --branch=feature/ST-XXX-description

# Verify session
python3 scripts/swarm/session.py verify \
  --story-id=ST-XXX \
  --branch=feature/ST-XXX-description

# Close session
python3 scripts/swarm/session.py close \
  --story-id=ST-XXX
```

## Workflow Path Selection

Use this quick guide to determine which workflow path applies:

| Criteria | SAFE Path | STANDARD Path | COMPLEX Path |
|----------|-----------|---------------|--------------|
| **Files touched** | ≤5 files, ≤200 lines | 6-15 files, 200-500 lines | >15 files or >500 lines |
| **Risk level** | Documentation, tests | Feature additions | Infrastructure, security |
| **CI changes** | None | None | Any CI modification |
| **Review** | Auto-merge | GitReviewBot | Human required |
| **Examples** | Docstrings, comments | New features | Terraform, secrets |

## Next Steps

1. Read `workflow-paths.md` for detailed path explanations
2. Read `best-practices.md` for scope ownership and conflict avoidance
3. Read `troubleshooting.md` for common issues and solutions
4. Review `../runbooks/agent-autonomous-workflow.md` for operational procedures

## Getting Help

- **Scope conflicts**: Report to Jarvis immediately
- **CI failures**: See `troubleshooting.md` section on CI diagnosis
- **Merge conflicts**: Follow the procedure in `troubleshooting.md`
- **Emergency**: Use the emergency procedures in `troubleshooting.md`

## Quick Reference Links

- [AGENTS.md](../../AGENTS.md) - Role definitions and responsibilities
- [Skills](../../.opencode/skills/) - Available skills and their usage
- [Commands](../../.opencode/command/) - Workflow commands reference
- [BMM Workflow Status](../../docs/bmm-workflow-status.yaml) - Project status tracking

---

**Remember**: When in doubt, STOP and ask Jarvis. It's better to clarify than to create conflicts!
