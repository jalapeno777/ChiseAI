---
name: "chise-emergency-merge-override"
description: "ChiseAI: emergency procedure for bypassing normal merge authority (human approval required)."
disable-model-invocation: false
---

⚠️ WARNING: This bypasses normal safety controls. Only use in genuine emergencies.

## When To Use
- Critical security fix needed immediately
- Production outage requiring hotfix
- Merlin agent unavailable for >2 hours

## Required Approvals (MUST HAVE)
1. Technical Lead approval (verbal/Slack acknowledged)
2. Document: who approved, when, why
3. Emergency justification written

## Procedure

### 1. Verify Emergency Status
Confirm this is a genuine emergency that cannot wait for normal process.

### 2. Get Explicit Approval
```
EMERGENCY OVERRIDE APPROVED
Approver: [name]
Time: [timestamp]
Reason: [justification]
Story: HOTFIX-[date]-[brief]
```

### 3. Execute Bypass
```bash
# Verify emergency session authority + main merge lock
python3 scripts/swarm/session.py verify \
  --story-id "HOTFIX-[date]" \
  --branch "safety/emergency-[date]-[brief-desc]" \
  --worktree-path "<WORKTREE_PATH>" \
  --check-canonical \
  --require-main-merge-authority \
  --acquire-main-merge-lock

# Switch to main
git switch main
git fetch origin --prune
git pull --ff-only origin main

# Create emergency safety branch
git switch -c safety/emergency-[date]-[brief-desc]

# Apply minimal fix
# ... edits ...

# Validate minimum checks
python3 scripts/validate_status_sync.py
pytest tests/ -k "critical"  # Critical tests only

# Push
git push -u origin safety/emergency-[date]-[brief-desc]

# Force PR creation (exceptional/manual recovery path)
python3 scripts/gitea_pr_automerge.py \
    --story-id="HOTFIX-[date]" \
    --head="safety/emergency-[date]-[brief-desc]" \
    --agent-id="merlin"
```

### 4. Document Incident
Use `.opencode/command/chise-incident-log.md` to log:
- Type: emergency-override
- Approver name
- Justification
- Story reference

### 5. Post-Emergency (within 24h)
- [ ] Full retrospective
- [ ] Update runbooks if gaps found
- [ ] Review why normal process failed
- [ ] Check if merlin availability needs improvement

## DO NOT USE FOR
- Regular feature work
- Non-critical bug fixes
- Convenience/speed only
