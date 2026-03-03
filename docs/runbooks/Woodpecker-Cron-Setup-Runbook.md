# Woodpecker Cron Setup Runbook

**Story:** ST-KPI-RUNBOOK-001
**Purpose:** Setup guide for Woodpecker cron jobs for KPI evaluation cycles
**Last Updated:** 2026-03-02 (updated with programmatic setup method)

> **Note:** As of 2026-03-02, all cron jobs have been successfully configured via the Woodpecker API. See `docs/evidence/Cron-Setup-Attempt-20260302.md` for evidence.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step-by-Step Instructions](#step-by-step-instructions)
3. [Verification Steps](#verification-steps)
4. [Testing](#testing)
5. [Troubleshooting](#troubleshooting)
6. [Appendices](#appendices)

---

## Prerequisites

### Required Access

- **Woodpecker Server URL:**
  - From host machine: `http://localhost:8012`
  - From container: `http://host.docker.internal:8012`

- **Repository:** `craig/ChiseAI`

- **Admin Access to Woodpecker UI**

### Required Files

Pipeline file must exist at: `.woodpecker/cron-eval.yaml`

### Understanding Cron Expressions

Woodpecker uses standard cron syntax with 5 fields:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday=0 or 7, Monday=1)
│ │ │ │ │
* * * * *
```

### Cron Job Reference

| Job Name | Cron Expression | Description |
|----------|----------------|-------------|
| `6h-mini-eval` | `0 */6 * * *` | Every 6 hours at minute 0 (00:00, 06:00, 12:00, 18:00 UTC) |
| `daily-trends` | `15 0 * * *` | Daily at 00:15 UTC |
| `weekly-reflection` | `0 1 * * 1` | Weekly on Monday at 01:00 UTC |

---

## Setup Methods

There are two ways to set up Woodpecker cron jobs:

1. **Programmatic Setup (Recommended)** - Using the Woodpecker API
2. **Manual UI Setup** - Using the Woodpecker web interface

---

## Method 1: Programmatic Setup (Recommended)

This method uses the Woodpecker REST API to create cron jobs automatically.

### Prerequisites

- `WOODPECKER_TOKEN` environment variable set with a valid API token
- `curl` or similar HTTP client available
- Repository already registered in Woodpecker

### Quick Setup Script

```bash
#!/bin/bash
# Woodpecker Cron Setup Script
# Requires: WOODPECKER_TOKEN environment variable

WOODPECKER_URL="http://host.docker.internal:8012"
REPO_ID=1  # craig/ChiseAI

# Create 6h-mini-eval cron
curl -s -X POST \
  -H "Authorization: Bearer ${WOODPECKER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"6h-mini-eval","schedule":"0 */6 * * *","branch":"main","commit_message":"cron:6h-eval"}' \
  "${WOODPECKER_URL}/api/repos/${REPO_ID}/cron"

# Create daily-trends cron
curl -s -X POST \
  -H "Authorization: Bearer ${WOODPECKER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"daily-trends","schedule":"15 0 * * *","branch":"main","commit_message":"cron:daily-trends"}' \
  "${WOODPECKER_URL}/api/repos/${REPO_ID}/cron"

# Create weekly-reflection cron
curl -s -X POST \
  -H "Authorization: Bearer ${WOODPECKER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"weekly-reflection","schedule":"0 1 * * 1","branch":"main","commit_message":"cron:weekly-reflection"}' \
  "${WOODPECKER_URL}/api/repos/${REPO_ID}/cron"

echo "Cron jobs created successfully!"
```

### Verification

```bash
# List all cron jobs
curl -s -H "Authorization: Bearer ${WOODPECKER_TOKEN}" \
  "${WOODPECKER_URL}/api/repos/${REPO_ID}/cron" | python3 -m json.tool
```

---

## Method 2: Manual UI Setup

Use this method if you prefer to use the Woodpecker web interface.

### Step 1: Access Woodpecker UI

1. Open a web browser
2. Navigate to: `http://localhost:8012`
3. Log in using your Gitea credentials
4. Select repository: `craig/ChiseAI`

### Step 2: Navigate to Cron Jobs

**Option A: From Repository Page**

1. Click on the repository `craig/ChiseAI`
2. Go to **Settings** tab
3. Select **Cron Jobs** from the left sidebar

**Option B: Direct URL**

Navigate to: `http://localhost:8012/repos/craig/ChiseAI/settings/cron`

### Step 3: Create 6h Mini Eval Cron

1. Click **+ New Cron** button
2. Fill in the form:

   - **Name:** `6h-mini-eval`
   - **Schedule:** `0 */6 * * *`
   - **Branch:** `main`
   - **Commit Message:** `cron:6h-eval`
   - **Enabled:** ☑️ (checked)

3. Click **Save**

**Verification:** The cron job should appear in the list with next run time calculated.

### Step 4: Create Daily Trends Cron

1. Click **+ New Cron** button
2. Fill in the form:

   - **Name:** `daily-trends`
   - **Schedule:** `15 0 * * *`
   - **Branch:** `main`
   - **Commit Message:** `cron:daily-trends`
   - **Enabled:** ☑️ (checked)

3. Click **Save**

**Verification:** The cron job should appear in the list with next run time calculated.

### Step 5: Create Weekly Reflection Cron

1. Click **+ New Cron** button
2. Fill in the form:

   - **Name:** `weekly-reflection`
   - **Schedule:** `0 1 * * 1`
   - **Branch:** `main`
   - **Commit Message:** `cron:weekly-reflection`
   - **Enabled:** ☑️ (checked)

3. Click **Save**

**Verification:** The cron job should appear in the list with next run time calculated.

### Step 6: Verify All Cron Jobs

After creating all three cron jobs, verify the cron job list shows:

| Name | Schedule | Branch | Commit Message | Next Run |
|------|----------|--------|----------------|----------|
| `6h-mini-eval` | `0 */6 * * *` | `main` | `cron:6h-eval` | [calculated time] |
| `daily-trends` | `15 0 * * *` | `main` | `cron:daily-trends` | [calculated time] |
| `weekly-reflection` | `0 1 * * 1` | `main` | `cron:weekly-reflection` | [calculated time] |

---

## Verification Steps

### 1. Check Cron Job List

- **Action:** Navigate to Cron Jobs page
- **Expected:** All 3 cron jobs visible and enabled

### 2. Verify Next Run Times

- **Action:** Review next run times for each job
- **Expected:**
  - `6h-mini-eval`: Next run within 6 hours of current time (at :00 minute)
  - `daily-trends`: Next run at next 00:15 UTC
  - `weekly-reflection`: Next run on next Monday at 01:00 UTC

### 3. Verify Pipeline File Detection

- **Action:** Click on any cron job to view details
- **Expected:** Pipeline file `.woodpecker/cron-eval.yaml` is detected

### 4. Check Branch Filters

- **Action:** Verify each cron job is configured for `main` branch
- **Expected:** All jobs targeting `main` branch

### 5. Verify Commit Messages

- **Action:** Check commit message for each job
- **Expected:**
  - `6h-mini-eval` → `cron:6h-eval`
  - `daily-trends` → `cron:daily-trends`
  - `weekly-reflection` → `cron:weekly-reflection`

---

## Testing

### Manual Trigger for Testing

**Purpose:** Test a cron job without waiting for scheduled time

**Steps:**

1. Navigate to the cron job list in Woodpecker UI
2. Locate the cron job to test (e.g., `6h-mini-eval`)
3. Click the **Run** button (▶️) next to the cron job
4. Monitor the pipeline execution

**Expected Behavior:**
- Pipeline starts immediately
- Job status updates from "Pending" → "Running" → "Success/Failure"
- Artifacts are produced in `_bmad-output/brain-eval/`

### Expected Artifacts

After a successful cron job run, the following artifacts should be produced:

| Artifact Path | Description |
|---------------|-------------|
| `_bmad-output/brain-eval/kpi-6h-*.json` | 6h mini eval KPI results |
| `_bmad-output/brain-eval/kpi-daily-*.json` | Daily trends KPI results |
| `_bmad-output/brain-eval/kpi-weekly-*.json` | Weekly reflection KPI results |
| `_bmad-output/ci/kpi-scheduler-*.log` | Pipeline execution logs |
| `_bmad-output/ci/kpi-scheduler-*.status` | Step exit codes |

### Checking Logs

**Option A: Woodpecker UI**

1. Navigate to the pipeline execution page
2. Click on the step (e.g., `kpi-scheduler-6h`)
3. View step logs in the right panel

**Option B: Docker Container Logs**

```bash
# Check Woodpecker agent logs
docker logs woodpecker-agent -f

# Check Woodpecker server logs
docker logs woodpecker-server -f
```

### Verification After Test Run

1. **Check Pipeline Status:** All steps should show green (success)
2. **Check Artifacts:** Navigate to the pipeline artifacts section
3. **Verify Redis Data:**

```bash
# Connect to Redis
docker exec -it chiseai-redis redis-cli

# Check for KPI data
KEYS bmad:chiseai:kpi:*
```

---

## Troubleshooting

### Cron Job Not Appearing

**Symptoms:** Cron job created but not visible in list

**Causes & Solutions:**

1. **YAML Syntax Error**
   - Check `.woodpecker/cron-eval.yaml` for syntax errors
   - Validate YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('.woodpecker/cron-eval.yaml'))"`

2. **Woodpecker Server Not Running**
   ```bash
   # Check Woodpecker server status
   docker ps | grep woodpecker

   # Check server logs
   docker logs woodpecker-server
   ```

3. **Gitea Webhook Not Configured**
   - Verify Gitea webhook points to Woodpecker server
   - Check webhook payload delivery in Woodpecker logs

### Pipeline Not Triggering

**Symptoms:** Cron job scheduled but pipeline doesn't run

**Causes & Solutions:**

1. **Branch Filter Issue**
   - Verify target branch (`main`) exists
   - Check branch spelling matches exactly (case-sensitive)

2. **Cron Expression Invalid**
   - Validate cron expression using [crontab.guru](https://crontab.guru/)
   - Check for extra spaces or invalid characters

3. **Pipeline File Not Found**
   - Verify `.woodpecker/cron-eval.yaml` exists in repository
   - Check file path and spelling

4. **Woodpecker Agent Not Running**
   ```bash
   # Check agent status
   docker ps | grep woodpecker-agent

   # Restart agent if needed
   docker restart woodpecker-agent
   ```

### Pipeline Fails

**Symptoms:** Pipeline runs but fails at some step

**Common Issues:**

1. **Python Script Error**
   - Check step logs in Woodpecker UI
   - Verify `scripts/evaluation/kpi_scheduler.py` exists
   - Check script syntax: `python3 -m py_compile scripts/evaluation/kpi_scheduler.py`

2. **Redis Connectivity Issue**
   ```bash
   # From Woodpecker container, test Redis connection
   docker exec woodpecker-agent python3 -c "import redis; r=redis.Redis(host='chiseai-redis', port=6380); print(r.ping())"
   ```

3. **Missing Dependencies**
   - Check if `pyyaml`, `requests`, `numpy`, `scipy` install successfully
   - Verify network connectivity to PyPI

### No Artifacts Produced

**Symptoms:** Pipeline succeeds but no output files

**Solutions:**

1. **Check Output Directory:**
   - Verify `_bmad-output/` directory is created
   - Check permissions: `ls -la _bmad-output/`

2. **Check Redis Data Storage:**
   - Verify Redis is running: `docker ps | grep redis`
   - Check Redis logs: `docker logs chiseai-redis`

3. **Review Script Logic:**
   - Check `scripts/evaluation/kpi_scheduler.py` for error handling
   - Verify data processing logic produces expected output

### Commit Message Not Recognized

**Symptoms:** Pipeline runs but wrong cycle executes (e.g., all cycles run)

**Solution:**

1. **Verify Commit Message Exact Match:**
   - Check commit message in cron job configuration
   - Must match exactly (case-sensitive):
     - `cron:6h-eval`
     - `cron:daily-trends`
     - `cron:weekly-reflection`

2. **Check Pipeline Logic:**
   - Review `.woodpecker/cron-eval.yaml` step conditions
   - Verify `CI_COMMIT_MESSAGE` environment variable is used correctly

### All Cron Jobs Triggering Simultaneously

**Symptoms:** All 3 cron jobs trigger on the same schedule

**Solution:**

1. **Check Cron Expressions:**
   - Verify each job has a unique cron expression
   - Ensure no overlap in schedules

2. **Check Branch Filter:**
   - Ensure all jobs target the same branch (`main`)
   - Verify branch name spelling

3. **Review Pipeline Logic:**
   - Check `.woodpecker/cron-eval.yaml` step conditions
   - Verify commit message filtering logic

---

## Appendices

### Appendix A: Cron Expression Examples

| Expression | Description |
|------------|-------------|
| `0 */6 * * *` | Every 6 hours (00:00, 06:00, 12:00, 18:00) |
| `15 0 * * *` | Daily at 00:15 UTC |
| `0 1 * * 1` | Weekly on Monday at 01:00 UTC |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 * * 0` | Weekly on Sunday at 00:00 UTC |
| `0 9 * * 1-5` | Weekdays at 09:00 UTC |

### Appendix B: Pipeline File Structure

The `.woodpecker/cron-eval.yaml` pipeline expects:

- **Trigger:** `CI_COMMIT_MESSAGE` environment variable
- **Branch:** `main`
- **Event:** `cron`

Pipeline steps:
- `kpi-scheduler-6h`: Runs 6-hour mini eval
- `kpi-scheduler-daily`: Runs daily trends
- `kpi-scheduler-weekly`: Runs weekly reflection
- `ci-gate`: Final gate that fails if any step failed

### Appendix C: Redis Connectivity Requirements

Woodpecker containers need access to:

- **Redis Server:** `chiseai-redis` (on `chiseai` network)
- **Port:** `6380`
- **Network:** `chiseai` (Docker network)

**Connection String:** `redis://chiseai-redis:6380`

### Appendix D: Woodpecker Docker Compose Configuration

```yaml
version: '3.8'

services:
  woodpecker-server:
    image: woodpeckerci/woodpecker-server:latest
    ports:
      - "8012:8000"
    environment:
      - WOODPECKER_GITEA=true
      - WOODPECKER_GITEA_URL=http://gitea:3000
      - WOODPECKER_AGENT_SECRET=your-secret-key
    networks:
      - chiseai
    volumes:
      - woodpecker-server-data:/var/lib/woodpecker

  woodpecker-agent:
    image: woodpeckerci/woodpecker-agent:latest
    command: agent
    environment:
      - WOODPECKER_SERVER=woodpecker-server:9000
      - WOODPECKER_AGENT_SECRET=your-secret-key
    networks:
      - chiseai
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - woodpecker-server

networks:
  chiseai:
    external: true

volumes:
  woodpecker-server-data:
```

### Appendix E: Useful Commands

```bash
# List all Woodpecker containers
docker ps | grep woodpecker

# Check Woodpecker server logs
docker logs woodpecker-server -f

# Check Woodpecker agent logs
docker logs woodpecker-agent -f

# Restart Woodpecker services
docker restart woodpecker-server woodpecker-agent

# Verify Woodpecker network connectivity
docker network inspect chiseai | grep woodpecker

# Check Redis connectivity from Woodpecker agent
docker exec woodpecker-agent ping chiseai-redis

# View cron job configuration via API
curl http://localhost:8012/api/repos/craig/ChiseAI/crons \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Appendix F: Contact & Support

**For Issues:**
- Check Woodpecker logs first
- Review this runbook's troubleshooting section
- Verify all prerequisites are met

**Related Documentation:**
- Woodpecker Documentation: https://woodpecker-ci.org/docs/
- Cron Expression Help: https://crontab.guru/
- ChiseAI AGENTS.md: `/home/tacopants/projects/ChiseAI/AGENTS.md`

**Related Stories:**
- ST-KPI-005: Scheduler Integration (original cron pipeline story)
- ST-KPI-RUNBOOK-001: This runbook creation story

---

**End of Runbook**
