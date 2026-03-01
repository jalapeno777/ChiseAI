# Mini BrainEval Runbook

> **Story:** ST-BRAIN-EVAL-005  
> **Last Updated:** 2026-03-01  
> **Owner:** Platform Team  
> **Status:** READY FOR USE

---

> **Safety Note:** This documentation covers evaluation and observability only. No risk caps, promotion gates, or live trading behavior are modified by this system.

---

## 1. Overview

### 1.1 What is Mini BrainEval?

**Mini BrainEval** is a lightweight evaluation engine that provides continuous monitoring of the agent brain's performance without the overhead of full evaluation runs. It operates at three cadences (6h, daily, weekly) to deliver layered insights into system health and performance.

### 1.2 Key Features

| Feature | Description |
|---------|-------------|
| **KPI Collection** | Gathers accuracy, precision, recall, F1 from BrainEvaluator |
| **Data Freshness Checks** | Monitors Redis, InfluxDB, Qdrant, PostgreSQL connectivity |
| **Issue Detection** | Scans logs for errors and problems |
| **Mitigation Tracking** | Records suggested fixes for detected issues |
| **Trend Analysis** | Weekly cadence includes historical trend comparison |

### 1.3 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Mini BrainEval                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 6h Eval      │  │ Daily Eval   │  │ Weekly Eval  │      │
│  │ (Quick)      │  │ (Analysis)   │  │ (Comprehensive)│    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         ▼                 ▼                 ▼               │
│  ┌─────────────────────────────────────────────────┐       │
│  │              Core Components                     │       │
│  │  • KPI Collector                                │       │
│  │  • Data Freshness Checker                       │       │
│  │  • Issue Detector                               │       │
│  │  • Mitigation Engine                            │       │
│  │  • Proxy Metrics Collector                      │       │
│  │  • Trend Analyzer                               │       │
│  └─────────────────────────────────────────────────┘       │
│                           │                                 │
│                           ▼                                 │
│  ┌─────────────────────────────────────────────────┐       │
│  │              Storage Layer                       │       │
│  │  • Redis (bmad:chiseai:brain:eval:mini:*)       │       │
│  │  • InfluxDB (metrics)                           │       │
│  │  • File System (_bmad-output/brain-eval/)       │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Schema Documentation

### 2.1 MiniEvalResult

The primary output of every Mini BrainEval run.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `eval_id` | string (UUID) | Unique identifier for this evaluation |
| `timestamp` | string (ISO-8601) | When evaluation was run |
| `cadence` | string | "6h", "daily", or "weekly" |
| `kpis` | dict | Key Performance Indicators from BrainEvaluator |
| `proxies` | dict | System-level proxy metrics |
| `data_freshness` | dict | Status of each data source |
| `issues` | list[Issue] | Detected issues |
| `mitigations` | list[Mitigation] | Applied/suggested mitigations |

**Example:**
```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-03-01T12:00:00.123456+00:00",
  "cadence": "6h",
  "kpis": {
    "avg_accuracy": 0.9234,
    "avg_precision": 0.9156
  },
  "proxies": {},
  "data_freshness": {
    "redis": "fresh"
  },
  "issues": [],
  "mitigations": []
}
```

### 2.2 Issue

Represents a detected problem during evaluation.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `issue_id` | string (UUID) | Unique identifier for this issue |
| `category` | string | Issue category (see IssueCategory enum) |
| `severity` | string | Severity level (P0-P3) |
| `description` | string | Human-readable description |
| `source` | string | Where the issue was detected |
| `timestamp` | string (ISO-8601) | When the issue was detected |

**IssueCategory Enum:**

| Value | Description |
|-------|-------------|
| `file_access` | File not found, permission denied, I/O errors |
| `db_connectivity` | Database connection failures |
| `env_slowdown` | Timeouts, high latency, memory pressure |
| `tool_error` | MCP tool errors, API errors, HTTP errors |
| `other` | Uncategorized issues |

**IssueSeverity Enum:**

| Value | Level | Description |
|-------|-------|-------------|
| `P0` | Critical | Blocks evaluation, immediate attention required |
| `P1` | High | Significantly impacts evaluation quality |
| `P2` | Medium | Minor impact, should be addressed soon |
| `P3` | Low | Informational, monitor for patterns |

**Example:**
```json
{
  "issue_id": "abc12345-6789-0abc-def0-1234567890ab",
  "category": "db_connectivity",
  "severity": "P1",
  "description": "Detected db_connectivity issue: ConnectionRefusedError to database",
  "source": "log_scan:db_connectivity",
  "timestamp": "2026-03-01T12:00:00.123456+00:00"
}
```

### 2.3 Mitigation

Represents a suggested or applied fix for an issue.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `mitigation_id` | string (UUID) | Unique identifier for this mitigation |
| `issue_id` | string (UUID) | Reference to the issue being mitigated |
| `action` | string | Description of the mitigation action |
| `result` | string | Outcome of the mitigation (see MitigationResult) |
| `timestamp` | string (ISO-8601) | When the mitigation was applied |

**MitigationResult Enum:**

| Value | Description |
|-------|-------------|
| `success` | Issue fully resolved |
| `failure` | Mitigation did not help |
| `partial` | Mitigation provided partial relief |

**Example:**
```json
{
  "mitigation_id": "def67890-1234-5678-90ab-cdef12345678",
  "issue_id": "abc12345-6789-0abc-def0-1234567890ab",
  "action": "Verify database connectivity and credentials",
  "result": "partial",
  "timestamp": "2026-03-01T12:00:00.234567+00:00"
}
```

---

## 3. How Mini BrainEvals Function

### 3.1 KPI Collection

**Purpose:** Gather performance metrics from BrainEvaluator

**Process:**
1. Query BrainEvaluator for recent evaluations
2. Aggregate metrics (accuracy, precision, recall, F1)
3. Calculate averages across recent runs
4. Include latest version and status information

**KPI Fields Collected:**

| KPI | Description | Calculation |
|-----|-------------|-------------|
| `avg_accuracy` | Average accuracy | Mean of recent evaluation accuracies |
| `avg_precision` | Average precision | Mean of recent evaluation precisions |
| `avg_recall` | Average recall | Mean of recent evaluation recalls |
| `avg_f1_score` | Average F1 score | Mean of recent evaluation F1 scores |
| `evaluations_count` | Number of evaluations | Count of recent evaluations |
| `passed_count` | Passed evaluations | Count of evaluations with "passed" status |
| `latest_version` | Latest brain version | Version string from most recent eval |
| `latest_status` | Latest status | "passed" or "failed" |
| `latest_accuracy` | Latest accuracy | Accuracy from most recent eval |

**When KPIs are Unavailable:**
- If no BrainEvaluator is configured, `kpis["status"]` = `"no_evaluator"`
- If collection fails, `kpis["error"]` contains the error message

### 3.2 Data Freshness Checks

**Purpose:** Verify all data sources are accessible and up-to-date

**Sources Checked:**

| Source | Check Method | Status Values |
|--------|--------------|---------------|
| Redis | `ping()` command | "fresh", "stale: {error}", "no_client" |
| InfluxDB | Query for recent data | "fresh", "stale: {error}", "no_client" |
| Qdrant | Collection info query | "fresh", "stale: {error}", "no_client" |
| PostgreSQL | Connection test | "fresh", "stale", "not_checked" |

**Freshness Status Interpretation:**

| Status | Meaning | Action |
|--------|---------|--------|
| `fresh` | Source is accessible and responding | None |
| `stale: {error}` | Source is unreachable or slow | Investigate connectivity |
| `no_client` | No client configured for this source | Optional - configure if needed |
| `not_checked` | Not currently implemented | Future enhancement |

### 3.3 Issue Detection from Logs

**Purpose:** Scan log files for errors and problems

**Log Patterns Detected:**

| Category | Patterns | Default Severity |
|----------|----------|-----------------|
| `file_access` | `FileNotFoundError`, `PermissionError`, `IOError`, `OSError` | P2 |
| `db_connectivity` | `ConnectionRefusedError`, `OperationalError`, `psycopg2.*connection` | P1 |
| `env_slowdown` | `TimeoutError`, `slow.*query`, `high.*latency`, `memory.*pressure` | P2 |
| `tool_error` | `ToolError`, `MCP.*error`, `API.*error`, `HTTPError` | P1 |

**Severity Determination:**

Issues are assigned severity based on:
1. **Context keywords**: "critical", "fatal", "emergency", "panic" → P0
2. **Category defaults**: See table above
3. **Fallback**: P3 for uncategorized

**Log Source Locations:**

Mini BrainEval searches these locations in order:
1. `/var/log/chiseai/app.log`
2. `/tmp/chiseai.log`
3. `logs/app.log`

### 3.4 Mitigation Tracking

**Purpose:** Suggest and track fixes for detected issues

**Automatic Mitigations by Category:**

| Category | Suggested Action | Result |
|----------|------------------|--------|
| `file_access` | Check file permissions and paths | partial |
| `db_connectivity` | Verify database connectivity and credentials | partial |
| `env_slowdown` | Check system resources (CPU, memory, disk) | partial |
| `tool_error` | Retry operation with exponential backoff | partial |

**Note:** All automatic mitigations return `partial` because they are suggestions requiring human action, not automatic fixes.

---

## 4. How to Interpret Results

### 4.1 Healthy Evaluation

**Indicators:**
- ✅ `issues`: Empty array
- ✅ `data_freshness`: All "fresh" or "no_client"
- ✅ `kpis.avg_accuracy`: > 0.85
- ✅ `kpis.latest_status`: "passed"

**Example:**
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
    "passed_count": 10,
    "latest_version": "brain-v2.3.1",
    "latest_status": "passed",
    "latest_accuracy": 0.9450
  },
  "proxies": {},
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

### 4.2 Evaluation with Issues

**Indicators:**
- ⚠️ `issues`: Non-empty array
- ⚠️ `mitigations`: Contains suggestions

**Example:**
```json
{
  "eval_id": "660e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-03-01T12:00:00Z",
  "cadence": "daily",
  "kpis": { "avg_accuracy": 0.8234 },
  "proxies": { "cpu_percent": 78.5, "memory_percent": 85.2 },
  "data_freshness": {
    "redis": "fresh",
    "influxdb": "stale: Connection refused",
    "qdrant": "fresh"
  },
  "issues": [
    {
      "issue_id": "abc-123",
      "category": "db_connectivity",
      "severity": "P1",
      "description": "Detected db_connectivity issue: ConnectionRefusedError to InfluxDB",
      "source": "log_scan:db_connectivity",
      "timestamp": "2026-03-01T12:00:00Z"
    }
  ],
  "mitigations": [
    {
      "mitigation_id": "mit-456",
      "issue_id": "abc-123",
      "action": "Verify database connectivity and credentials",
      "result": "partial",
      "timestamp": "2026-03-01T12:00:00Z"
    }
  ]
}
```

**Action Required:**
1. Check InfluxDB container: `docker ps | grep influxdb`
2. Verify network connectivity
3. Check credentials configuration

### 4.3 Critical Evaluation

**Indicators:**
- 🚨 `issues` contains P0 severity
- 🚨 Evaluation itself failed

**Example:**
```json
{
  "eval_id": "770e8400-e29b-41d4-a716-446655440002",
  "timestamp": "2026-03-01T12:00:00Z",
  "cadence": "6h",
  "kpis": {},
  "proxies": {},
  "data_freshness": {},
  "issues": [
    {
      "issue_id": "crit-001",
      "category": "other",
      "severity": "P0",
      "description": "Evaluation failed: Redis connection timeout after 30 seconds",
      "source": "MiniBrainEval.run_6h_eval",
      "timestamp": "2026-03-01T12:00:00Z"
    }
  ],
  "mitigations": []
}
```

**Action Required:**
1. Immediate investigation of Redis
2. Check system resources
3. Review error logs for root cause

---

## 5. Integration with Main BrainEval

### 5.1 Relationship Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Evaluation Hierarchy                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────────────────────────────────────────────┐     │
│   │              Full BrainEval                       │     │
│   │  • Comprehensive test suite execution             │     │
│   │  • All metrics and validations                    │     │
│   │  • Promotion decisions                            │     │
│   │  • Triggered manually or on PR                    │     │
│   └──────────────────────────────────────────────────┘     │
│                           ▲                                 │
│                           │ provides KPIs                   │
│                           │                                 │
│   ┌──────────────────────────────────────────────────┐     │
│   │              Mini BrainEval                       │     │
│   │  • Lightweight KPI collection                     │     │
│   │  • Health checks                                  │     │
│   │  • Issue detection                                │     │
│   │  • Scheduled automatically (6h/daily/weekly)      │     │
│   └──────────────────────────────────────────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Data Flow

1. **Full BrainEval** runs comprehensive tests and stores results
2. **Mini BrainEval** queries BrainEvaluator for recent results
3. **Mini BrainEval** aggregates metrics into KPIs
4. **Mini BrainEval** performs additional health checks
5. **Mini BrainEval** stores results for trend analysis

### 5.3 When to Use Each

| Scenario | Use Full BrainEval | Use Mini BrainEval |
|----------|-------------------|-------------------|
| Pre-deployment validation | ✅ | ❌ |
| PR quality gate | ✅ | ❌ |
| Brain version promotion | ✅ | ❌ |
| Continuous monitoring | ❌ | ✅ |
| Quick health check | ❌ | ✅ |
| Trend analysis | ❌ | ✅ (weekly) |
| Issue detection | ❌ | ✅ |

---

## 6. Example Output Walkthrough

### 6.1 Complete 6h Evaluation

**Command:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence 6h
```

**Output:**
```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-03-01T12:00:00.123456+00:00",
  "cadence": "6h",
  "kpis": {
    "avg_accuracy": 0.9234,
    "avg_precision": 0.9156,
    "avg_recall": 0.9312,
    "avg_f1_score": 0.9233,
    "evaluations_count": 10,
    "passed_count": 9,
    "latest_version": "brain-v2.3.1",
    "latest_status": "passed",
    "latest_accuracy": 0.9450
  },
  "proxies": {},
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

**Interpretation:**
- ✅ All KPIs are healthy (accuracy > 0.90)
- ✅ 9/10 recent evaluations passed
- ✅ All data sources are fresh
- ✅ No issues detected
- **Status:** Healthy, no action required

### 6.2 Daily Evaluation with Issues

**Command:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence daily
```

**Output:**
```json
{
  "eval_id": "660e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-03-01T06:00:00.123456+00:00",
  "cadence": "daily",
  "kpis": {
    "avg_accuracy": 0.8756,
    "avg_precision": 0.8623,
    "avg_recall": 0.8891,
    "avg_f1_score": 0.8754,
    "evaluations_count": 24,
    "passed_count": 21,
    "latest_version": "brain-v2.3.1",
    "latest_status": "passed"
  },
  "proxies": {
    "cpu_percent": 45.2,
    "memory_percent": 72.8,
    "disk_percent": 38.5,
    "redis_connected_clients": 12,
    "redis_used_memory_mb": 256.4
  },
  "data_freshness": {
    "redis": "fresh",
    "influxdb": "fresh",
    "qdrant": "stale: Connection timeout",
    "postgres": "not_checked"
  },
  "issues": [
    {
      "issue_id": "issue-001",
      "category": "db_connectivity",
      "severity": "P1",
      "description": "Detected db_connectivity issue: ConnectionRefusedError to Qdrant",
      "source": "log_scan:db_connectivity",
      "timestamp": "2026-03-01T06:00:00.234567+00:00"
    }
  ],
  "mitigations": [
    {
      "mitigation_id": "mit-001",
      "issue_id": "issue-001",
      "action": "Verify database connectivity and credentials",
      "result": "partial",
      "timestamp": "2026-03-01T06:00:00.345678+00:00"
    }
  ]
}
```

**Interpretation:**
- ⚠️ KPIs slightly lower than expected (accuracy 0.87 vs target 0.90)
- ⚠️ 21/24 evaluations passed (87.5%)
- ⚠️ Memory usage elevated at 72.8%
- ⚠️ Qdrant is stale (connection timeout)
- ⚠️ 1 P1 issue detected
- **Status:** Degraded, investigate Qdrant connectivity

**Actions:**
1. Check Qdrant container: `docker ps | grep qdrant`
2. Verify Qdrant is accessible: `curl http://localhost:6333/collections`
3. Review recent logs for connection patterns
4. Monitor memory usage

### 6.3 Weekly Evaluation with Trends

**Command:**
```bash
python3 scripts/evaluation/schedule_brain_eval.py --cadence weekly
```

**Output:**
```json
{
  "eval_id": "770e8400-e29b-41d4-a716-446655440002",
  "timestamp": "2026-03-01T06:00:00.123456+00:00",
  "cadence": "weekly",
  "kpis": {
    "avg_accuracy": 0.9123,
    "avg_precision": 0.9045,
    "avg_recall": 0.9201,
    "avg_f1_score": 0.9122,
    "evaluations_count": 168,
    "passed_count": 162,
    "latest_version": "brain-v2.3.1",
    "trend_analysis": {
      "evaluations_count": 28,
      "avg_issues_per_eval": 0.8,
      "critical_issues_count": 0,
      "trend_direction": "improving"
    }
  },
  "proxies": {
    "cpu_percent": 42.1,
    "memory_percent": 65.3,
    "disk_percent": 35.2,
    "redis_connected_clients": 8,
    "redis_used_memory_mb": 198.7
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

**Interpretation:**
- ✅ KPIs are healthy and stable
- ✅ 162/168 weekly evaluations passed (96.4%)
- ✅ Trend analysis shows "improving" direction
- ✅ Average issues per eval: 0.8 (low)
- ✅ No critical issues this week
- ✅ All data sources fresh
- ✅ System resources healthy
- **Status:** Excellent, trending positive

---

## 7. Programmatic Access

### 7.1 Using MiniBrainEval Directly

```python
from evaluation.mini_brain_eval import MiniBrainEval
import redis

# Initialize with Redis client
redis_client = redis.Redis(host='localhost', port=6380, db=0)
evaluator = MiniBrainEval(redis_client=redis_client)

# Run evaluations
result_6h = evaluator.run_6h_eval()
result_daily = evaluator.run_daily_eval()
result_weekly = evaluator.run_weekly_eval()

# Access results
print(f"Issues detected: {len(result_6h.issues)}")
print(f"Has critical issues: {result_6h.has_critical_issues()}")
print(f"P0 issues: {len(result_6h.get_issues_by_severity('P0'))}")

# Get specific issue categories
db_issues = result_6h.get_issues_by_category('db_connectivity')
for issue in db_issues:
    print(f"  - {issue.description}")

# Get mitigations for an issue
if result_6h.issues:
    mitigations = result_6h.get_mitigations_for_issue(result_6h.issues[0].issue_id)
    for mit in mitigations:
        print(f"Mitigation: {mit.action}")
```

### 7.2 Retrieving Historical Results

```python
from evaluation.mini_brain_eval import MiniBrainEval
from evaluation.schemas.mini_eval import MiniEvalResult
import redis

redis_client = redis.Redis(host='localhost', port=6380, db=0)
evaluator = MiniBrainEval(redis_client=redis_client)

# Get recent results
recent = evaluator.get_recent_results(limit=10)
for result in recent:
    print(f"{result.timestamp}: {result.cadence} - {len(result.issues)} issues")

# Get results for specific cadence
daily_results = evaluator.get_recent_results(cadence='daily', limit=7)
for result in daily_results:
    print(f"{result.timestamp}: {result.kpis.get('avg_accuracy', 'N/A')}")
```

### 7.3 Parsing Stored Results

```python
from evaluation.schemas.mini_eval import MiniEvalResult
import json

# From JSON file
with open('_bmad-output/brain-eval/daily/2026-03-01.json') as f:
    data = json.load(f)
    result = MiniEvalResult.from_dict(data)

# From Redis
import redis
redis_client = redis.Redis(host='localhost', port=6380, db=0)
data = redis_client.get('bmad:chiseai:brain:eval:mini:daily:2026-03-01')
if data:
    result = MiniEvalResult.from_json(data)

# Analyze result
if result.has_critical_issues():
    print("CRITICAL: P0 issues detected!")
    for issue in result.get_issues_by_severity('P0'):
        print(f"  {issue.description}")
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: No KPIs being collected

**Symptoms:**
```json
"kpis": { "status": "no_evaluator" }
```

**Resolution:**
This is expected if BrainEvaluator is not configured. To enable KPI collection:

```python
from brain.evaluation import BrainEvaluator
from evaluation.mini_brain_eval import MiniBrainEval

brain_eval = BrainEvaluator()
mini_eval = MiniBrainEval(brain_evaluator=brain_eval)
result = mini_eval.run_6h_eval()
```

#### Issue: Data freshness shows "no_client"

**Symptoms:**
```json
"data_freshness": {
  "redis": "no_client",
  "influxdb": "no_client"
}
```

**Resolution:**
Pass the appropriate clients when initializing:

```python
import redis
from influxdb import InfluxDBClient

redis_client = redis.Redis(host='localhost', port=6380)
influx_client = InfluxDBClient(host='localhost', port=8086)

evaluator = MiniBrainEval(
    redis_client=redis_client,
    influxdb_client=influx_client
)
```

#### Issue: Issues not detected from logs

**Symptoms:**
- Known errors in logs but `issues: []`

**Resolution:**
1. Check log file exists in expected locations
2. Verify LOG_PATTERNS match your log format
3. Specify custom log source:

```python
evaluator = MiniBrainEval()
issues = evaluator.detect_issues(log_source='/path/to/custom.log')
```

### 8.2 Debug Commands

**Check Redis keys:**
```bash
redis-cli -h localhost -p 6380 KEYS "bmad:chiseai:brain:eval:mini:*"
```

**View stored result:**
```bash
redis-cli -h localhost -p 6380 GET "bmad:chiseai:brain:eval:mini:6h:2026-03-01T12:00:00" | jq .
```

**Test Mini BrainEval:**
```bash
python3 -c "
from evaluation.mini_brain_eval import MiniBrainEval
e = MiniBrainEval()
r = e.run_6h_eval()
print(f'Issues: {len(r.issues)}')
print(f'Critical: {r.has_critical_issues()}')
"
```

---

## 9. References

### 9.1 Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| BrainEval Cadence Runbook | `docs/runbooks/brain-eval-cadence.md` | Scheduling and cadence system |
| Repeated Issues Runbook | `docs/runbooks/repeated-issues.md` | Issue detection and analysis |
| Brain Evaluation System | `src/brain/evaluation.py` | Core BrainEvaluator |

### 9.2 Source Code

| Component | Location |
|-----------|----------|
| Mini BrainEval Engine | `src/evaluation/mini_brain_eval.py` |
| Schema Definitions | `src/evaluation/schemas/mini_eval.py` |
| Scheduling Script | `scripts/evaluation/schedule_brain_eval.py` |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-01 | Platform Team | Initial runbook creation |

---

*This runbook was created per ST-BRAIN-EVAL-005 requirements and is ready for operational use.*
