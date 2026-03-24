---
name: chiseai-ci-failure-workflow
description: Comprehensive CI/Woodpecker/Gitea failure detection, diagnosis, triage, and resolution workflow for ChiseAI agents.
metadata:
  version: "1.0"
  opencode_min_version: "1.1.60"
  author: "ChiseAI Team"
  last_updated: "2026-03-24"
---

# chiseai-ci-failure-workflow

## Goal

Transform CI failures from blockers into structured, solvable problems through systematic detection, diagnosis, triage, and resolution. This skill provides agents with a complete workflow for handling Woodpecker/Gitea CI failures from initial detection through verification and escalation.

## When To Use

- CI pipeline shows failures on a PR
- Woodpecker/Gitea CI blocks merge
- Pipeline is hanging (>10 min with no progress)
- Slow CI affecting delivery cadence
- Prebuilt image issues suspected
- Routine CI health auditing
- Post-incident CI failure analysis

## When Not To Use

- **Pre-commit failures** - Use `chiseai-validation` skill with `chise-precommit-gates` instead
- **Code debugging without CI context** - Use systematic-debugging skill for general debugging
- **Status file sync issues** - Use `chiseai-workflow-status-guard` for status YAML problems
- **Incident response without CI focus** - Use `chiseai-incident-response` for general incidents
- **Docker/container issues not CI-related** - Use `chiseai-docker-governance` for container problems

---

## 1. Detection Layer

### Primary Detection Command

```bash
python3 scripts/ci/woodpecker_triage.py status --format human
```

This returns pipeline overview with status, event type, ref, and PR candidates.

### Detecting Failures for Specific PR

```bash
python3 scripts/ci/woodpecker_triage.py status --pr <N> --format human
```

### Hanging Pipeline Detection

A pipeline is considered **hanging** if:

- No status change for >10 minutes
- Step shows `running` but no log output
- Woodpecker UI shows stale timestamps

Check hanging indicators:

```bash
# Look for pipelines with old timestamps
python3 scripts/ci/woodpecker_triage.py status --limit 20 --format json | jq '.pipelines[] | select(.status=="running")'
```

### Gitea Actions Status (Alternative)

If Woodpecker is unavailable, check via Gitea API or UI for PR status.

---

## 2. Diagnosis Layer

### Systematic Diagnosis Command

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr <N> --write-artifacts --format human
```

This extracts root causes from step logs, categorizes failures, and provides repro commands.

### Output Artifacts

When `--write-artifacts` is used, results are written to `_bmad-output/ci/woodpecker/` including:

- `root_cause_report.md` - Human-readable root cause analysis
- `step_logs/` - Individual step log files
- `repro_commands.sh` - Commands to reproduce failures locally

### Diagnosis Categories

After diagnosis, classify into one of four categories:

| Category           | Description                                        | Indicators                                       |
| ------------------ | -------------------------------------------------- | ------------------------------------------------ |
| **infrastructure** | Docker, network, agent, or service issue           | Connection errors, timeout, resource exhaustion  |
| **code**           | Application code defect                            | Test failures, type errors, import failures      |
| **config**         | Pipeline, environment, or tooling misconfiguration | Missing env vars, invalid syntax, wrong versions |
| **flaky**          | Non-deterministic test or race condition           | Intermittent failures, rarely reproducible       |

---

## 3. Triage Section

### Priority Levels

| Priority | Description         | Examples                                  | Response                   |
| -------- | ------------------- | ----------------------------------------- | -------------------------- |
| **P0**   | Blocks ALL PRs      | Lint tool failure, pre-commit hook broken | Immediate fix required     |
| **P1**   | Blocks specific PRs | Test failure in changed code              | Fix before merge           |
| **P2**   | Degraded experience | Slow pipeline (>20min), non-critical test | Fix in current sprint      |
| **P3**   | Cosmetic            | Formatting issues, minor warnings         | Fix before close of sprint |

### Triage Process

1. Run diagnosis to get root cause
2. Determine category (infrastructure/code/config/flaky)
3. Assign priority (P0-P3)
4. Check if fix pattern exists (see Section 4)
5. If no pattern match, escalate per ladder

### Triage Decision Tree

```
CI Failure Detected
    │
    ▼
Run: woodpecker_triage.py diagnose --pr <N>
    │
    ▼
Is root cause clear? ──No──► Escalate (see Section 6)
    │
   Yes
    │
    ▼
Categorize: infrastructure | code | config | flaky
    │
    ▼
Assign Priority: P0 | P1 | P2 | P3
    │
    ▼
Known fix pattern? ──Yes──► Apply fix (see Section 4)
    │
    No
    │
    ▼
Escalate (see Section 6)
```

---

## 4. Fix Patterns Section

### Pattern 1: ARG_MAX Error (ALREADY FIXED)

**Symptom**: `ARG_MAX` error or argument list too long

**Root Cause**: Shell expansion exceeds OS limits

**Fix**: Use xargs batching in pipeline. Already fixed in `.woodpecker/` pipeline files.

**Verification**: Re-trigger pipeline, confirm no ARG_MAX errors.

---

### Pattern 2: Missing Status File

**Symptom**: Step fails with "file not found" for expected status files

**Root Cause**: Step dependencies not properly declared, or step executed out of order

**Fix**:

1. Check step order in `.woodpecker/*.yaml`
2. Verify dependent steps completed successfully
3. Add explicit `depends_on` if missing

**Verification**: Re-run pipeline with `--from-local-dir` pointing to CI artifacts.

---

### Pattern 3: Flaky Test

**Symptom**: Test fails intermittently, passes on re-run

**Fix**:

1. Isolate: Mark test with `@pytest.mark.flaky` if not already
2. Retry: Re-trigger pipeline (once only for flaky)
3. Investigate: Check for timing issues, async race conditions, or test isolation problems

**Verification**: Run test 3 times locally, all should pass.

---

### Pattern 4: Config Drift

**Symptom**: Works locally, fails in CI

**Root Cause**: Environment differences between local and CI (Python version, dependencies, env vars)

**Fix**:

1. Check `pyproject.toml`, `requirements*.txt` for version mismatches
2. Verify CI uses same Docker image as local
3. Compare env vars: `woodpecker_triage.py diagnose` shows environment

**Verification**: Run `pip freeze > requirements.lock` and ensure CI uses same lock file.

---

### Pattern 5: Prebuilt Image Issues

**Symptom**: Pipeline fails immediately at step start, no application logs

**Root Cause**: Prebuilt image missing dependencies, wrong entrypoint, or image not rebuilt after changes

**Fix**:

1. Check if image tag is `latest` or specific SHA
2. Force image rebuild in Woodpecker if using `latest`
3. Verify Dockerfile changes were committed and pushed

**Verification**: Trigger rebuild with clean cache.

---

### Pattern 6: Secret/Env Var Missing

**Symptom**: Step fails with `KeyError` or `Environment variable not set`

**Fix**:

1. Check Woodpecker repo settings for required secrets
2. Add missing env vars to `.woodpecker/` pipeline file under `environment`
3. Ensure secrets are scoped correctly (not `*` if repo is restricted)

**Verification**: Run `woodpecker_triage.py diagnose` and check environment section.

---

## 5. Verification Section

### Local Replay

If CI artifacts were captured locally:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --from-local-dir _bmad-output/ci/woodpecker --format human
```

### Remote Re-trigger

To verify fix in CI:

1. Push fix to branch
2. If PR exists, push to trigger CI
3. If no PR, trigger manually via Woodpecker UI or API

### Verification Checklist

After applying fix:

- [ ] Run `woodpecker_triage.py status --pr <N>` confirms green
- [ ] All required CI contexts pass
- [ ] No new warnings introduced
- [ ] If pre-commit hook was broken, verify with `git status -sb`

---

## 6. Escalation Section

### Escalation Ladder

| Level  | Agent      | Scope                                          | Max Passes | Trigger                                        |
| ------ | ---------- | ---------------------------------------------- | ---------- | ---------------------------------------------- |
| **L1** | dev        | Standard fixes (lint, formatting, simple test) | 2          | Unknown root cause after diagnosis             |
| **L2** | senior-dev | Complex fixes (infrastructure, multi-step)     | 2          | L1 exhausted or infrastructure issue           |
| **L3** | merlin     | Critical/seismic (main blocked, data risk)     | 3          | L2 exhausted or P0 without resolution          |
| **L4** | Aria       | Requires Craig decision                        | N/A        | All levels exhausted or policy decision needed |

### Escalation Triggers

Escalate when:

1. **Same error_signature repeats 2x** without strategy change
2. **Root cause unclear** after diagnosis
3. **Fix requires changes to shared infrastructure** (`.woodpecker/`, Docker images, terraform)
4. **P0 incident** with >30 min resolution time
5. **All L1/L2 passes exhausted**

### Escalation Evidence Requirements

When escalating, provide:

```yaml
ESCALATION_PACKET:
  story_id: <story_id>
  branch: <branch-name>

  root_cause: |
    <What diagnosis showed>

  error_signature: |
    <tool + error message + file:line or test name>

  attempts_made:
    - attempt_1: <what was tried and outcome>
    - attempt_2: <what was tried and outcome>

  strategy_delta: |
    <What different approach will be tried next>

  escalation_to: <L2|L3|L4>

  blocking_reason: |
    <Why this cannot be resolved at current level>
```

### Escalation to Merlin/Aria

Use Redis to log escalation:

```python
redis_state_rpush(
    name="bmad:chiseai:iterlog:story:<story_id>:escalations",
    value=json.dumps(escalation_packet)
)
```

---

## 7. Health Audit Section

### Pipeline Health Metrics

Track these metrics over time to identify trends:

| Metric            | Healthy | Warning   | Critical |
| ----------------- | ------- | --------- | -------- |
| Pipeline duration | <10 min | 10-20 min | >20 min  |
| Failure rate      | <5%     | 5-15%     | >15%     |
| Hanging pipelines | 0       | 1-2/week  | >2/week  |
| Flaky test rate   | <2%     | 2-5%      | >5%      |

### Health Audit Commands

```bash
# Get pipeline duration trend (requires jq)
python3 scripts/ci/woodpecker_triage.py status --limit 50 --format json | \
  jq '.pipelines[] | {number, status, duration_min: (.updated - .created / 60)}'

# Failure rate over last 50 pipelines
python3 scripts/ci/woodpecker_triage.py status --limit 50 --format json | \
  jq '[.pipelines[] | select(.status == "failure" or .status == "error")] | length'

# Find flaky tests (tests that fail intermittently)
# Check git log for test file changes correlated with CI re-runs
```

### Slow Pipeline Investigation

1. Run diagnose to see which steps took longest:

```bash
python3 scripts/ci/woodpecker_triage.py diagnose --pr <N> --format json | \
  jq '.failed_steps[] | {name, duration}'
```

2. Check for:
   - Large artifact downloads/uploads
   - Sequential steps that could be parallelized
   - Network latency to registries
   - Docker image pull time (use prebuilt images)

### Hanging Pipeline Recovery

If pipeline is hanging:

1. Cancel via Woodpecker UI or API
2. Investigate: Check Woodpecker agent logs
3. If agent issue: Restart agent container
4. Re-trigger pipeline

---

## 8. Incident Logging

For P0/P1 failures, log incident per `chiseai-incident-response` skill:

```python
incident = {
    "story_id": "<story_id>",
    "severity": "P0",  # or P1
    "category": "ci_failure",
    "root_cause": "<from diagnosis>",
    "resolution": "<how it was fixed>",
    "prevention": "<how to prevent recurrence>"
}
redis_state_rpush(
    name=f"bmad:chiseai:iterlog:story:<story_id>:incidents",
    value=json.dumps(incident)
)
```

---

## Exit Conditions

Stop and escalate to Jarvis if:

- **P0 failure after 2 dev passes** - Main branch is blocked, escalate to senior-dev immediately
- **Same error_signature repeats 2x** - Circuit breaker triggered, escalate with evidence
- **Root cause requires infrastructure changes** - Cannot fix without touching `.woodpecker/` or terraform
- **Hanging pipeline >30 min** - Agent logs show Woodpecker infrastructure issue
- **Woodpecker API unavailable** - Cannot diagnose, escalate to L2 for infrastructure assessment
- **All known patterns exhausted** - Fix doesn't match any documented pattern

---

## Troubleshooting/Safety

### Common Issues

| Issue                       | Resolution                                       |
| --------------------------- | ------------------------------------------------ |
| `Missing WOODPECKER_TOKEN`  | Set env var or use `--token` flag                |
| `Non-JSON response`         | Check Woodpecker server is running, try again    |
| `Local artifacts not found` | Ensure `--write-artifacts` was used in diagnosis |
| `Repo ID not found`         | Verify owner/repo name matches Woodpecker config |
| `ARG_MAX still occurs`      | Pipeline wasn't rebuilt, force clean cache       |

### Safety Checks

- [ ] Always capture diagnosis artifacts with `--write-artifacts`
- [ ] Never push fixes without verifying locally first (where applicable)
- [ ] Log P0/P1 incidents to Redis for post-mortem
- [ ] Verify green CI before claiming fix is complete
- [ ] Check that escalation evidence includes error_signature

---

## Related Skills

- **chiseai-validation** - General validation patterns including pre-commit and CI gates
- **chiseai-incident-response** - Incident logging and post-mortem for CI failures
- **chiseai-git-workflow** - Git workflow for branch management and PR handling
- **chiseai-docker-governance** - Docker/container issues not CI-related

---

## Related Commands

- `.opencode/command/chise-ci-pr-status.md` - Get PR pipeline status
- `.opencode/command/chise-ci-root-cause.md` - Extract root cause from failures
- `.opencode/command/chise-ci-failure-bundle.md` - Create failure artifact bundle
- `.opencode/command/chise-precommit-gates.md` - Pre-commit validation including CI checks
