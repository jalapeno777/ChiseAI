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
# Switch to main
git checkout main
git pull origin main

# Create hotfix branch
git checkout -b hotfix/emergency-[date]-[brief-desc]

# Apply minimal fix
# ... edits ...

# Validate minimum checks
python3 scripts/validate_status_sync.py
pytest tests/ -k "critical"  # Critical tests only

# Push
git push origin hotfix/emergency-[date]-[brief-desc]

# Force PR creation
python3 scripts/gitea_pr_automerge.py \
    --story-id="HOTFIX-[date]" \
    --branch="hotfix/emergency-[date]-[brief-desc]" \
    --emergency-override=true \
    --approver="[name]"
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
