---
name: "chise-branch-hygiene-check"
description: "ChiseAI: analyze branch hygiene, identify stale branches, and recommend cleanup actions."
disable-model-invocation: true
---

Analyze repository branch hygiene and recommend cleanup actions.

## Execution

### Basic Check
```bash
python3 scripts/swarm/branch_hygiene_check.py --report
```

### With Auto-Cleanup (Dry Run)
```bash
python3 scripts/swarm/branch_hygiene_check.py --dry-run --auto-clean
```

### Force Cleanup (DANGER)
```bash
python3 scripts/swarm/branch_hygiene_check.py --auto-clean --force
```

## Output Format

```
Branch Hygiene Report - 2026-02-16
===================================

🔴 CRITICAL (4 branches):
  feature/ST-NS-001-old (behind main 15 commits, 30 days old)
  → Action: Delete (already merged)

🟡 WARNING (3 branches):
  feature/ST-CI-007 (behind main 8 commits)
  → Action: Update or delete
  
✅ HEALTHY (12 branches):
  feature/ST-NS-020-neuro (active, up-to-date)
```

## Redis Updates

This command updates:
- bmad:chiseai:branch_hygiene:warned:*
- bmad:chiseai:branch_hygiene:deleted:*
- bmad:chiseai:branch_hygiene:summary:[date]

## When To Run

- Weekly: During merlin PR sweep
- Before releases: Clean up before major deploy
- On-demand: When repository feels cluttered

## Related
- `.opencode/skills/chiseai-branch-hygiene/SKILL.md`
- `.opencode/command/chise-merlin-pr-sweep.md`
