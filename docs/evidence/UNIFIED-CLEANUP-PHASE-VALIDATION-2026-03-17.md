# Unified Cleanup Validation Evidence - 2026-03-17

## Scope

Validation evidence for implementation of the Unified Cleanup Plan across:
- `AGENTS.md`
- `.opencode/agent/*.md`
- CI/local/pre-commit policy enforcement wiring
- lessons loop artifacts

## Automated Validation Commands

```bash
python3 scripts/validate_swarm_policy_consistency.py
python3 scripts/validate_swarm_policy_consistency.py --strict
```

Result:
- `SWARM POLICY CONSISTENCY: PASS`
- `SWARM POLICY CONSISTENCY: PASS`

## Required Policy Signal Checks

Verified by grep:
- canonical escalation ladder (`2/2/2/3`) present in AGENTS + Jarvis + JarvisRuntime + README
- `PLAN_APPROVED=true` gates present in Aria/AriaRuntime/Jarvis/JarvisRuntime
- `LESSON_CANDIDATE` path present in worker/Jarvis/Aria flow
- soft-deprecation markers present for `quickdev-fast` and `juniordev`
- two-remediation cap present in Aria/Jarvis

## Scenario Validation (Policy-Level Dry Runs)

The following scenarios were validated at policy/contract level via rule checks:
- Scenario A: 1SP happy path -> quickdev route
- Scenario B: quickdev fails twice -> escalate to dev
- Scenario C: dev fails twice -> escalate to senior-dev
- Scenario D: senior-dev fails twice -> escalate to merlin
- Scenario E: merlin fails three times -> blocker return to Aria
- Scenario F: critic fail -> remediation round 1 -> re-review
- Scenario G: fail after round 2 -> blocker return to Aria

These are represented in the enforced textual contracts and validated by `scripts/validate_swarm_policy_consistency.py`.
