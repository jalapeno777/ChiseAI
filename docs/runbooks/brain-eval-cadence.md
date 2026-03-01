# BrainEval Cadence System Runbook

> **Story:** ST-BRAIN-EVAL-005  
> **Last Updated:** 2026-03-01  
> **Owner:** Platform Team  
> **Status:** READY FOR USE

---

> **Safety Note:** This documentation covers evaluation and observability only. No risk caps, promotion gates, or live trading behavior are modified by this system.

---

## 1. Overview

### 1.1 Purpose

The **BrainEval Cadence System** provides automated, scheduled evaluation runs at three distinct frequencies (6-hour, daily, weekly) to continuously monitor agent brain performance, detect issues, and track KPIs. This lightweight evaluation layer ensures early detection of problems without blocking critical trading operations.

### 1.2 Key Principles

| Principle | Description |
|-----------|-------------|
| **Non-Blocking** | Evaluations run asynchronously and don't block trading |
| **Layered Depth** | 6h (quick check) → daily (analysis) → weekly (comprehensive) |
| **Issue Detection** | Automatic log scanning for problems |
| **Trend Analysis** | Track performance and issues over time |
| **Safe Observability** | Read-only evaluation; no modifications to trading logic |

### 1.3 Cadence Summary

| Cadence | Frequency | Purpose | Duration |
|---------|-----------|---------|----------|
| **6h** | Every 6 hours | Quick health check, KPI snapshot, recent issues | ~30 seconds |
| **Daily** | Once per day | Full KPI analysis, trend comparison, issue aggregation | ~2 minutes |
| **Weekly** | Once per week | Comprehensive analysis, framework recommendations | ~5 minutes |

---

## 2. Three-Level Cadence System

### 2.1 6-Hour Evaluation

**Purpose:** Quick health check to catch immediate problems

**What It Computes:**
- KPI snapshot from recent BrainEvaluator runs
- Data freshness checks (Redis, InfluxDB, Qdrant, PostgreSQL)
- Recent issue detection from logs
- Basic mitigation suggestions

**Output Example:**
```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-03-01T12:00:00Z",
  "cadence": "6h",
  "kpis": {
    "avg_accuracy": 0.9234,
    "avg_precision": 0.9156,
    "avg_recall": 0.9312,
    "avg_f1_score": 0.9233,
    "evaluations_count": 10,
    "passed_count": 9,
    "latest_version": "brain-v2.3.1",
    "latest_status": "passed"
  },
  "data_freshness": {
    "redis": "fresh",
    "influxdb": "fresh",
    "qdrant": "fresh",
    "postgres": "not_checked"
  },
  "issues": [],
  "mitigations": []
}
```

**When to Use:**
- Continuous monitoring between deeper evaluations
- Quick sanity checks after deployments
- Early warning system for emerging problems

### 2.2 Daily Evaluation

**Purpose:** Comprehensive daily analysis with trend tracking

**What It Computes:**
- All 6h evaluation content, plus:
- Proxy metrics (CPU, memory, disk, Redis stats)
- 24-hour issue aggregation
- Trend comparison with previous day
- Category-wise issue breakdown

**Output Example:**
```json
{
  "eval_id": "660e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-03-01T06:00:00Z",
  "cadence": "daily",
  "kpis": {
    "avg_accuracy": 0.9234,
    "trend_analysis": {
      "direction": "improving",
      "change_percent": 2.3
    }
  },
  "proxies": {
    "cpu_percent": 45.2,
    "memory_percent": 62.8,
    "disk_percent": 38.5,
    "redis_connected_clients": 12,
    "redis_used_memory_mb": 256.4
  },
  "data_freshness": {
    "redis": "fresh",
    "influxdb": "fresh",
    "qdrant": "fresh"
  },
  "issues": [
    {
      "issue_id": "abc-123",
      "category": "db_connectivity",
      "severity": "P2",
      "description": "Detected db_connectivity issue: ConnectionRefusedError",
      "source": "log_scan:db_connectivity"
    }
  ],
  "mitigations": [
    {
      "mitigation_id": "mit-456",
      "issue_id": "abc-123",
      "action": "Verify database connectivity and credentials",
      "result": "partial"
    }
  ]
}
```

**When to Use:**
- Daily operations review
- Performance trend analysis
- Issue pattern detection

### 2.3 Weekly Evaluation

**Purpose:** Deep comprehensive analysis with strategic recommendations

**What It Computes:**
- All daily evaluation content, plus:
- Full week trend analysis
- Historical data comparison
- Framework improvement recommendations
- Severity trend analysis
- Repeated issue pattern detection

**Output Example:**
```json
{
  "eval_id": "770e8400-e29b-41d4-a716-446655440002",
  "timestamp": "2026-03-01T06:00:00Z",
  "cadence": "weekly",
  "kpis": {
    "avg_accuracy": 0.9234,
    "trend_analysis": {
      "evaluations_count": 28,
      "avg_issues_per_eval": 1.2,
      "critical_issues_count": 2,
      "trend_direction": "improving"
    }
  },
  "proxies": {
    "cpu_percent": 42.1,
    "memory_percent": 58.3
  },
  "issues": [],
  "mitigations": [],
  "recommendations": [
    "Consider implementing connection pooling for database connections",
    "Review database connection timeout settings"
  ]
}
```

**When to Use:**
- Weekly performance reviews
- Strategic planning for brain improvements
- Identifying systemic issues
- Capacity planning

---

## 3. Manual Execution

### 3.1 Basic Commands

**Run 6-hour evaluation:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence 6h
```

**Run daily evaluation:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence daily
```

**Run weekly evaluation:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence weekly
```

### 3.2 Advanced Options

**Specify output directory:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence daily --output-dir /custom/path/brain-eval
```

**Dry run (testing):**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence 6h --dry-run
```

**Disable Redis (for testing):**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence 6h --no-redis
```

### 3.3 Expected Output

**Successful 6h evaluation:**
```
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Starting 6h evaluation
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Output directory: _bmad-output/brain-eval
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Dry run: False
2026-03-01 12:00:01 - schedule_brain_eval - INFO - Running 6h evaluation...
2026-03-01 12:00:01 - MiniBrainEval - INFO - Starting 6h evaluation
2026-03-01 12:00:01 - MiniBrainEval - INFO - Detected 0 issues from log scan
2026-03-01 12:00:01 - MiniBrainEval - INFO - 6h evaluation completed with 0 issues
2026-03-01 12:00:01 - schedule_brain_eval - INFO - Evaluation completed in 0.52 seconds
2026-03-01 12:00:01 - schedule_brain_eval - INFO - Issues detected: 0
2026-03-01 12:00:01 - schedule_brain_eval - INFO - Mitigations applied: 0
2026-03-01 12:00:01 - schedule_brain_eval - INFO - Result saved to _bmad-output/brain-eval/6h/2026-03-01T12-00-00.json
2026-03-01 12:00:01 - schedule_brain_eval - INFO - 6h evaluation completed successfully
```

**Dry run output:**
```
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Starting 6h evaluation
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Output directory: _bmad-output/brain-eval
2026-03-01 12:00:00 - schedule_brain_eval - INFO - Dry run: True
2026-03-01 12:00:00 - schedule_brain_eval - INFO - DRY RUN: Skipping actual evaluation
2026-03-01 12:00:00 - schedule_brain_eval - INFO - DRY RUN: Would save result to _bmad-output/brain-eval/6h/2026-03-01T12-00-00.json
2026-03-01 12:00:00 - schedule_brain_eval - INFO - DRY RUN: Saved mock result to _bmad-output/brain-eval/6h/2026-03-01T12-00-00.json
```

---

## 4. Cron Setup

### 4.1 Shell Script Wrappers

Create wrapper scripts for cron execution:

**`scripts/evaluation/run_6h_eval.sh`:**
```bash
#!/bin/bash
# Run 6-hour BrainEval
# Executed at 0:00, 6:00, 12:00, 18:00 UTC

set -e

PROJECT_ROOT="/home/tacopants/projects/ChiseAI"
LOG_FILE="$PROJECT_ROOT/_bmad-output/brain-eval/logs/cron-6h.log"

cd "$PROJECT_ROOT"

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Starting 6h BrainEval" >> "$LOG_FILE"

python3 scripts/evaluation/schedule_brain_eval.py \
  --cadence 6h \
  --output-dir _bmad-output/brain-eval \
  2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Completed with exit code $EXIT_CODE" >> "$LOG_FILE"
exit $EXIT_CODE
```

**`scripts/evaluation/run_daily_eval.sh`:**
```bash
#!/bin/bash
# Run daily BrainEval
# Executed at 06:00 UTC daily

set -e

PROJECT_ROOT="/home/tacopants/projects/ChiseAI"
LOG_FILE="$PROJECT_ROOT/_bmad-output/brain-eval/logs/cron-daily.log"

cd "$PROJECT_ROOT"

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Starting daily BrainEval" >> "$LOG_FILE"

python3 scripts/evaluation/schedule_brain_eval.py \
  --cadence daily \
  --output-dir _bmad-output/brain-eval \
  2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Completed with exit code $EXIT_CODE" >> "$LOG_FILE"
exit $EXIT_CODE
```

**`scripts/evaluation/run_weekly_eval.sh`:**
```bash
#!/bin/bash
# Run weekly BrainEval
# Executed at 06:00 UTC every Sunday

set -e

PROJECT_ROOT="/home/tacopants/projects/ChiseAI"
LOG_FILE="$PROJECT_ROOT/_bmad-output/brain-eval/logs/cron-weekly.log"

cd "$PROJECT_ROOT"

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Starting weekly BrainEval" >> "$LOG_FILE"

python3 scripts/evaluation/schedule_brain_eval.py \
  --cadence weekly \
  --output-dir _bmad-output/brain-eval \
  2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') - Completed with exit code $EXIT_CODE" >> "$LOG_FILE"
exit $EXIT_CODE
```

**Make scripts executable:**
```bash
chmod +x scripts/evaluation/run_6h_eval.sh
chmod +x scripts/evaluation/run_daily_eval.sh
chmod +x scripts/evaluation/run_weekly_eval.sh
```

### 4.2 Crontab Entries

**Add to `/etc/crontab` or user crontab:**

```bash
# BrainEval Cadence Schedule
# ==========================

# 6-hour evaluations: 00:00, 06:00, 12:00, 18:00 UTC
0 0,6,12,18 * * * tacopants /home/tacopants/projects/ChiseAI/scripts/evaluation/run_6h_eval.sh

# Daily evaluation: 06:00 UTC
0 6 * * * tacopants /home/tacopants/projects/ChiseAI/scripts/evaluation/run_daily_eval.sh

# Weekly evaluation: 06:00 UTC every Sunday
0 6 * * 0 tacopants /home/tacopants/projects/ChiseAI/scripts/evaluation/run_weekly_eval.sh
```

**Or using `crontab -e`:**
```bash
# Edit crontab
crontab -e

# Add these lines:
0 0,6,12,18 * * * /home/tacopants/projects/ChiseAI/scripts/evaluation/run_6h_eval.sh
0 6 * * * /home/tacopants/projects/ChiseAI/scripts/evaluation/run_daily_eval.sh
0 6 * * 0 /home/tacopants/projects/ChiseAI/scripts/evaluation/run_weekly_eval.sh
```

### 4.3 Cron Schedule Reference

| Cadence | Cron Expression | Execution Times (UTC) |
|---------|----------------|----------------------|
| 6h | `0 0,6,12,18 * * *` | 00:00, 06:00, 12:00, 18:00 |
| Daily | `0 6 * * *` | 06:00 every day |
| Weekly | `0 6 * * 0` | 06:00 every Sunday |

---

## 5. Output Locations and Formats

### 5.1 Directory Structure

```
_bmad-output/brain-eval/
├── 6h/
│   ├── 2026-03-01T00-00-00.json
│   ├── 2026-03-01T06-00-00.json
│   ├── 2026-03-01T12-00-00.json
│   └── 2026-03-01T18-00-00.json
├── daily/
│   ├── 2026-02-28.json
│   ├── 2026-03-01.json
│   └── 2026-03-02.json
├── weekly/
│   ├── 2026-W08.json
│   ├── 2026-W09.json
│   └── 2026-W10.json
└── logs/
    ├── schedule_2026-03-01.log
    ├── cron-6h.log
    ├── cron-daily.log
    └── cron-weekly.log
```

### 5.2 Filename Conventions

| Cadence | Format | Example |
|---------|--------|---------|
| 6h | `YYYY-MM-DDTHH-00-00.json` | `2026-03-01T12-00-00.json` |
| Daily | `YYYY-MM-DD.json` | `2026-03-01.json` |
| Weekly | `YYYY-WNN.json` (ISO week) | `2026-W09.json` |

### 5.3 Output Schema

Each evaluation produces a `MiniEvalResult` with the following structure:

```json
{
  "eval_id": "uuid",
  "timestamp": "ISO-8601 timestamp",
  "cadence": "6h|daily|weekly",
  "kpis": {
    "avg_accuracy": 0.0,
    "avg_precision": 0.0,
    "avg_recall": 0.0,
    "avg_f1_score": 0.0,
    "evaluations_count": 0,
    "passed_count": 0,
    "latest_version": "string",
    "latest_status": "passed|failed",
    "latest_accuracy": 0.0
  },
  "proxies": {
    "cpu_percent": 0.0,
    "memory_percent": 0.0,
    "disk_percent": 0.0,
    "redis_connected_clients": 0,
    "redis_used_memory_mb": 0.0
  },
  "data_freshness": {
    "redis": "fresh|stale|no_client",
    "influxdb": "fresh|stale|no_client",
    "qdrant": "fresh|stale|no_client",
    "postgres": "fresh|stale|not_checked"
  },
  "issues": [
    {
      "issue_id": "uuid",
      "category": "file_access|db_connectivity|env_slowdown|tool_error|other",
      "severity": "P0|P1|P2|P3",
      "description": "string",
      "source": "string",
      "timestamp": "ISO-8601 timestamp"
    }
  ],
  "mitigations": [
    {
      "mitigation_id": "uuid",
      "issue_id": "uuid",
      "action": "string",
      "result": "success|failure|partial",
      "timestamp": "ISO-8601 timestamp"
    }
  ]
}
```

### 5.4 Redis Storage

Results are also stored in Redis for programmatic access:

**Key Pattern:** `bmad:chiseai:brain:eval:mini:{cadence}:{timestamp}`

**Example:**
```
bmad:chiseai:brain:eval:mini:6h:2026-03-01T12:00:00
bmad:chiseai:brain:eval:mini:daily:2026-03-01
bmad:chiseai:brain:eval:mini:weekly:2026-W09
```

**TTL:** 30 days (2592000 seconds)

---

## 6. Troubleshooting

### 6.1 Common Issues

#### Issue: Evaluation fails with Redis connection error

**Symptoms:**
```
WARNING: Failed to connect to Redis: Connection refused
Continuing without Redis client
```

**Diagnosis:**
```bash
# Check Redis is running
docker ps | grep chiseai-redis

# Check Redis connectivity
redis-cli -h localhost -p 6380 ping

# Check from container (if in Docker)
redis-cli -h host.docker.internal -p 6380 ping
```

**Resolution:**
1. Ensure Redis container is running: `docker start chiseai-redis`
2. Verify port mapping: `docker port chiseai-redis`
3. Check firewall rules if applicable
4. Run with `--no-redis` flag if Redis is unavailable

#### Issue: No KPIs collected

**Symptoms:**
```json
"kpis": {
  "status": "no_evaluator"
}
```

**Diagnosis:**
```bash
# Check if BrainEvaluator is configured
python3 -c "from brain.evaluation import BrainEvaluator; print('Available')"
```

**Resolution:**
1. This is expected if BrainEvaluator is not configured
2. KPIs will be populated when BrainEvaluator is available
3. Proxy metrics are still collected as fallback

#### Issue: Issues not being detected

**Symptoms:**
```
Issues detected: 0
```
But you know there are errors in logs.

**Diagnosis:**
```bash
# Check log file location
ls -la /var/log/chiseai/app.log
ls -la logs/app.log

# Check log content
tail -100 logs/app.log | grep -i error
```

**Resolution:**
1. Ensure logs are being written to expected locations
2. Check LOG_PATTERNS in mini_brain_eval.py match your log format
3. Specify custom log source if needed

#### Issue: Cron job not running

**Symptoms:**
No output files being generated on schedule.

**Diagnosis:**
```bash
# Check cron logs
grep CRON /var/log/syslog | grep brain

# Check crontab entries
crontab -l

# Check script permissions
ls -la scripts/evaluation/run_*_eval.sh
```

**Resolution:**
1. Ensure scripts are executable: `chmod +x scripts/evaluation/run_*.sh`
2. Verify cron daemon is running: `systemctl status cron`
3. Check PATH in crontab includes Python
4. Add full paths to crontab entries

### 6.2 Debug Commands

**Test evaluation manually:**
```bash
# Run with verbose logging
python3 scripts/evaluation/schedule_brain_eval.py --cadence 6h --dry-run

# Check output files
ls -la _bmad-output/brain-eval/6h/

# View latest result
cat _bmad-output/brain-eval/6h/*.json | jq .
```

**Check Redis data:**
```bash
# List all mini eval keys
redis-cli -h localhost -p 6380 KEYS "bmad:chiseai:brain:eval:mini:*"

# Get specific result
redis-cli -h localhost -p 6380 GET "bmad:chiseai:brain:eval:mini:6h:2026-03-01T12:00:00"
```

**Check log files:**
```bash
# View recent cron logs
tail -100 _bmad-output/brain-eval/logs/cron-6h.log

# View schedule logs
tail -100 _bmad-output/brain-eval/logs/schedule_2026-03-01.log
```

### 6.3 Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | No action needed |
| 1 | Failure | Check logs for details |

### 6.4 Contact Information

| Issue Type | Contact | Response SLA |
|-----------|---------|--------------|
| Cron issues | Platform Team | < 4 hours |
| Redis connectivity | Platform Team | < 2 hours |
| KPI collection | Brain Team | < 1 business day |
| Feature requests | Captain Craig | < 1 week |

---

## 7. Monitoring and Alerting

### 7.1 Key Metrics to Monitor

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `eval_duration_seconds` | Time to complete evaluation | > 60s (6h), > 180s (daily), > 300s (weekly) |
| `issues_detected_count` | Number of issues found | > 10 (warning), > 25 (critical) |
| `critical_issues_count` | P0 issues detected | > 0 (immediate alert) |
| `data_freshness` | Status of data sources | Any "stale" status |

### 7.2 Grafana Dashboard

Navigate to Grafana at `http://localhost:3001` and look for the "BrainEval Dashboard" to view:
- Evaluation success rate over time
- Issue trends by category
- KPI trends (accuracy, precision, recall, F1)
- Data freshness status
- Evaluation duration trends

### 7.3 Alerting Rules

**Critical alert (P0 issue detected):**
```yaml
# Alert when critical issues are found
- alert: BrainEvalCriticalIssue
  expr: brain_eval_critical_issues > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "BrainEval detected critical issues"
    description: "{{ $value }} critical (P0) issues detected"
```

**Warning alert (stale data):**
```yaml
# Alert when data sources are stale
- alert: BrainEvalStaleData
  expr: brain_eval_data_freshness{status="stale"} > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "BrainEval data source is stale"
    description: "Data source {{ $labels.source }} is stale"
```

---

## 8. References

### 8.1 Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Mini BrainEval Runbook | `docs/runbooks/mini-brain-eval.md` | Detailed MiniEval documentation |
| Repeated Issues Runbook | `docs/runbooks/repeated-issues.md` | Issue detection and analysis |
| Brain Evaluation System | `src/brain/evaluation.py` | Core BrainEvaluator implementation |

### 8.2 Source Code

| Component | Location |
|-----------|----------|
| Scheduling Script | `scripts/evaluation/schedule_brain_eval.py` |
| Mini BrainEval Engine | `src/evaluation/mini_brain_eval.py` |
| Schema Definitions | `src/evaluation/schemas/mini_eval.py` |

### 8.3 Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `output_dir` | `_bmad-output/brain-eval` | Directory for evaluation results |
| `redis_ttl` | 2592000 (30 days) | TTL for Redis stored results |
| `log_dir` | `{output_dir}/logs` | Directory for log files |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-01 | Platform Team | Initial runbook creation |

---

*This runbook was created per ST-BRAIN-EVAL-005 requirements and is ready for operational use.*
