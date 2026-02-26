# PR Pipeline FAQ

Frequently asked questions about the autonomous PR pipeline.

## General Questions

### Q: What is the PR pipeline?

**A:** The PR pipeline is an autonomous system that enables AI agents to safely contribute code through structured review and merge processes. It provides three paths (SAFE, STANDARD, COMPLEX) based on risk level, with automated validation and appropriate human oversight.

### Q: Who can use the PR pipeline?

**A:** Any AI agent that has completed onboarding can use the PR pipeline. Agents must understand Git workflows, scope ownership, and the three PR paths.

### Q: How do I get started?

**A:** Follow the [Agent Onboarding Guide](agent-onboarding-guide.md):
1. Read AGENTS.md
2. Complete the onboarding checklist
3. Validate your readiness
4. Start with a SAFE path PR

### Q: What are the three PR paths?

**A:**
- **SAFE**: Documentation and simple fixes, automated approval
- **STANDARD**: Features and fixes, requires human approval
- **COMPLEX**: Architecture and security, requires multiple approvals

See [PR Pipeline Quick Start](pr-pipeline-quickstart.md) for details.

## Workflow Questions

### Q: How do I start working on a story?

**A:**
```bash
# 1. Start session
python3 scripts/swarm/session.py start \
    --story-id=ST-XXX \
    --agent=<your-id> \
    --branch=feature/ST-XXX-description \
    --scopes="src/module/"

# 2. Claim scope
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-XXX \
    --scope="src/module/"

# 3. Start working
```

### Q: How do I know which PR path to use?

**A:** Use the path selector:
```bash
python3 scripts/pr_lifecycle/pr_path_selector.py \
    --story-id=ST-XXX \
    --files="src/module/"
```

**Quick guide:**
- Documentation only → SAFE
- New features → STANDARD
- Architecture changes → COMPLEX

### Q: Can I work on multiple stories at once?

**A:** It's not recommended. The system is designed for one active story per agent session. Complete one story before starting another to avoid confusion and scope conflicts.

### Q: What if I need to switch stories temporarily?

**A:**
```bash
# Stash or commit current work
git stash
# or
git commit -m "wip: temporary commit"

# Close current session (keep worktree)
python3 scripts/swarm/session.py close

# Start new session for other story
python3 scripts/swarm/session.py start \
    --story-id=ST-YYY \
    --agent=<your-id> \
    --branch=feature/ST-YYY-description

# Later, return to first story
python3 scripts/swarm/session.py start \
    --story-id=ST-XXX \
    --agent=<your-id> \
    --branch=feature/ST-XXX-description
```

## Scope and Ownership

### Q: What is scope ownership?

**A:** Scope ownership is a mechanism to prevent conflicts when multiple agents work in parallel. Before editing files, you must "claim" ownership of the scope (directory/module) in Redis.

### Q: How do I claim scope ownership?

**A:**
```bash
# Via CLI
python3 scripts/pr_lifecycle/agent_cli.py reserve-scope \
    --story-id=ST-XXX \
    --scope="src/module/"

# Or manually
redis-cli -h host.docker.internal -p 6380 \
    HSET bmad:chiseai:ownership src:module "ST-XXX/agent/2026-02-25T10:00:00Z"
```

### Q: What if the scope is already owned?

**A:** Stop and report to Jarvis. Do not proceed without resolving the conflict. Options include:
- Waiting for the owner to complete
- Requesting re-scope from Jarvis
- Working on a different story

### Q: How granular should scope be?

**A:** Scope at the module/directory level, not individual files:
- ✅ Good: `src/strategy/dsl/`, `docs/guides/`
- ❌ Bad: `src/strategy/dsl/grammar.py`, `src/`

### Q: When should I release scope ownership?

**A:** Release when:
- Your PR is merged
- You're abandoning the story
- You're explicitly handing off to another agent

```bash
redis-cli -h host.docker.internal -p 6380 \
    HDEL bmad:chiseai:ownership src:module
```

## Git and Branching

### Q: What branch naming convention should I use?

**A:**
```
feature/ST-XXX-short-description
fix/ST-XXX-bug-description
safety/hotfix-YYYY-MM-DD
```

### Q: Can I work directly on main?

**A:** No. Never work directly on main. Always create a feature branch:
```bash
git checkout -b feature/ST-XXX-description
```

### Q: How often should I commit?

**A:** Commit frequently with logical units of work:
- After completing a small feature
- Before switching contexts
- After fixing a bug
- At natural breakpoints

### Q: What's the commit message format?

**A:**
```
type(scope): description (ST-XXX)

Body explaining what and why.

Refs: ST-XXX
```

Example: `feat(dsl): add trailing stop syntax (ST-DSL-042)`

### Q: How do I keep my branch up to date?

**A:**
```bash
# Fetch latest
git fetch origin

# Rebase onto main
git rebase origin/main

# Or merge
git merge origin/main
```

Rebase is preferred for feature branches.

## Validation and Testing

### Q: What are pre-commit gates?

**A:** Pre-commit gates are validation checks that must pass before submitting work:
- Code formatting (black)
- Linting (ruff)
- Tests (pytest)
- Security scan (bandit)

### Q: How do I run pre-commit gates?

**A:**
```bash
# Run all gates
python3 .opencode/command/chise-precommit-gates.md

# Or individually
black --check src/ scripts/
ruff check src/ scripts/
pytest tests/ -x --tb=short
```

### Q: What if tests fail?

**A:**
1. Run tests locally to see details: `pytest tests/ -v`
2. Fix the failing tests
3. Re-run pre-commit gates
4. Only submit when all pass

### Q: Do I need to write tests?

**A:** Yes, for code changes:
- Bug fixes: Add regression test
- New features: Add unit and integration tests
- Refactoring: Ensure existing tests pass

Documentation-only changes don't require tests.

## Submission and Handoff

### Q: How do I submit my work?

**A:**
```bash
# 1. Run pre-commit gates
python3 .opencode/command/chise-precommit-gates.md

# 2. Push branch
git push origin feature/ST-XXX-description

# 3. Submit via CLI
python3 scripts/pr_lifecycle/agent_cli.py submit \
    --story-id=ST-XXX \
    --message="Description of changes"

# 4. Report handoff to Jarvis
```

### Q: Should I open the PR myself?

**A:** No. Workers do NOT open PRs. Handoff to Jarvis, who coordinates with merlin to create and manage PRs.

### Q: What should be in my handoff report?

**A:**
```markdown
## Handoff: ST-XXX

**Branch:** feature/ST-XXX-description
**Head SHA:** abc123def456
**Path:** [SAFE|STANDARD|COMPLEX]
**Validation:** All pre-commit gates passed

**Files Changed:**
| File | Type | Lines |
|------|------|-------|
| path | add/mod/del | +N/-M |

**Test Results:**
```
pytest tests/ -v
==== N passed in X.XXs ====
```

**Blockers:** None

Ready for merlin PR sweep.
```

### Q: What happens after I handoff?

**A:**
1. Jarvis reviews your handoff
2. Jarvis coordinates with merlin
3. Merlin creates/updates the PR
4. CI runs automated checks
5. Based on path, either auto-approves or requests human review
6. Once approved, merlin merges to main
7. Branch is cleaned up

## CI and Automation

### Q: What CI checks run on my PR?

**A:** Standard checks include:
- Code formatting (black)
- Linting (ruff)
- Unit tests (pytest)
- Integration tests
- Security scan (bandit)
- Type checking (mypy)

### Q: How do I check CI status?

**A:**
```bash
# Via CLI
python3 scripts/pr_lifecycle/agent_cli.py pr-status --pr=<number>

# Or check Gitea/GitHub web interface
```

### Q: What if CI fails?

**A:**
1. Check the failure logs
2. Fix the issue locally
3. Commit the fix
4. Push to the same branch
5. CI will re-run automatically

### Q: Can I skip CI for documentation changes?

**A:** Use `[ci skip]` or `[skip ci]` in commit message:
```bash
git commit -m "docs: update README [ci skip]"
```

Use sparingly - only for pure documentation.

## Timing and Expectations

### Q: How long does the PR process take?

**A:**
- **SAFE path**: Minutes to hours
- **STANDARD path**: Hours to days
- **COMPLEX path**: Days to weeks

Depends on review availability and complexity.

### Q: What if my PR is stuck?

**A:** After reasonable time:
1. Check CI status
2. Verify no blockers
3. Politely ping reviewers
4. Escalate to Jarvis if needed

### Q: How long should I wait for review?

**A:**
- SAFE path: No wait (automated)
- STANDARD path: 24-48 hours
- COMPLEX path: 3-5 days

After this, it's appropriate to follow up.

## Human Interaction

### Q: When do I interact with humans?

**A:** Minimal direct interaction:
- COMPLEX path PRs may need design discussions
- Review feedback should be addressed
- Escalations go through Jarvis

### Q: How do I respond to review feedback?

**A:**
1. Acknowledge each comment
2. Make requested changes
3. Test changes
4. Commit with fixes
5. Push and notify

### Q: What if I disagree with feedback?

**A:**
1. Consider the perspective
2. Ask clarifying questions
3. Explain your reasoning
4. Find compromise
5. Escalate through Jarvis if needed

## Error Handling

### Q: What if I encounter an error not in the troubleshooting guide?

**A:**
1. Document the error (screenshot/logs)
2. Try to understand the cause
3. Search for similar issues
4. Ask Jarvis for help
5. Once resolved, add to troubleshooting guide

### Q: What if Redis is unavailable?

**A:** Continue without Redis:
- Document in handoff that Redis was down
- Use file-based fallbacks if available
- Report infrastructure issue

### Q: What if I make a mistake?

**A:** Don't panic. Mistakes happen:
1. Stop and assess
2. Document what happened
3. Ask for help if needed
4. Fix if possible
5. Learn and document

## Best Practices

### Q: What's the most important thing to remember?

**A:** **Always claim scope ownership before editing files.** This prevents conflicts and keeps the system safe.

### Q: How can I be a good agent citizen?

**A:**
- Follow the processes
- Document your learnings
- Help other agents
- Keep PRs small and focused
- Respond promptly to feedback
- Maintain high quality

### Q: What should I document?

**A:** Document:
- Lessons learned
- Useful patterns
- Gotchas and workarounds
- Process improvements

Add to skills, guides, or tempmemories.

## Advanced Topics

### Q: Can I work in parallel with other agents?

**A:** Yes, if:
- Scopes are disjoint
- No shared files
- Not touching global-lock areas
- Jarvis has planned the parallel work

### Q: What are global-lock areas?

**A:** Files that require sequential access:
- `.woodpecker.yml` (CI config)
- `pyproject.toml` (project config)
- `AGENTS.md` (agent guidelines)
- `docs/bmm-workflow-status.yaml`

### Q: How do I handle emergencies?

**A:**
1. Use safety branch: `safety/hotfix-YYYY-MM-DD`
2. Make minimal changes
3. Fast-track through COMPLEX path
4. Document thoroughly
5. Follow up with proper fix

See [AGENTS.md](../../AGENTS.md) for emergency procedures.

### Q: Can I suggest improvements to the pipeline?

**A:** Yes! Document your suggestion:
- What problem it solves
- How it would work
- Trade-offs
- Implementation ideas

Share with Jarvis for consideration.

## Resources

### Q: Where can I find more information?

**A:**
- [Agent Onboarding Guide](agent-onboarding-guide.md) - Full onboarding
- [PR Pipeline Quick Start](pr-pipeline-quickstart.md) - Quick reference
- [PR Pipeline Best Practices](pr-pipeline-best-practices.md) - Best practices
- [PR Pipeline Troubleshooting](pr-pipeline-troubleshooting.md) - Problem solving
- [AGENTS.md](../../AGENTS.md) - Essential reference
- `.opencode/skills/` - Skill documentation

### Q: Who do I ask for help?

**A:**
- **Jarvis**: Orchestrator for workflow issues
- **Merlin**: Merge authority for main
- **Captain Craig**: Infrastructure and governance

### Q: How do I report bugs in the pipeline?

**A:**
```markdown
**BUG REPORT: [Brief description]**

**What happened:** [Description]
**What I expected:** [Expected behavior]
**What actually happened:** [Actual behavior]

**Steps to reproduce:**
1. [Step 1]
2. [Step 2]

**Environment:**
- Story: ST-XXX
- Branch: feature/ST-XXX
- Agent: your-id

**Logs:**
```
[Relevant logs]
```
```

---

**Still have questions?** Check the related documents or ask Jarvis.

**Related Documents:**
- [Agent Onboarding Guide](agent-onboarding-guide.md)
- [PR Pipeline Quick Start](pr-pipeline-quickstart.md)
- [PR Pipeline Best Practices](pr-pipeline-best-practices.md)
- [PR Pipeline Troubleshooting](pr-pipeline-troubleshooting.md)
