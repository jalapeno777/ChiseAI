# Agent Onboarding Guide

Welcome to the ChiseAI autonomous PR pipeline! This guide will help you onboard as an AI agent and start contributing effectively.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Onboarding Checklist](#onboarding-checklist)
4. [Understanding the PR Pipeline](#understanding-the-pr-pipeline)
5. [First PR Walkthrough](#first-pr-walkthrough)
6. [Capability Requirements](#capability-requirements)
7. [Common Pitfalls](#common-pitfalls)
8. [Getting Help](#getting-help)

## Overview

The ChiseAI PR pipeline is an autonomous system that enables AI agents to safely contribute code through a structured review and merge process. The system has three PR paths:

- **SAFE Path**: For documentation, simple fixes, and low-risk changes
- **STANDARD Path**: For feature implementations with standard review
- **COMPLEX Path**: For high-risk changes requiring extensive validation

### Key Principles

1. **Data-First**: Gather all data before analysis
2. **Granular Tasks**: Small, clear validation criteria
3. **Sequential Work**: No parallel work until data foundation complete
4. **Quality Gates**: Each task must pass validation

## Prerequisites

Before you start, ensure you have:

- Git configured with user.name and user.email
- Access to the repository
- Redis connectivity (for scope ownership)
- Python environment with pytest, ruff, and black
- Understanding of basic Git operations

### Environment Setup

```bash
# Verify git configuration
git config user.name
git config user.email

# Verify Python tools
python3 -m pytest --version
python3 -m ruff --version
python3 -m black --version

# Verify Redis connectivity
redis-cli -h host.docker.internal -p 6380 PING
```

## Onboarding Checklist

Use the onboarding helper to track your progress:

```bash
# Validate your onboarding status
python3 scripts/pr_lifecycle/agent_onboarding.py --agent-id=<your-id> --validate

# View required reading list
python3 scripts/pr_lifecycle/agent_onboarding.py --reading-list
```

### Required Reading (In Order)

1. **[AGENTS.md](../../AGENTS.md)** - CRITICAL - Start here
   - Git safety essentials
   - Docker connectivity rules
   - Merge authority structure
   - Emergency procedures

2. **[Git Workflow Skill](../../.opencode/skills/chiseai-git-workflow/SKILL.md)** - CRITICAL
   - Branch strategy
   - PR workflow
   - Commit message format
   - Handoff procedures

3. **[Parallel Safety Skill](../../.opencode/skills/chiseai-parallel-safety/SKILL.md)** - HIGH
   - Scope ownership
   - Conflict prevention
   - Global-lock areas
   - Incident handling

4. **[Memory Operations Skill](../../.opencode/skills/chiseai-memory-ops/SKILL.md)** - HIGH
   - Redis usage patterns
   - Qdrant for long-term memory
   - TTL management
   - Fallback strategies

5. **Iteration Commands**
   - `chise-iterloop-start` - Start iteration
   - `chise-precommit-gates` - Validate before PR
   - `chise-iterloop-close` - Close iteration

### Setup Verification

- [ ] Git configured (user.name, user.email)
- [ ] Redis accessible
- [ ] Test environment working (pytest, ruff)
- [ ] Read AGENTS.md completely
- [ ] Read Git Workflow skill
- [ ] Understand scope ownership

## Understanding the PR Pipeline

### The Three PR Paths

#### SAFE Path

**Use for:**
- Documentation updates
- README improvements
- Comment additions
- Simple configuration changes
- Spelling/grammar fixes

**Characteristics:**
- Automated review only
- No human approval required
- Fastest path (minutes)
- Lowest risk

**Example:**
```bash
# SAFE path PR
python3 scripts/pr_lifecycle/pr_path_selector.py --story-id=ST-DOCS-001 --files="docs/"
# Output: SAFE path recommended
```

#### STANDARD Path

**Use for:**
- Feature implementations
- Bug fixes
- Refactoring
- New tests
- Configuration changes

**Characteristics:**
- Automated review
- Human approval required
- Standard timeline (hours to days)
- Medium risk

**Example:**
```bash
# STANDARD path PR
python3 scripts/pr_lifecycle/pr_path_selector.py --story-id=ST-FEAT-001 --files="src/feature.py"
# Output: STANDARD path recommended
```

#### COMPLEX Path

**Use for:**
- Architecture changes
- Security modifications
- Database migrations
- Critical path modifications
- High-risk changes

**Characteristics:**
- Extensive automated validation
- Multiple human approvals
- Extended timeline (days to weeks)
- Highest risk
- May require design review

**Example:**
```bash
# COMPLEX path PR
python3 scripts/pr_lifecycle/pr_path_selector.py --story-id=ST-ARCH-001 --files="src/core/architecture.py"
# Output: COMPLEX path recommended
```

### Workflow Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Start     │───▶│   Select     │───▶│   Claim     │
│   Story     │    │   PR Path    │    │   Scope     │
└─────────────┘    └──────────────┘    └─────────────┘
                                              │
                                              ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Merge     │◀───│   Handoff    │◀───│   Implement │
│   to Main   │    │   to Jarvis  │    │   Changes   │
└─────────────┘    └──────────────┘    └─────────────┘
```

## First PR Walkthrough

Let's walk through your first PR using the SAFE path.

### Step 1: Validate Onboarding

```bash
# Check if you're ready
python3 scripts/pr_lifecycle/agent_onboarding.py \
    --agent-id=<your-id> \
    --validate

# Expected output:
# ✓ Onboarding complete! Agent is ready for PR pipeline.
```

### Step 2: Start Swarm Session

```bash
# Start isolated worktree session
python3 scripts/swarm/session.py start \
    --story-id=ST-FIRST-001 \
    --agent=<your-id> \
    --branch=feature/ST-FIRST-001-first-pr \
    --scopes="docs/"

# Expected output:
# session.start: OK
# - worktree: /tmp/worktrees/...
# - branch: feature/ST-FIRST-001-first-pr
```

### Step 3: Claim Scope Ownership

```bash
# Reserve scope via CLI
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-FIRST-001 \
    --scope="docs/guides/"

# Expected output:
# ✓ Scope reserved successfully
```

### Step 4: Make Changes

Create a simple documentation file:

```bash
# Create a test file
echo "# Test Document\n\nThis is a test." > docs/guides/test-document.md

# Stage changes
git add docs/guides/test-document.md

# Commit with proper format
git commit -m "docs(guides): add test document (ST-FIRST-001)"
```

### Step 5: Run Pre-Commit Gates

```bash
# Validate before submission
python3 .opencode/command/chise-precommit-gates.md

# Or run manually:
black --check src/ scripts/
ruff check src/ scripts/
pytest tests/ -x --tb=short
```

### Step 6: Submit Work

```bash
# Submit via CLI
python3 scripts/pr_lifecycle/agent_cli.py submit \
    --story-id=ST-FIRST-001 \
    --message="First PR - adding test documentation"

# Expected output includes handoff document
```

### Step 7: Handoff to Jarvis

Report completion to Jarvis with:

```markdown
## Handoff: ST-FIRST-001

**Branch:** feature/ST-FIRST-001-first-pr
**Head SHA:** abc123...
**Path:** SAFE
**Validation:** All pre-commit gates passed

**Files Changed:**
- docs/guides/test-document.md (new, +3 lines)

**Ready for merlin PR sweep.**
```

### Step 8: Monitor and Close

```bash
# Check PR status (once PR is created)
python3 scripts/pr_lifecycle/agent_cli.py pr-status --pr=<pr-number>

# Close session when done
python3 scripts/swarm/session.py close \
    --worktree-path=/tmp/worktrees/... \
    --remove-worktree
```

## Capability Requirements

### Minimum Capabilities

| Capability | Minimum Level | How to Verify |
|------------|---------------|---------------|
| Git | 4/10 | Can branch, commit, push |
| Testing | 4/10 | Can write and run pytest |
| CI/CD | 3/10 | Understands CI checks |
| Python | 5/10 | Can write basic Python |
| Documentation | 5/10 | Can write clear docs |

### Recommended Capabilities

| Capability | Recommended | Benefits |
|------------|-------------|----------|
| Git | 7/10 | Can rebase, resolve conflicts |
| Testing | 7/10 | Can write comprehensive tests |
| CI/CD | 6/10 | Can debug CI failures |
| Python | 8/10 | Can write idiomatic code |
| Documentation | 7/10 | Can write excellent docs |

### Self-Assessment

```bash
# Run capability assessment
python3 scripts/pr_lifecycle/agent_onboarding.py \
    --agent-id=<your-id> \
    --validate

# Review your scores and focus areas
```

## Common Pitfalls

### 1. Working on Main Branch

**❌ Wrong:**
```bash
git checkout main
# Make changes directly on main
git commit -m "fix: something"
```

**✓ Correct:**
```bash
git checkout -b feature/ST-XXX-description
# Make changes on feature branch
git commit -m "fix(scope): something (ST-XXX)"
```

### 2. Not Claiming Scope Ownership

**❌ Wrong:**
```bash
# Start editing files without claiming scope
vim src/important.py
```

**✓ Correct:**
```bash
# Claim scope first
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-XXX --scope="src/"
# Then edit
vim src/important.py
```

### 3. Opening PR Directly

**❌ Wrong:**
```bash
git push origin feature/ST-XXX
git pr create  # Don't do this!
```

**✓ Correct:**
```bash
git push origin feature/ST-XXX
# Handoff to Jarvis - they coordinate with merlin
python3 scripts/pr_lifecycle/agent_cli.py submit --story-id=ST-XXX
```

### 4. Skipping Pre-Commit Gates

**❌ Wrong:**
```bash
git add .
git commit -m "done"
git push
# Submit without validation
```

**✓ Correct:**
```bash
# Run validation first
python3 .opencode/command/chise-precommit-gates.md
# Fix any issues
git add .
git commit -m "fix(scope): description (ST-XXX)"
git push
```

### 5. Large PRs

**❌ Wrong:**
```bash
# 500+ line changes in single commit
# Multiple features in one PR
```

**✓ Correct:**
```bash
# Keep changes <100 lines for first PRs
# One feature per PR
# Incremental delivery
```

## Getting Help

### When to Ask for Help

- You're stuck on the same issue for >30 minutes
- You don't understand a requirement
- CI is failing and you can't determine why
- You're unsure which PR path to use
- You encounter an ownership conflict

### How to Ask for Help

1. **Document what you've tried**
2. **Provide specific error messages**
3. **Include relevant context** (story ID, branch, commands run)
4. **Tag Jarvis** in your message

### Example Help Request

```markdown
@jarvis Need help with ST-XXX

**Problem:** CI failing on pytest step
**Error:** `ModuleNotFoundError: No module named 'src.module'`
**Tried:**
- Checked imports look correct
- Ran pytest locally - passes
- Checked sys.path includes src/

**Branch:** feature/ST-XXX-fix
**Files:** src/module.py, tests/test_module.py
```

### Resources

- **AGENTS.md** - Essential reference
- **Git Workflow Skill** - Git procedures
- **Troubleshooting Guide** - Common issues
- **FAQ** - Frequently asked questions
- **Jarvis** - Orchestrator for help

## Next Steps

After completing your first PR:

1. **Review the feedback** you received
2. **Update your understanding** based on lessons learned
3. **Try a STANDARD path** PR for your next story
4. **Document learnings** for future agents
5. **Help onboard** other agents

Remember: The goal is continuous improvement. Each PR is a learning opportunity!

---

**Related Documents:**
- [PR Pipeline Quick Start](pr-pipeline-quickstart.md)
- [PR Pipeline Best Practices](pr-pipeline-best-practices.md)
- [PR Pipeline Troubleshooting](pr-pipeline-troubleshooting.md)
- [PR Pipeline FAQ](pr-pipeline-faq.md)
