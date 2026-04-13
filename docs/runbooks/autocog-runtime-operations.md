# Autocog Runtime Operations Runbook

> **Scope**: This runbook covers operational procedures for the autonomous cognition (autocog) system as of 2026-04-13.
>
> **Last Updated**: 2026-04-13

---

## 1. Overview

The **autonomous cognition (autocog) system** is ChiseAI's self-assessment and improvement loop. It continuously evaluates the agent brain's decision quality, belief consistency, and alignment with operating constraints.

### Components

| Component             | Purpose                                                        | Location                                                               |
| --------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **Self-Assessment**   | Periodic evaluation of agent decisions and patterns            | `scripts/ops/run_autonomous_self_assessment.py`                        |
| **Full Cycle Engine** | Comprehensive belief consistency, improvement, and calibration | `scripts/ops/run_autonomous_full_cycle.py`                             |
| **Brain Scheduler**   | Container orchestrating scheduled cognition cycles             | `brain-scheduler` container (Docker)                                   |
| **Output Artifacts**  | JSON evaluation reports stored for review                      | `docs/governance/self_assessments/` and `_bmad-output/autocog/cycles/` |
| **Heartbeat Keys**    | Redis-based liveness indicators for running cycles             | `bmad:chiseai:autocog:heartbeat:*`                                     |

---

## 2. Current System State (2026-04-13)

### 2.1 Self-Assessment Artifacts

- **Location**: `docs/governance/self_assessments/`
- **Latest artifact**: `self_assessment_2026-04-12_*` (dated 2026-04-12)
- Self-assessments are running independently via the controller.

### 2.2 Full Cycle Artifacts

- **Location**: `_bmad-output/autocog/cycles/`
- **Status**: **No artifacts found** — full cycle mode has not produced output yet.

### 2.3 Brain-Scheduler Container

```
Container Name: brain-scheduler
Status: Running (healthy)
Uptime: ~2 weeks
```

Verify with:

```bash
docker ps | grep brain-scheduler
```

### 2.4 Woodpecker Cron Jobs

| Cron Name | Schedule | Status |
| --------- | -------- | ------ |

- **Status**: **NOT CONFIGURED** — No autocog Woodpecker cron jobs exist.
- Only `workflow-archive-*` crons are currently configured.
- See [Section 8](#8-woodpecker-cron-setup-instructions) for setup instructions.

---

## 3. Architecture

The autocog system supports two execution paths:

### 3.1 Woodpecker Cron Pipeline (NOT YET CONFIGURED)

```
┌─────────────────────────────────────────────────────────────┐
│                  Woodpecker CI/CD                           │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │  autocog-cron   │───▶│  .woodpecker/autocog-scheduler │ │
│  │  (scheduled)     │    │  .yaml                          │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

- **File**: `.woodpecker/autocog-scheduler.yaml`
- **Purpose**: Trigger full autocog cycles on a schedule
- **Status**: NOT YET CONFIGURED — cron job needs to be created in Woodpecker

### 3.2 Self-Assessment (Active)

```
┌─────────────────────────────────────────────────────────────┐
│              Self-Assessment (Controller-Driven)             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  run_autonomous_self_assessment.py                   │   │
│  │  --notify-discord                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                               │
│                            ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  docs/governance/self_assessments/                  │   │
│  │  self_assessment_YYYY-MM-DD_*.json                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

- **File**: `scripts/ops/run_autonomous_self_assessment.py`
- **Purpose**: Periodic self-evaluation independent of Woodpecker scheduling
- **Status**: **ACTIVE** — running via brain-scheduler controller

---

## 4. How to Run Manual Autocog Cycles

### 4.1 Self-Assessment

Run a self-assessment evaluation with optional Discord notification:

```bash
python3 scripts/ops/run_autonomous_self_assessment.py --notify-discord
```

**Flags**:
| Flag | Description |
|------|-------------|
| `--notify-discord` | Send completion notification to Discord |

**Output**: `docs/governance/self_assessments/self_assessment_YYYY-MM-DD_*.json`

### 4.2 Full Cycle (Multiple Modes)

Run a comprehensive autocog cycle with a specific mode:

```bash
python3 scripts/ops/run_autonomous_full_cycle.py --mode <MODE> --notify-discord
```

**Available Modes**:

| Mode                 | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `full`               | Complete all cycle components                    |
| `belief_consistency` | Evaluate belief alignment across agent decisions |
| `improvement_cycle`  | Identify and address capability gaps             |
| `calibration`        | Assess prediction/outcome alignment              |
| `autonomy_tune`      | Fine-tune autonomy parameters                    |
| `constitution_audit` | Audit alignment with operating constraints       |

**Flags**:
| Flag | Description |
|------|-------------|
| `--mode <MODE>` | Required. Select cycle mode from table above |
| `--notify-discord` | Send completion notification to Discord |

**Output**: `_bmad-output/autocog/cycles/YYYY-MM-DD_*.json`

---

## 5. How to Check if Scheduled Cycles are Running

### 5.1 Check Woodpecker Cron List

List all Woodpecker cron jobs and filter for autocog crons:

```bash
# Via Gitea API
curl -s -H "Authorization: token $GITEA_TOKEN" \
  "$GITEA_API_URL/api/v1/repos/craig/ChiseAI/actions/cron" | \
  jq '.[] | select(.name | contains("autocog"))'
```

Or check via Woodpecker UI directly at `https://gitea.chiseai.com`

### 5.2 Check Self-Assessment Artifacts

Verify recent self-assessments have been generated:

```bash
# List self-assessment artifacts sorted by date
ls -la docs/governance/self_assessments/ | sort -k9

# Check for today's artifact
ls docs/governance/self_assessments/ | grep "$(date +%Y-%m-%d)"
```

### 5.3 Check Redis Heartbeat Keys

Monitor liveness of running autocog cycles:

```bash
# List all autocog heartbeat keys
redis-cli KEYS "bmad:chiseai:autocog:heartbeat:*"

# Get heartbeat TTL (time remaining)
redis-cli TTL "bmad:chiseai:autocog:heartbeat:<cycle_id>"

# Get heartbeat details
redis-cli HGETALL "bmad:chiseai:autocog:heartbeat:<cycle_id>"
```

**Expected heartbeat fields**:
| Field | Description |
|-------|-------------|
| `last_ping` | Unix timestamp of last heartbeat |
| `current_phase` | Current execution phase |
| `mode` | Cycle mode (if applicable) |

---

## 6. How to Read Autocog Artifacts

### 6.1 Self-Assessment Artifacts

**Location**: `docs/governance/self_assessments/self_assessment_YYYY-MM-DD_*.json`

**Structure**:

```json
{
  "assessment_date": "2026-04-12",
  "components": {
    "decision_quality": { ... },
    "belief_consistency": { ... },
    "constraint_alignment": { ... }
  },
  "findings": [
    {
      "severity": "high|medium|low",
      "category": "string",
      "description": "string",
      "recommendation": "string"
    }
  ],
  "overall_score": 0.85
}
```

### 6.2 Full Cycle Artifacts

**Location**: `_bmad-output/autocog/cycles/YYYY-MM-DD_*.json`

**Structure**:

```json
{
  "cycle_date": "2026-04-13",
  "mode": "full|belief_consistency|improvement_cycle|calibration|autonomy_tune|constitution_audit",
  "phases": {
    "evaluation": { ... },
    "analysis": { ... },
    "recommendations": { ... }
  },
  "severity_summary": {
    "high": 0,
    "medium": 0,
    "low": 0
  }
}
```

---

## 7. How Aria Should Process Autocog Findings

Aria follows a three-stage process for handling autocog outputs:

### 7.1 Daily Run

Run the daily autocog evaluation and artifact collection:

**Command File**: `.opencode/command/chise-autocog-daily-run.md`

```bash
# Execute daily run
python3 scripts/ops/run_autonomous_self_assessment.py --notify-discord

# Collect and catalog new artifacts
ls -la docs/governance/self_assessments/ | tail -5
```

### 7.2 Review

Review findings and classify by severity:

**Command File**: `.opencode/command/chise-autocog-review.md`

| Severity   | Action Required                         |
| ---------- | --------------------------------------- |
| **High**   | Immediate escalation to Aria for review |
| **Medium** | Add to backlog for next sprint          |
| **Low**    | Document and monitor                    |

### 7.3 Action

Route findings to appropriate resolution path:

**Command File**: `.opencode/command/chise-autocog-action.md`

| Finding Type            | Routing                            |
| ----------------------- | ---------------------------------- |
| Belief inconsistency    | `senior-dev` for analysis          |
| Calibration drift       | `chise-metacog-tune` workflow      |
| Constraint violation    | Immediate `BLOCKER_PACKET` to Aria |
| Improvement opportunity | `chise-iterloop-add-story`         |

---

## 8. Woodpecker Cron Setup Instructions

### 8.1 Required Cron Jobs

| Cron Name             | Schedule    | Description                                 |
| --------------------- | ----------- | ------------------------------------------- |
| `autocog-daily`       | `0 3 * * *` | Daily self-assessment at 03:00 UTC          |
| `autocog-weekly`      | `0 4 * * 0` | Weekly full cycle on Sunday at 04:00 UTC    |
| `autocog-calibration` | `0 2 * * 3` | Calibration check on Wednesday at 02:00 UTC |

### 8.2 API Method Using curl

```bash
# Create autocog-daily cron
curl -X POST \
  -H "Authorization: Bearer $WOODPECKER_TOKEN" \
  -H "Content-Type: application/json" \
  https://woodpecker.chiseai.com/api/crons \
  -d '{
    "name": "autocog-daily",
    "repo": "craig/ChiseAI",
    "branch": "main",
    "schedule": "0 3 * * *",
    "workflow": "autocog-scheduler"
  }'
```

### 8.3 Manual UI Method

1. Navigate to Woodpecker: `https://woodpecker.chiseai.com`
2. Go to **Repository Settings** → **Crons**
3. Click **Add Cron**
4. Fill in:
   - **Name**: `autocog-daily`
   - **Branch**: `main`
   - **Cron Schedule**: `0 3 * * *`
   - **Workflow**: `autocog-scheduler`
5. Click **Save**
6. Repeat for `autocog-weekly` and `autocog-calibration`

---

## 9. Troubleshooting Common Issues

### 9.1 Self-Assessment Not Running

**Symptoms**: No new artifacts in `docs/governance/self_assessments/`

**Diagnosis**:

```bash
# Check for import errors in controller
python3 -c "from scripts.ops.run_autonomous_self_assessment import *"

# Check brain-scheduler container logs
docker logs brain-scheduler --tail=50

# Check Redis connectivity
redis-cli PING
```

**Resolution**:

1. Verify `scripts/ops/run_autonomous_self_assessment.py` has no syntax errors
2. Restart brain-scheduler: `docker restart brain-scheduler`
3. Check disk space for `docs/governance/self_assessments/`

### 9.2 No Cycles Artifacts

**Symptoms**: `_bmad-output/autocog/cycles/` is empty despite running full cycles

**Diagnosis**:

```bash
# Check directory permissions
ls -la _bmad-output/autocog/cycles/

# Test Redis connectivity for artifact storage
redis-cli SET test_key "test" && redis-cli GET test_key

# Verify output directory exists
mkdir -p _bmad-output/autocog/cycles/
```

**Resolution**:

1. Create output directory if missing:
   ```bash
   mkdir -p _bmad-output/autocog/cycles/
   chmod 755 _bmad-output/autocog/cycles/
   ```
2. Verify Redis is accessible from brain-scheduler container
3. Check for disk space issues

### 9.3 Cron Not Triggering

**Symptoms**: Woodpecker shows cron created but pipeline never runs

**Diagnosis**:

```bash
# Verify cron exists with exact name
curl -s -H "Authorization: Bearer $WOODPECKER_TOKEN" \
  https://woodpecker.chiseai.com/api/crons/craig/ChiseAI | \
  jq '.[] | select(.name == "autocog-daily")'
```

**Resolution**:

1. **Verify cron name matches exactly** — Woodpecker cron names are case-sensitive
2. Ensure the workflow `.woodpecker/autocog-scheduler.yaml` exists on the target branch
3. Check that the repository is active (Woodpecker pauses crons on inactive repos)
4. Manually trigger once to verify: Click **Run Now** in Woodpecker UI

### 9.4 Discord Notification Not Sent

**Symptoms**: Cycle completes but no Discord notification

**Diagnosis**:

```bash
# Check Discord webhook configuration
env | grep DISCORD

# Test webhook manually
curl -X POST -H "Content-Type: application/json" \
  -d '{"content": "test"}' \
  $DISCORD_WEBHOOK_URL
```

**Resolution**:

1. Verify `DISCORD_WEBHOOK_URL` environment variable is set
2. Check webhook URL is valid and not revoked
3. Ensure brain-scheduler container has access to the environment variable

---

## Quick Reference

| Task                  | Command                                                                         |
| --------------------- | ------------------------------------------------------------------------------- |
| Run self-assessment   | `python3 scripts/ops/run_autonomous_self_assessment.py --notify-discord`        |
| Run full cycle        | `python3 scripts/ops/run_autonomous_full_cycle.py --mode full --notify-discord` |
| Check heartbeat       | `redis-cli KEYS "bmad:chiseai:autocog:heartbeat:*"`                             |
| List self-assessments | `ls -la docs/governance/self_assessments/ \| sort -k9 \| tail -5`               |
| Check container       | `docker ps \| grep brain-scheduler`                                             |

---

_For questions or issues not covered here, escalate to Aria via `BLOCKER_PACKET`._
