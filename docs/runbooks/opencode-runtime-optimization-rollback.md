# OpenCode Runtime Optimization Rollback Guide

## Purpose
Safely roll back the runtime/TPS optimization changes if any quality, guardrail, or workflow regression is detected.

## Trigger Conditions
Rollback immediately if any of the following occur:
- Missing required validation evidence on completed tasks
- Guardrail/compliance drift or merge-authority violations
- Increased hallucination/derailment versus baseline
- Meaningful throughput gains are not observed after canary

## Changes Covered
This rollback guide covers:
- `opencode.jsonc` tuning
- runtime agent profiles (`aria-runtime`, `jarvis-runtime`)
- runtime canary and hygiene commands
- cache-friendly prompt runbook
- autonomous effort routing notes in Aria/Jarvis docs

## Rollback Strategy
Use phased rollback to reduce operational risk.

### Phase 1: Runtime profile rollback (lowest blast radius)
1. Stop using `aria-runtime` and `jarvis-runtime`.
2. Resume full `aria` + `jarvis` only.
3. Keep canonical policies unchanged.

Effect:
- Immediate return to prior orchestration behavior.

### Phase 2: Config rollback
Revert these `opencode.jsonc` adjustments if needed:
- watcher ignore additions:
  - `.backup/**`
  - `.benchmarks/**`
  - `htmlcov/**`
  - `coverage.xml`
- Aria tool restriction:
  - `duckduckgo*`: `false` -> `true`
- MCP disablements:
  - `MiniMax_Web`: `enabled: false` -> `true`
  - `MiniMax_Image`: `enabled: false` -> `true`
- log level:
  - `WARN` -> prior level (if required for debugging)

### Phase 3: Documentation/runtime artifact rollback
If desired, remove runtime-only artifacts:
- `.opencode/agent/AriaRuntime.md`
- `.opencode/agent/JarvisRuntime.md`
- `.opencode/command/chise-runtime-guardrail-canary.md`
- `.opencode/command/chise-opencode-session-hygiene.md`
- `docs/runbooks/opencode-cache-friendly-prompts.md`
- this rollback file

## Fast Technical Rollback (Git)
If these changes are in a single commit, prefer commit-level revert:

```bash
git revert <commit_sha>
```

If only partial rollback is needed, restore specific files:

```bash
git restore --source=<commit_sha>^ -- opencode.jsonc
git restore --source=<commit_sha>^ -- .opencode/agent/Aria.md .opencode/agent/Jarvis.md .opencode/agent/README.md
git restore --source=<commit_sha>^ -- .opencode/agent/AriaRuntime.md .opencode/agent/JarvisRuntime.md
git restore --source=<commit_sha>^ -- .opencode/command/chise-runtime-guardrail-canary.md .opencode/command/chise-opencode-session-hygiene.md
git restore --source=<commit_sha>^ -- docs/runbooks/opencode-cache-friendly-prompts.md docs/runbooks/opencode-runtime-optimization-rollback.md
```

## Verification Checklist After Rollback
- `opencode stats` trend returns to expected baseline behavior
- guardrail artifacts and acceptance evidence are present as expected
- orchestration no longer uses runtime profiles
- no unintended file changes remain staged or modified

Verification commands:

```bash
git status -sb
opencode stats --days 1 --models 20 --tools 20 --project ""
```

## Notes
- `docs/tempmemories/**` is intentionally excluded from hygiene pruning.
- Keep rollback evidence in incident logs/iterlog when rollback is triggered.
