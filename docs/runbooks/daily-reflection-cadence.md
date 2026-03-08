# Daily Reflection Cadence Runbook

> **Story**: ST-DAILY-REFLECTION-001
> **Last Updated**: 2026-03-08
> **Owner**: ChiseAI Infrastructure Team
> **Cadence**: 7-day stabilization

## Overview

This runbook documents the 7-day daily reflection cadence system, which generates daily reflection-quality reports and posts them to Discord. The system tracks KPIs, trends, incidents, and blockers to provide continuous visibility into system health and improvement trajectories.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Manual Execution](#manual-execution)
4. [Scheduled Execution](#scheduled-execution)
5. [Discord Integration](#discord-integration)
6. [Monitoring & Verification](#monitoring--verification)
7. [Troubleshooting](#troubleshooting)
8. [Cadence Management](#cadence-management)

---

## Quick Start

### Prerequisites

- Redis accessible at `chiseai-redis:6380`
- Discord webhook configured in `.env`
- Python 3.11+ with `redis`, `requests`, `pyyaml` packages

### Test Manual Execution

```bash
# Generate report without posting to Discord
python3 scripts/standup/generate_daily_reflection_report.py --verbose

# Generate and post to Discord
python3 scripts/standup/generate_daily_reflection_report.py --post-discord --verbose
```

### Verify Discord Delivery

Check the #development channel for the report. It should appear as:

```
# 📊 Daily Reflection Report - Day 1/7
**Date:** 2026-03-08
**Cadence:** 7-day-stabilization
...
```

---

## Architecture

### Components

| Component | Path | Description |
|-----------|------|-------------|
| Report Generator | `scripts/standup/generate_daily_reflection_report.py` | Main script that generates reports |
| Cron Configuration | `infrastructure/cron/chiseai-daily-reflection` | Cron job definition (09:00 UTC) |
| Redis Keys | `bmad:chiseai:daily_reflection_report:*` | Historical report storage |
| Discord Channel | #development | Delivery target for reports |

### Data Sources

The report aggregates data from:

1. **Redis Metrics**
   - `bmad:chiseai:metrics:reflection` - Reflection completion rates
   - `bmad:chiseai:metrics:iterations` - Iteration tracking
   - `bmad:chiseai:incidents:*` - Active incidents
   - `bmad:chiseai:ownership_conflicts` - Scope conflicts

2. **Workflow Status**
   - `docs/bmm-workflow-status.yaml` - Story status and blockers

3. **Git Activity**
   - Commits, merges, and active branches

### Report Contents

Each daily report includes:

1. **KPI Snapshot**
   - Reflection completion rate
   - Metacognitive calibration score
   - Active stories count
   - Completed iterations
   - Average iteration duration

2. **Trend Deltas (7-day)**
   - Reflection rate delta
   - Calibration improvement
   - Velocity trend (improving/stable/declining)
   - Blocker trend

3. **Incidents**
   - Active incidents from last 24 hours
   - Severity, type, story ID, description

4. **Blockers**
   - Workflow-blocked stories
   - Scope conflicts
   - Validation failures

5. **Git Activity**
   - Commits today
   - Merges today
   - Active feature branches

6. **Recommendations**
   - Actionable suggestions based on current metrics

---

## Manual Execution

### Basic Execution

```bash
# Run from repository root
cd /home/tacopants/projects/ChiseAI

# Generate report (prints to stdout)
python3 scripts/standup/generate_daily_reflection_report.py
```

### With Discord Posting

```bash
# Generate and post to Discord
python3 scripts/standup/generate_daily_reflection_report.py --post-discord --verbose
```

### Specify Day Number

```bash
# Manually specify day 3 of 7
python3 scripts/standup/generate_daily_reflection_report.py --day 3 --total-days 7 --post-discord
```

### Save to File

```bash
# Save JSON report to file
python3 scripts/standup/generate_daily_reflection_report.py --output /tmp/report.json --verbose
```

### Full Command Reference

```bash
python3 scripts/standup/generate_daily_reflection_report.py \
  --day 1 \
  --total-days 7 \
  --post-discord \
  --redis-host chiseai-redis \
  --redis-port 6380 \
  --output /tmp/daily_report.json \
  --verbose
```

---

## Scheduled Execution

### Option 1: System Cron (Recommended for Host)

#### Install Cron Job

```bash
# Copy cron file to cron.d
sudo cp infrastructure/cron/chiseai-daily-reflection /etc/cron.d/

# Set proper permissions
sudo chmod 644 /etc/cron.d/chiseai-daily-reflection

# Verify installation
sudo crontab -l | grep daily-reflection
```

#### Verify Cron is Running

```bash
# Check cron service
sudo systemctl status cron

# Check cron logs
sudo tail -f /var/log/syslog | grep CRON
```

### Option 2: Docker Scheduler (Recommended for Containers)

The `chiseai-brain-scheduler` container can be extended to include daily reflection reports.

#### Add to Scheduler

Edit `infrastructure/docker/docker-compose.scheduler.yml`:

```yaml
environment:
  # Add daily reflection interval
  - SCHEDULER_INTERVAL_DAILY_REFLECTION=86400  # 24 hours
```

#### Modify Scheduler Script

Add daily reflection job to the scheduler loop (see `infrastructure/docker/scheduler_entrypoint.sh`).

### Option 3: Woodpecker CI Cron

For CI-based execution, add a cron pipeline:

```yaml
# .woodpecker/daily-reflection.yml
when:
  - event: cron
    cron: daily-reflection

steps:
  generate-report:
    image: python:3.11
    commands:
      - pip install redis requests pyyaml
      - python3 scripts/standup/generate_daily_reflection_report.py --post-discord
```

---

## Discord Integration

### Configuration

Discord integration requires one of:

1. **Webhook URL** (Preferred)
   ```bash
   export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   ```

2. **Bot Token + Channel ID**
   ```bash
   export DISCORD_BOT_TOKEN="..."
   export DISCORD_DEVELOPMENT_CHANNEL_ID="1444447985378398459"
   ```

### Test Discord Delivery

```bash
# Test webhook directly
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "✅ Daily Reflection Reporter test message"}'

# Test via script
python3 scripts/standup/generate_daily_reflection_report.py --post-discord --verbose
```

### Expected Output

The report appears in #development channel with:

```
# 📊 Daily Reflection Report - Day 1/7
**Date:** 2026-03-08
**Cadence:** 7-day-stabilization

## ✅ Health Status: STABLE

## 📈 KPI Snapshot
- Reflection Completion Rate: 85.0%
- Metacog Calibration Score: 72.0%
- Active Stories: 5
- Completed Iterations: 12
- Avg Iteration Duration: 4.5h

## 📉 Trend Deltas (7-day)
- 📈 Reflection Rate Delta: +5.0%
- 📈 Calibration Improvement: +3.0%
- Velocity Trend: Improving
- Blocker Trend: Stable

## 🚨 Incidents (0)
✅ No active incidents in last 24 hours

## 🔒 Blockers (0)
✅ No active blockers

## 🔀 Git Activity (Today)
- Commits: 8
- Merges: 2
- Active Branches: 3

## 💡 Recommendations
✅ System healthy - maintain current practices

---
🤖 Generated by ChiseAI Daily Reflection Reporter
📅 2026-03-08T09:00:00
```

---

## Monitoring & Verification

### Check Report Generation

```bash
# Check latest report in Redis
redis-cli -h chiseai-redis -p 6380 HGETALL bmad:chiseai:daily_reflection_report:$(date +%Y-%m-%d)

# List last 7 days of reports
for i in {0..6}; do
  date=$(date -d "$i days ago" +%Y-%m-%d)
  echo "=== $date ==="
  redis-cli -h chiseai-redis -p 6380 HGET bmad:chiseai:daily_reflection_report:$date day
done
```

### Check Logs

```bash
# View today's log
tail -f /home/tacopants/projects/ChiseAI/logs/daily-reflection/daily_$(date +%Y%m%d).log

# Search for errors
grep -i error /home/tacopants/projects/ChiseAI/logs/daily-reflection/daily_*.log
```

### Verify Schedule Active

```bash
# Check cron job
crontab -l | grep daily-reflection

# Expected output:
# 0 9 * * * cd /home/tacopants/projects/ChiseAI && /usr/bin/python3 scripts/standup/generate_daily_reflection_report.py --post-discord --redis-host chiseai-redis --verbose >> $LOG_DIR/daily_$(date +\%Y\%m\%d).log 2>&1
```

### Monitor Redis Keys

```bash
# Scan for report keys
redis-cli -h chiseai-redis -p 6380 SCAN 0 MATCH bmad:chiseai:daily_reflection_report:* COUNT 10

# Check cadence start date
redis-cli -h chiseai-redis -p 6380 GET bmad:chiseai:reflection_cadence:start_date
```

---

## Troubleshooting

### Issue: Report not posting to Discord

**Symptoms:**
- Script runs successfully
- No message appears in #development

**Diagnosis:**
```bash
# Check environment variables
echo $DISCORD_WEBHOOK_URL
echo $DISCORD_BOT_TOKEN
echo $DISCORD_DEVELOPMENT_CHANNEL_ID

# Test webhook manually
curl -X POST $DISCORD_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

**Solution:**
1. Verify webhook URL is correct in `.env`
2. Check Discord channel permissions
3. Try using bot token instead of webhook

### Issue: Redis connection failed

**Symptoms:**
- Error: "Redis connection failed"
- KPIs show zeros

**Diagnosis:**
```bash
# Check Redis is running
docker ps | grep redis

# Test connection
redis-cli -h chiseai-redis -p 6380 PING
```

**Solution:**
1. Ensure Redis container is running: `docker start chiseai-redis`
2. Verify network connectivity: `docker network inspect chiseai`
3. Check Redis host is correct (use `chiseai-redis` from containers, `localhost` from host)

### Issue: Cron job not running

**Symptoms:**
- No logs generated
- No reports in Redis

**Diagnosis:**
```bash
# Check cron service
sudo systemctl status cron

# Check cron logs
sudo grep CRON /var/log/syslog | tail -20

# Verify cron job syntax
crontab -l
```

**Solution:**
1. Ensure cron service is running: `sudo systemctl start cron`
2. Verify cron job is installed: `sudo crontab -l`
3. Check script permissions: `ls -l scripts/standup/generate_daily_reflection_report.py`
4. Test manual execution first

### Issue: Wrong day number calculated

**Symptoms:**
- Day number doesn't match expected day of cadence

**Diagnosis:**
```bash
# Check cadence start date
redis-cli -h chiseai-redis -p 6380 GET bmad:chiseai:reflection_cadence:start_date
```

**Solution:**
1. Set correct start date: `redis-cli -h chiseai-redis -p 6380 SET bmad:chiseai:reflection_cadence:start_date "2026-03-08"`
2. Or manually specify day: `--day 3`

---

## Cadence Management

### Start New 7-Day Cadence

```bash
# Set start date in Redis
redis-cli -h chiseai-redis -p 6380 SET bmad:chiseai:reflection_cadence:start_date "2026-03-08"

# Generate day 1 report
python3 scripts/standup/generate_daily_reflection_report.py --day 1 --post-discord --verbose
```

### Check Current Cadence Status

```bash
# Get start date
redis-cli -h chiseai-redis -p 6380 GET bmad:chiseai:reflection_cadence:start_date

# Calculate current day
python3 -c "
from datetime import datetime
start = datetime.strptime('2026-03-08', '%Y-%m-%d')
current_day = (datetime.now() - start).days + 1
print(f'Day {min(current_day, 7)} of 7')
"
```

### Reset Cadence

```bash
# Clear start date
redis-cli -h chiseai-redis -p 6380 DEL bmad:chiseai:reflection_cadence:start_date

# Start fresh
redis-cli -h chiseai-redis -p 6380 SET bmad:chiseai:reflection_cadence:start_date "$(date +%Y-%m-%d)"
```

### Extend Cadence

To extend beyond 7 days, modify the cron job or scheduler configuration:

```bash
# For 14-day cadence
python3 scripts/standup/generate_daily_reflection_report.py --total-days 14 --post-discord
```

---

## Related Documentation

- **Discord Notifications Runbook**: `docs/runbooks/discord-notifications.md`
- **Reflection Scheduler Ops**: `docs/runbooks/reflection-scheduler-ops.md`
- **Metacognition Operations**: `docs/runbooks/metacog-ops.md` (if exists)
- **Workflow Status**: `docs/bmm-workflow-status.yaml`
- **Cron File**: `infrastructure/cron/chiseai-daily-reflection`

---

## Contact

For issues or questions:
- **Infrastructure Team**: Check #development channel
- **Runbook Owner**: ChiseAI Infrastructure Team
- **Escalation**: Create incident with tag `daily-reflection`

---

## Changelog

### 2026-03-08
- Initial creation of daily reflection cadence system
- Added 7-day stabilization support
- Integrated Discord delivery
- Created manual and scheduled execution paths
