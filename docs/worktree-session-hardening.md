# Worktree Session Hardening (2026-02-28)

## Summary
This change hardens OpenCode/BMAD swarm execution so tests and git actions run in the assigned worktree/branch instead of accidentally running from the repository root (`main` worktree).

## Why This Was Added
The previous workflow relied on advisory instructions. In practice, commands were sometimes run from the wrong current directory, which caused:
- session verification against the wrong path
- tests/lint running on `main` worktree
- false "not done" loops and repeated rework

## What Changed

### 1) Contract Hardening (instructions and commands)
All worker execution now expects an explicit tuple:
- `STORY_ID`
- `AGENT_ID`
- `BRANCH`
- `WORKTREE_PATH`

Updated files:
- `AGENTS.md`
- `.opencode/agent/Aria.md`
- `.opencode/agent/Jarvis.md`
- `.opencode/agent/Dev.md`
- `.opencode/agent/Quickdev.md`
- `.opencode/agent/SeniorDev.md`
- `.opencode/agent/Merlin.md`

### 2) Command Hardening
Command docs now require explicit `--worktree-path` for `session.py verify/close` and route checks through session-bound execution.

Updated files:
- `.opencode/command/chise-swarm-session.md`
- `.opencode/command/chise-precommit-gates.md`
- `.opencode/command/chise-pr-automerge.md`
- `.opencode/command/chise-merge-queue-tick.md`

### 3) Mechanical Enforcement Scripts
Added two scripts under `scripts/swarm/`:

1. `assert_session_context.py`
- Validates:
  - session file exists at `WORKTREE_PATH/.swarm-session.json`
  - session story/branch/worktree matches expected values
  - current cwd is inside `WORKTREE_PATH`
  - current git branch equals expected branch
- exits non-zero on mismatch

2. `run_in_session.sh`
- Runs `assert_session_context.py`
- executes command inside `WORKTREE_PATH`
- intended wrapper for tests/lint/git commands

### 4) Skill Consistency
Updated skill guidance to avoid invalid/implied worktree usage:
- `.opencode/skills/chiseai-git-workflow/SKILL.md`
- `.opencode/skills/chiseai-worker-contracts/SKILL.md`

## Expected Behavior After Hardening
- Worker tasks fail fast when session tuple is wrong.
- Precommit and automerge instructions are explicitly worktree-bound.
- Orchestrator handoffs include enough data for deterministic branch/worktree execution.

## Debugging Guide

### A. Confirm session tuple and current context
```bash
echo "$STORY_ID" "$AGENT_ID" "$BRANCH" "$WORKTREE_PATH"
python3 scripts/swarm/session.py verify --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" --check-canonical
python3 scripts/swarm/assert_session_context.py --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH"
```

### B. If assertion fails with missing session file
Possible causes:
- wrong `WORKTREE_PATH`
- session was never started in that worktree
- session was already closed/removed

Recovery:
```bash
python3 scripts/swarm/session.py start --story-id "$STORY_ID" --agent "$AGENT_ID" --branch "$BRANCH"
# set WORKTREE_PATH from output, then verify again
```

### C. If branch mismatch occurs
```bash
cd "$WORKTREE_PATH"
git branch --show-current
git status -sb
```
Fix by switching to expected branch inside worktree or rebuilding session with correct branch.

### D. If tests still run from root
Run tests only through wrapper:
```bash
bash scripts/swarm/run_in_session.sh --story-id "$STORY_ID" --branch "$BRANCH" --worktree-path "$WORKTREE_PATH" -- pytest
```

## Safe Rollback / Reversal
If this hardening blocks active work unexpectedly, rollback is non-destructive:

1. Stop using wrappers in commands (temporary):
- Revert changes in `.opencode/command/*` listed above.

2. Keep scripts but disable enforcement:
- Remove `assert_session_context.py` invocations from command docs/agent contracts.

3. Full rollback:
```bash
git checkout -- AGENTS.md \
  .opencode/agent/Aria.md .opencode/agent/Jarvis.md .opencode/agent/Dev.md \
  .opencode/agent/Quickdev.md .opencode/agent/SeniorDev.md .opencode/agent/Merlin.md \
  .opencode/command/chise-swarm-session.md .opencode/command/chise-precommit-gates.md \
  .opencode/command/chise-pr-automerge.md .opencode/command/chise-merge-queue-tick.md \
  .opencode/skills/chiseai-git-workflow/SKILL.md .opencode/skills/chiseai-worker-contracts/SKILL.md
git rm scripts/swarm/assert_session_context.py scripts/swarm/run_in_session.sh
git checkout -- docs/worktree-session-hardening.md
```

Note: use rollback selectively; preferred path is to fix tuple propagation in orchestration prompts.

## Operational Recommendation
Treat `run_in_session.sh` as the default executor wrapper in worker contracts and command templates. Keep direct command usage for debug only.
