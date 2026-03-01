# Repeated Issue Detection Runbook

> **Story:** ST-BRAIN-EVAL-005  
> **Last Updated:** 2026-03-01  
> **Owner:** Platform Team  
> **Status:** READY FOR USE

---

> **Safety Note:** This documentation covers evaluation and observability only. No risk caps, promotion gates, or live trading behavior are modified by this system.

---

## 1. Overview

### 1.1 What is Repeated Issue Detection?

**Repeated Issue Detection** is a system that identifies recurring problems across multiple evaluation runs by using fingerprinting to group similar issues. This enables:

- Early detection of systemic problems
- Trend analysis of issue severity over time
- Framework improvement recommendations
- Prioritized remediation guidance

### 1.2 Key Concepts

| Concept | Description |
|---------|-------------|
| **Fingerprinting** | Normalizing issue descriptions to identify duplicates |
| **Clustering** | Grouping similar issues by fingerprint |
| **Trend Analysis** | Tracking severity changes over time |
| **Recommendations** | Auto-generated suggestions based on patterns |

### 1.3 Benefits

| Benefit | Description |
|---------|-------------|
| **Reduce Noise** | Group 100+ similar issues into 5-10 clusters |
| **Prioritize Fixes** | Focus on issues occurring most frequently |
| **Track Progress** | Monitor if fixes are reducing recurrence |
| **Guide Improvements** | Get actionable recommendations for framework changes |

---

## 2. How Fingerprinting Works

### 2.1 Fingerprint Generation

Fingerprints are created by:

1. **Normalizing** the issue description (removing variable parts)
2. **Combining** with the issue category
3. **Hashing** to create a consistent identifier

**Format:** `{category}:{hash}`

**Example:**
```
db_connectivity:a1b2c3d4e5f6g7h8
```

### 2.2 Normalization Rules

The fingerprinting system removes these variable parts from descriptions:

| Variable Type | Pattern | Replacement |
|---------------|---------|-------------|
| Timestamps | `2026-03-01T12:00:00Z` | `<TIMESTAMP>` |
| UUIDs | `550e8400-e29b-41d4-a716-446655440000` | `<UUID>` |
| File paths | `/home/user/project/file.py` | `file.py` |
| Line numbers | `:123` | `:<LINE>` |
| PIDs | `pid=12345` | `<PID>` |
| Memory addresses | `0x7f8a1b2c3d4e` | `<ADDR>` |
| IP addresses | `192.168.1.1` | `<IP>` |
| Port numbers | `:8080` | `:<PORT>` |
| Session IDs | `session_abc123` | `<SESSION>` |
| Request IDs | `req_xyz789` | `<REQUEST>` |
| Hex numbers | `0x1a2b` | `<HEX>` |

### 2.3 Fingerprinting Examples

**Original Issues:**
```
Issue 1: "Redis connection timeout at 2026-03-01T12:00:00Z"
Issue 2: "Redis connection timeout at 2026-03-01T18:00:00Z"
Issue 3: "Redis connection timeout at 2026-03-02T06:00:00Z"
```

**Normalized (all three):**
```
"redis connection timeout at <timestamp>"
```

**Same Fingerprint:**
```
db_connectivity:a1b2c3d4e5f6g7h8
```

**Result:** All three issues are clustered together as one repeated issue with count=3.

### 2.4 Code Example

```python
from evaluation.fingerprinting import IssueFingerprint
from evaluation.schemas.mini_eval import Issue, IssueCategory, IssueSeverity

# Create two similar issues
issue1 = Issue.create(
    category=IssueCategory.DB_CONNECTIVITY,
    severity=IssueSeverity.P1,
    description="Redis connection timeout at 2026-03-01T12:00:00Z",
    source="test"
)

issue2 = Issue.create(
    category=IssueCategory.DB_CONNECTIVITY,
    severity=IssueSeverity.P1,
    description="Redis connection timeout at 2026-03-01T18:00:00Z",
    source="test"
)

# Generate fingerprints
fp1 = IssueFingerprint.generate(issue1)
fp2 = IssueFingerprint.generate(issue2)

print(fp1)  # db_connectivity:a1b2c3d4e5f6g7h8
print(fp2)  # db_connectivity:a1b2c3d4e5f6g7h8
print(fp1 == fp2)  # True - same fingerprint!
```

---

## 3. How to Interpret the Repeated Issue Report

### 3.1 Report Structure

```json
{
  "generated_at": "2026-03-01T12:00:00Z",
  "time_window_hours": 24,
  "total_issues": 45,
  "unique_issues": 8,
  "repeated_issues": [...],
  "top_recurring": [...],
  "recommendations": [...],
  "trend_analysis": {...}
}
```

### 3.2 Key Metrics

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| `total_issues` | All issues in time window | Volume indicator |
| `unique_issues` | Distinct fingerprint count | Problem diversity |
| `repeated_issues` | Issues with count > 1 | Recurring problems |
| `top_recurring` | Top 10 by occurrence | Priority targets |

### 3.3 Understanding Issue Clusters

Each `IssueCluster` contains:

```json
{
  "fingerprint": "db_connectivity:a1b2c3d4e5f6g7h8",
  "category": "db_connectivity",
  "count": 15,
  "first_seen": "2026-03-01T00:00:00Z",
  "last_seen": "2026-03-01T23:00:00Z",
  "examples": [
    {
      "issue_id": "...",
      "description": "Redis connection timeout...",
      "timestamp": "2026-03-01T22:00:00Z",
      "severity": "P1"
    }
  ],
  "severity_trend": "stable",
  "severity_history": ["P1", "P1", "P1", "P2", "P1"]
}
```

**Key Fields:**

| Field | Description | Use |
|-------|-------------|-----|
| `count` | Occurrences | Prioritization (higher = more urgent) |
| `first_seen` / `last_seen` | Time range | Duration of problem |
| `examples` | Recent instances | Context for debugging |
| `severity_trend` | Trend direction | Improving/worsening/stable |
| `severity_history` | Severity over time | Pattern analysis |

### 3.4 Severity Trends

| Trend | Meaning | Action |
|-------|---------|--------|
| `improving` | Severity decreasing over time | Monitor, may resolve on its own |
| `stable` | Severity consistent | Investigate root cause |
| `worsening` | Severity increasing | **Immediate attention required** |

**Trend Calculation:**
- Compares first half vs second half of severity history
- Maps P0=0, P1=1, P2=2, P3=3 (lower = worse)
- "improving" if second half > first half * 1.1
- "worsening" if second half < first half * 0.9

### 3.5 Trend Analysis

The `trend_analysis` section provides detailed breakdowns:

```json
{
  "issues_by_hour": {
    "2026-03-01T00": 2,
    "2026-03-01T06": 5,
    "2026-03-01T12": 8,
    "2026-03-01T18": 3
  },
  "categories_trend": {
    "db_connectivity": {
      "count": 15,
      "hours": {
        "2026-03-01T00": 1,
        "2026-03-01T06": 4,
        "2026-03-01T12": 8,
        "2026-03-01T18": 2
      }
    }
  },
  "severity_distribution": {
    "P0": 2,
    "P1": 15,
    "P2": 20,
    "P3": 8
  },
  "time_range_hours": 24
}
```

**Use Cases:**
- `issues_by_hour`: Identify peak problem times
- `categories_trend`: Focus remediation efforts
- `severity_distribution`: Assess overall health

---

## 4. How to Prioritize Fixes

### 4.1 Priority Matrix

| Priority | Criteria | Response Time |
|----------|----------|---------------|
| **P0 - Critical** | Any P0 issue, count > 0 | Immediate |
| **P1 - High** | Count > 10, worsening trend | < 4 hours |
| **P2 - Medium** | Count > 5, stable trend | < 24 hours |
| **P3 - Low** | Count < 5, improving trend | Monitor |

### 4.2 Decision Framework

```
┌─────────────────────────────────────────────────────────────┐
│                 Issue Prioritization Flow                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Start: Review repeated_issues list                        │
│           │                                                 │
│           ▼                                                 │
│   ┌───────────────────┐                                     │
│   │ Has P0 issues?    │──── Yes ───▶ IMMEDIATE ACTION      │
│   └─────────┬─────────┘               │                    │
│             │ No                      │                    │
│             ▼                         │                    │
│   ┌───────────────────┐               │                    │
│   │ Trend worsening?  │──── Yes ───▶ HIGH PRIORITY         │
│   └─────────┬─────────┐               │                    │
│             │ No                      │                    │
│             ▼                         │                    │
│   ┌───────────────────┐               │                    │
│   │ Count > 10?       │──── Yes ───▶ MEDIUM PRIORITY       │
│   └─────────┬─────────┘               │                    │
│             │ No                      │                    │
│             ▼                         │                    │
│   ┌───────────────────┐               │                    │
│   │ Trend improving?  │──── Yes ───▶ MONITOR               │
│   └─────────┬─────────┘               │                    │
│             │ No                      │                    │
│             ▼                         │                    │
│        INVESTIGATE                    │                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Action Matrix

| Issue Type | Recommended Action | Framework Impact |
|------------|-------------------|------------------|
| **P0 Critical** | Fix immediately, halt other work | High - may need hotfix |
| **Recurring Patterns** | Framework improvement | Medium - schedule for sprint |
| **One-off Issues** | Monitor for recurrence | Low - add to backlog |
| **Improving Trends** | Document, no action | None - continue monitoring |

### 4.4 Category-Specific Actions

| Category | Count Threshold | Recommended Action |
|----------|-----------------|-------------------|
| `db_connectivity` | > 5 | Implement connection pooling, review timeouts |
| `file_access` | > 3 | Review permissions, validate paths |
| `env_slowdown` | > 5 | Scale resources, optimize memory |
| `tool_error` | > 3 | Add retry logic, circuit breaker pattern |

---

## 5. Example Report Walkthrough

### 5.1 Scenario: Database Connectivity Issues

**Report:**
```json
{
  "generated_at": "2026-03-01T12:00:00Z",
  "time_window_hours": 24,
  "total_issues": 45,
  "unique_issues": 8,
  "repeated_issues": [
    {
      "fingerprint": "db_connectivity:a1b2c3d4e5f6g7h8",
      "category": "db_connectivity",
      "count": 15,
      "first_seen": "2026-03-01T00:00:00Z",
      "last_seen": "2026-03-01T12:00:00Z",
      "examples": [
        {
          "issue_id": "issue-001",
          "description": "Detected db_connectivity issue: ConnectionRefusedError to Redis at localhost:6380",
          "timestamp": "2026-03-01T11:00:00Z",
          "severity": "P1"
        }
      ],
      "severity_trend": "worsening",
      "severity_history": ["P2", "P2", "P1", "P1", "P1"]
    },
    {
      "fingerprint": "env_slowdown:b2c3d4e5f6g7h8i9",
      "category": "env_slowdown",
      "count": 8,
      "first_seen": "2026-03-01T06:00:00Z",
      "last_seen": "2026-03-01T12:00:00Z",
      "examples": [],
      "severity_trend": "stable",
      "severity_history": ["P2", "P2", "P2"]
    }
  ],
  "top_recurring": [
    {
      "fingerprint": "db_connectivity:a1b2c3d4e5f6g7h8",
      "category": "db_connectivity",
      "count": 15,
      "first_seen": "2026-03-01T00:00:00Z",
      "last_seen": "2026-03-01T12:00:00Z",
      "examples": [],
      "severity_trend": "worsening",
      "severity_history": ["P2", "P2", "P1", "P1", "P1"]
    }
  ],
  "recommendations": [
    "Consider implementing connection pooling for database connections",
    "Review database connection timeout settings"
  ],
  "trend_analysis": {
    "issues_by_hour": {
      "2026-03-01T06": 5,
      "2026-03-01T12": 15
    },
    "categories_trend": {
      "db_connectivity": { "count": 15 },
      "env_slowdown": { "count": 8 }
    },
    "severity_distribution": {
      "P1": 15,
      "P2": 30
    }
  }
}
```

### 5.2 Analysis

**Immediate Observations:**
1. **Top Issue:** db_connectivity with 15 occurrences
2. **Trend:** Worsening (P2 → P1)
3. **Peak Time:** 12:00 UTC (15 issues in this hour)
4. **Distribution:** All P1 and P2, no P0 or P3

**Priority Assessment:**
- ✅ No P0 issues (good)
- ⚠️ db_connectivity has worsening trend (HIGH PRIORITY)
- ⚠️ 15 occurrences in 24 hours (above threshold)
- ✅ Recommendations provided (actionable)

**Recommended Actions:**
1. **Immediate:** Check Redis container status
2. **Short-term:** Review connection pooling configuration
3. **Medium-term:** Adjust timeout settings
4. **Long-term:** Implement circuit breaker pattern

### 5.3 Real-World Scenarios

#### Scenario 1: Spiking Database Errors

**Pattern:** 
- db_connectivity count jumps from 5 to 50 in one hour
- Severity trend: worsening

**Diagnosis:**
- Database container may be restarting
- Network partition possible
- Connection pool exhaustion

**Actions:**
```bash
# Check database status
docker ps | grep redis
docker logs chiseai-redis --tail 100

# Check connection count
redis-cli -h localhost -p 6380 INFO clients

# Check network
ping chiseai-redis
```

#### Scenario 2: Gradual Memory Pressure

**Pattern:**
- env_slowdown count slowly increasing over days
- Severity trend: stable but elevated
- Examples mention "memory pressure"

**Diagnosis:**
- Memory leak in application
- Growing dataset size
- Insufficient container resources

**Actions:**
```bash
# Check memory usage
docker stats chiseai-api --no-stream

# Check process memory
ps aux --sort=-%mem | head -10

# Consider scaling
docker update --memory 4g chiseai-api
```

#### Scenario 3: Tool API Failures

**Pattern:**
- tool_error count spiking at specific times
- Category: tool_error
- Examples mention "API error", "HTTPError"

**Diagnosis:**
- External API rate limiting
- API endpoint changes
- Network connectivity issues

**Actions:**
```bash
# Check API health
curl -I https://api.example.com/health

# Review rate limits
# (varies by API provider)

# Consider retry logic
# Update tool configuration
```

---

## 6. Programmatic Access

### 6.1 Generating Reports

```python
from evaluation.repeated_issue_detector import RepeatedIssueDetector
import redis

# Initialize with Redis
redis_client = redis.Redis(host='localhost', port=6380, db=0)
detector = RepeatedIssueDetector(redis_client=redis_client)

# Generate 24-hour report
report = detector.detect_repeated_issues(
    time_window_hours=24,
    min_occurrences=2
)

# Print report
print(report)
```

### 6.2 Accessing Report Data

```python
# Basic stats
print(f"Total issues: {report.total_issues}")
print(f"Unique issues: {report.unique_issues}")
print(f"Repeated issues: {len(report.repeated_issues)}")

# Top recurring issues
for issue in report.top_recurring[:5]:
    print(f"\n{issue.category}: {issue.count} occurrences")
    print(f"  Trend: {issue.severity_trend}")
    print(f"  First: {issue.first_seen}")
    print(f"  Last: {issue.last_seen}")

# Recommendations
print("\nRecommendations:")
for rec in report.recommendations:
    print(f"  - {rec}")

# Trend analysis
if report.trend_analysis:
    print("\nSeverity Distribution:")
    for severity, count in report.trend_analysis.severity_distribution.items():
        print(f"  {severity}: {count}")
```

### 6.3 Getting Historical Reports

```python
# Get recent reports
reports = detector.get_recent_reports(limit=10)
for report in reports:
    print(f"{report.generated_at}: {report.total_issues} issues")

# Get specific report by ID
report = detector.get_report_by_id("20260301_120000")
if report:
    print(report)
```

### 6.4 Trend Analysis Only

```python
# Get trend analysis without full report
trends = detector.get_trend_analysis(time_window_hours=24)

print("Issues by hour:")
for hour, count in sorted(trends.issues_by_hour.items()):
    print(f"  {hour}: {count}")

print("\nCategory breakdown:")
for category, data in trends.categories_trend.items():
    print(f"  {category}: {data['count']} issues")
```

---

## 7. Integration with BrainEval

### 7.1 Weekly Evaluation Integration

The weekly BrainEval automatically includes repeated issue detection:

```python
from evaluation.mini_brain_eval import MiniBrainEval
from evaluation.repeated_issue_detector import RepeatedIssueDetector

# Run weekly eval (includes repeated issue analysis)
evaluator = MiniBrainEval(redis_client=redis)
result = evaluator.run_weekly_eval()

# The trend_analysis includes repeated issue data
if 'trend_analysis' in result.kpis:
    print(f"Trend direction: {result.kpis['trend_analysis']['trend_direction']}")
```

### 7.2 Standalone Detection

For ad-hoc analysis:

```python
from evaluation.repeated_issue_detector import RepeatedIssueDetector

detector = RepeatedIssueDetector(redis_client=redis)

# 24-hour analysis
report_24h = detector.detect_repeated_issues(time_window_hours=24)

# 7-day analysis
report_7d = detector.detect_repeated_issues(time_window_hours=168)

# Compare
print(f"24h: {report_24h.total_issues} issues, {len(report_24h.repeated_issues)} repeated")
print(f"7d:  {report_7d.total_issues} issues, {len(report_7d.repeated_issues)} repeated")
```

---

## 8. Troubleshooting

### 8.1 Common Issues

#### Issue: No repeated issues detected

**Symptoms:**
```json
{
  "total_issues": 50,
  "unique_issues": 50,
  "repeated_issues": []
}
```

**Diagnosis:**
- All issues are unique (good!)
- Fingerprinting may be too aggressive
- Check normalization rules

**Resolution:**
1. Review fingerprinting patterns in `fingerprinting.py`
2. Verify LOG_PATTERNS match your log format
3. Consider adjusting normalization rules if needed

#### Issue: Too many repeated issues

**Symptoms:**
```json
{
  "total_issues": 100,
  "unique_issues": 3,
  "repeated_issues": [3 very large clusters]
}
```

**Diagnosis:**
- Same issue occurring repeatedly
- Root cause not addressed
- Possible systemic problem

**Resolution:**
1. Review top_recurring for root cause
2. Implement recommended fixes
3. Monitor for improvement

#### Issue: Incorrect fingerprinting

**Symptoms:**
- Different issues grouped together
- Same issues not grouped

**Diagnosis:**
- Normalization rules may be too aggressive or too lenient
- Category may not match

**Resolution:**
1. Review normalization output:
```python
from evaluation.fingerprinting import IssueFingerprint
normalized = IssueFingerprint.normalize_description("your issue description")
print(normalized)
```

2. Adjust patterns in `fingerprinting.py` if needed

### 8.2 Debug Commands

**Check fingerprinting:**
```python
from evaluation.fingerprinting import IssueFingerprint
from evaluation.schemas.mini_eval import Issue, IssueCategory, IssueSeverity

issue = Issue.create(
    category=IssueCategory.DB_CONNECTIVITY,
    severity=IssueSeverity.P1,
    description="Your test description here",
    source="test"
)

fp = IssueFingerprint.generate(issue)
normalized = IssueFingerprint.normalize_description(issue.description)

print(f"Fingerprint: {fp}")
print(f"Normalized: {normalized}")
```

**View stored reports:**
```bash
redis-cli -h localhost -p 6380 KEYS "bmad:chiseai:brain:eval:repeated_issues:*"
```

**Get specific report:**
```bash
redis-cli -h localhost -p 6380 GET "bmad:chiseai:brain:eval:repeated_issues:20260301_120000" | jq .
```

---

## 9. Best Practices

### 9.1 Review Cadence

| Cadence | Review Type | Focus |
|---------|-------------|-------|
| **6h** | Quick glance | Check for P0 issues |
| **Daily** | Standard review | Top 5 recurring issues |
| **Weekly** | Deep dive | All repeated issues, trends |

### 9.2 Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| `total_issues` (24h) | > 50 | > 100 |
| `unique_issues` (24h) | > 20 | > 40 |
| Single cluster count | > 10 | > 25 |
| Worsening trends | > 2 | > 5 |

### 9.3 Documentation

When addressing repeated issues:

1. **Document the fix** in PR description
2. **Link to fingerprint** for tracking
3. **Update runbook** if new pattern discovered
4. **Monitor** for recurrence after fix

---

## 10. References

### 10.1 Related Documents

| Document | Location | Purpose |
|----------|----------|---------|
| BrainEval Cadence Runbook | `docs/runbooks/brain-eval-cadence.md` | Scheduling system |
| Mini BrainEval Runbook | `docs/runbooks/mini-brain-eval.md` | Mini evaluation details |
| Incident Response | `docs/runbooks/incident_response.md` | Incident handling |

### 10.2 Source Code

| Component | Location |
|-----------|----------|
| Repeated Issue Detector | `src/evaluation/repeated_issue_detector.py` |
| Fingerprinting | `src/evaluation/fingerprinting.py` |
| Schema Definitions | `src/evaluation/schemas/mini_eval.py` |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-01 | Platform Team | Initial runbook creation |

---

*This runbook was created per ST-BRAIN-EVAL-005 requirements and is ready for operational use.*
