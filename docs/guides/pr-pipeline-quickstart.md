# PR Pipeline Quick Start

Quick reference guide for agents already familiar with the PR pipeline. For detailed onboarding, see [Agent Onboarding Guide](agent-onboarding-guide.md).

## Quick Commands

### Session Management

```bash
# Start session
python3 scripts/swarm/session.py start \
    --story-id=ST-XXX \
    --agent=<your-id> \
    --branch=feature/ST-XXX-description \
    --scopes="src/module/"

# Verify session
python3 scripts/swarm/session.py verify --story-id=ST-XXX

# Close session
python3 scripts/swarm/session.py close --remove-worktree
```

### Scope Operations

```bash
# Reserve scope
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-XXX \
    --scope="src/module/"

# Check ownership
redis-cli -h host.docker.internal -p 6380 \
    HGET bmad:chiseai:ownership src:module
```

### Validation

```bash
# Pre-commit gates
python3 .opencode/command/chise-precommit-gates.md

# Fast push gate only
python3 scripts/ci/pre_push_gate.py

# Broader local CI when needed
./scripts/local-ci-checks.sh --merged-only
```

### Submission

```bash
# Submit work
python3 scripts/pr_lifecycle/agent_cli.py submit \
    --story-id=ST-XXX \
    --message="Description of changes"

# Check PR status
python3 scripts/pr_lifecycle/agent_cli.py pr-status --pr=<number>

# List my PRs
python3 scripts/pr_lifecycle/agent_cli.py list-prs --state=open
```

## PR Path Selection

| Path | Use For | Approval | Timeline |
|------|---------|----------|----------|
| **SAFE** | Docs, simple fixes | Auto | Minutes |
| **STANDARD** | Features, fixes | Human | Hours/Days |
| **COMPLEX** | Architecture, security | Multiple | Days/Weeks |

### Path Selection Helper

```bash
python3 scripts/pr_lifecycle/pr_path_selector.py \
    --story-id=ST-XXX \
    --files="src/module/"
```

### Quick Path Guidelines

**SAFE Path:**
- Documentation only
- Comments
- Spelling/grammar
- Config values
- <20 lines changed

**STANDARD Path:**
- New features
- Bug fixes
- Refactoring
- Tests
- 20-200 lines changed

**COMPLEX Path:**
- Architecture changes
- Security
- Database migrations
- Core modifications
- >200 lines or high risk

## Git Workflow

### Branch Naming

```
feature/ST-XXX-short-description
fix/ST-XXX-bug-description
safety/hotfix-YYYY-MM-DD
```

### Commit Format

```
type(scope): description (ST-XXX)

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Daily Workflow

```bash
# 1. Check status
git status -sb

# 2. Sync with main
git fetch origin
git rebase origin/main

# 3. Make changes
# ... edit files ...

# 4. Stage and commit
git add -p  # Review changes interactively
git commit -m "type(scope): description (ST-XXX)"

# 5. Validate
python3 .opencode/command/chise-precommit-gates.md

# 6. Push (repo-managed pre-push hook runs automatically)
git push origin feature/ST-XXX-description

# 7. Submit
python3 scripts/pr_lifecycle/agent_cli.py submit --story-id=ST-XXX
```

## Emergency Procedures

### CI Failure

```bash
# 1. Check logs
python3 scripts/pr_lifecycle/agent_cli.py pr-status --pr=<number>

# 2. Fix locally
# ... make fixes ...

# 3. Re-validate
pytest tests/ -x

# 4. Commit fix
git add .
git commit -m "fix: resolve CI failure (ST-XXX)"
git push
```

### Merge Conflict

```bash
# 1. Fetch latest
git fetch origin

# 2. Rebase
git rebase origin/main

# 3. Resolve conflicts
# ... edit files ...
git add .
git rebase --continue

# 4. Force push
git push --force-with-lease
```

### Scope Conflict

```bash
# Check who owns scope
redis-cli -h host.docker.internal -p 6380 \
    HGET bmad:chiseai:ownership src:module

# If conflict, STOP and report to Jarvis
```

### Uncommitted Changes

```bash
# Stash changes
git stash

# Or commit them
git add .
git commit -m "wip: temporary commit"

# Switch branches
git checkout other-branch
```

## Handoff Template

```markdown
## Handoff: ST-XXX

**Branch:** feature/ST-XXX-description
**Head SHA:** abc123def456
**Path:** [SAFE|STANDARD|COMPLEX]
**Validation:** [All passed|Issues noted]

**Files Changed:**
| File | Type | Lines |
|------|------|-------|
| path | add/mod/del | +N/-M |

**Test Results:**
```
pytest tests/ -v
==== N passed in X.XXs ====
```

**Blockers:** [None|List any]

Ready for merlin PR sweep.
```

## Common Issues

### Redis Unavailable

```bash
# Check connectivity
redis-cli -h host.docker.internal -p 6380 PING

# If fails, use file fallback
# Document in handoff
```

### Import Errors

```bash
# Ensure src/ is in path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Or use bootstrap
python3 -c "from config.bootstrap import bootstrap; bootstrap()"
```

### Test Failures

```bash
# Run specific test
pytest tests/test_file.py::test_function -v

# With debugging
pytest tests/test_file.py -v --tb=long -s

# Check coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Path Selection Decision Tree

```
Is it documentation only?
  ├─ Yes → SAFE Path
  └─ No → Does it touch core/architecture?
       ├─ Yes → COMPLEX Path
       └─ No → STANDARD Path
```

## Time Estimates

| Task | Estimate |
|------|----------|
| SAFE path PR | 30 min - 2 hours |
| STANDARD path PR | 2 - 8 hours |
| COMPLEX path PR | 1 - 5 days |
| Rebase/Conflict | 15 - 60 min |
| CI Debug | 15 min - 2 hours |

## Quick Reference Card

```
START:   session.py start --story-id=ST-XXX --agent=YOU --branch=feature/ST-XXX-desc
CLAIM:   agent_cli.py reserve-scope --story-id=ST-XXX --scope="src/"
WORK:    # Edit files
VALID:   chise-precommit-gates.md
COMMIT:  git commit -m "type(scope): desc (ST-XXX)"
SUBMIT:  agent_cli.py submit --story-id=ST-XXX
HANDOFF: Report to Jarvis
CLOSE:   session.py close --remove-worktree
```

## Related Documents

- [Agent Onboarding Guide](agent-onboarding-guide.md) - Full onboarding
- [PR Pipeline Best Practices](pr-pipeline-best-practices.md) - Best practices
- [PR Pipeline Troubleshooting](pr-pipeline-troubleshooting.md) - Problem solving
- [PR Pipeline FAQ](pr-pipeline-faq.md) - Common questions
