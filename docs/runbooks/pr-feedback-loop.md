# PR Feedback Loop Runbook

## Overview

The PR Feedback Loop system provides continuous improvement for the AI Swarm Autonomous PR Pipeline through outcome tracking, metric analysis, and automatic rule adjustment suggestions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PR FEEDBACK LOOP ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │ PR Lifecycle     │────>│ Outcome Tracker  │────>│ Feedback Loop    │    │
│  │ (Merge/Reject)   │     │ (Redis Storage)  │     │ (Analysis)       │    │
│  └──────────────────┘     └──────────────────┘     └────────┬─────────┘    │
│                                                             │               │
│                              ┌──────────────────────────────┼──────────┐   │
│                              │                              │          │   │
│                              ▼                              ▼          ▼   │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                      OUTPUTS                                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│  │  │ Weekly       │  │ Rule         │  │ Grafana      │             │   │
│  │  │ Reports      │  │ Adjustments  │  │ Dashboard    │             │   │
│  │  │ (Discord)    │  │ (Redis)      │  │ (InfluxDB)   │             │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Outcome Tracker (`scripts/pr_lifecycle/outcome_tracker.py`)

**Purpose:** Track PR outcomes and calculate success metrics

**Key Classes:**
- `PROutcome` - Represents a PR outcome
- `SuccessMetrics` - Aggregated success metrics
- `OutcomeTracker` - Main tracking interface

**Redis Keys:**
- `bmad:chiseai:pr:outcome:<pr_number>` - Outcome data
- `bmad:chiseai:pr:outcome:all` - All outcome IDs
- `bmad:chiseai:pr:outcome:type:<type>` - Outcomes by type
- `bmad:chiseai:pr:outcome:date:<YYYY-MM-DD>` - Daily index
- `bmad:chiseai:pr:metrics:daily:<YYYY-MM-DD>` - Daily metrics

**Data Retention:** 30 days

### 2. Feedback Loop (`scripts/pr_lifecycle/feedback_loop.py`)

**Purpose:** Analyze outcomes and generate improvement suggestions

**Key Classes:**
- `RuleAdjustmentSuggestion` - Suggested rule changes
- `WeeklyReport` - Weekly feedback report
- `FeedbackLoop` - Main analysis interface

**Redis Keys:**
- `bmad:chiseai:pr:rule_adjustment:<id>` - Suggestion details
- `bmad:chiseai:pr:rule_adjustment:pending` - Pending suggestions
- `bmad:chiseai:pr:report:<id>` - Report data
- `bmad:chiseai:pr:report:all` - All report IDs

**Data Retention:** 90 days

### 3. Metrics Module (`src/pr_lifecycle/metrics.py`)

**Purpose:** Metric definitions and export functions

**Key Classes:**
- `PRMetric` - Individual metric
- `PRPipelineMetrics` - Complete metrics set
- `MetricsExporter` - Export helpers

**Export Formats:**
- Prometheus exposition format
- InfluxDB line protocol
- JSON

## Metrics Explained

### Volume Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `total_prs` | Total PRs processed | N/A |
| `merged_prs` | Successfully merged | >90% of total |
| `rejected_prs` | Rejected PRs | <10% of total |
| `rolled_back_prs` | Merged then rolled back | <5% of merged |

### Success Rate Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `auto_merge_success_rate` | % of auto-merges that stayed merged | >95% |
| `review_accuracy` | % of reviews that were correct | >95% |
| `overall_success_rate` | % of PRs that merged successfully | >95% |

### Time Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `avg_time_to_merge` | Average time from open to merge | <60 min |
| `p95_time_to_merge` | 95th percentile time to merge | <120 min |

### Auto-Approval Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `auto_approved_count` | Number of auto-approved PRs | N/A |
| `auto_approved_success_rate` | % of auto-approvals that stayed merged | >95% |

## How to Interpret Metrics

### Success Rate Trends

**Rising Success Rate:**
- System is improving
- Review criteria may be well-calibrated
- Consider documenting what's working

**Falling Success Rate:**
- Investigate root cause
- Check for new failure patterns
- Review recent changes to criteria

### Time to Merge Trends

**Increasing Time:**
- CI pipeline may be slowing down
- Review queue may be backed up
- Consider parallelizing checks

**Decreasing Time:**
- System is becoming more efficient
- Good sign for developer velocity

### Rollback Rate

**High Rollback Rate (>5%):**
- Auto-approval criteria may be too lenient
- Review process may be missing issues
- Action: Tighten criteria or enhance checks

**Low Rollback Rate (<2%):**
- System is conservative but safe
- May be able to auto-approve more
- Action: Consider lowering threshold

## Rule Adjustment Suggestions

### Types of Suggestions

1. **Auto-Approval Threshold**
   - Increase when rollback rate >10%
   - Decrease when rollback rate <2% and volume high

2. **Merge Criteria**
   - Optimize CI pipeline when time to merge >120 min
   - Add checks when rollback rate high

3. **Review Threshold**
   - Enhance checklist when manual review rollback rate >5%

### Applying Suggestions

```bash
# View pending suggestions
python3 scripts/pr_lifecycle/feedback_loop.py pending

# Apply a suggestion
python3 scripts/pr_lifecycle/feedback_loop.py apply \
    --suggestion-id suggestion_2026-02-25T00:00:00Z_001 \
    --by "human-operator"
```

## Weekly Reports

### Report Contents

Each weekly report includes:
- Volume summary (total, merged, rejected, rolled back)
- Success rates (overall, auto-merge, review accuracy)
- Time metrics (average, P95)
- Trends vs previous week
- Key insights
- Action items
- Rule adjustment suggestions

### Generating Reports

```bash
# Generate weekly report
python3 scripts/pr_lifecycle/feedback_loop.py weekly

# Generate and post to Discord
python3 scripts/pr_lifecycle/feedback_loop.py weekly --post-discord

# Run full weekly cycle (report + export + Discord)
python3 scripts/pr_lifecycle/feedback_loop.py weekly-cycle
```

### Report Schedule

Reports are automatically generated and posted every Monday at 09:00 UTC via Woodpecker cron job.

## Grafana Dashboard

### Dashboard URL

http://host.docker.internal:3001/d/pr-pipeline-metrics

### Key Panels

1. **Volume Over Time** - PR volume trends
2. **Success Rate** - Overall and auto-merge success rates
3. **Time to Merge** - Average and P95 times
4. **Rolled Back PRs** - Rollback count and rate
5. **Active PRs** - Current queue depth

### Query Examples

```sql
-- Total PRs in time range
SELECT sum("value") FROM "pr_pipeline_volume" 
WHERE "metric" = 'total' AND $timeFilter

-- Success rate over time
SELECT mean("value") FROM "pr_pipeline_success" 
WHERE "metric" = 'overall' AND $timeFilter 
GROUP BY time(1h)

-- Average time to merge
SELECT mean("value") FROM "pr_pipeline_time" 
WHERE "metric" = 'avg' AND $timeFilter
```

## Troubleshooting

### Metrics Not Updating

1. Check Redis connectivity:
   ```bash
   redis-cli -h host.docker.internal -p 6380 PING
   ```

2. Verify outcome tracker is recording:
   ```bash
   python3 scripts/pr_lifecycle/outcome_tracker.py history --days 1
   ```

3. Check InfluxDB export:
   ```bash
   python3 scripts/pr_lifecycle/feedback_loop.py export --days 1
   ```

### High Rollback Rate

1. Analyze rollback patterns:
   ```bash
   python3 scripts/pr_lifecycle/feedback_loop.py analyze --days 7
   ```

2. Review recent suggestions:
   ```bash
   python3 scripts/pr_lifecycle/feedback_loop.py pending
   ```

3. Consider tightening auto-approval criteria

### Reports Not Posting to Discord

1. Check webhook URL:
   ```bash
   echo $DISCORD_WEBHOOK_URL
   ```

2. Test manually:
   ```bash
   python3 scripts/pr_lifecycle/feedback_loop.py weekly --post-discord
   ```

3. Check Woodpecker logs for cron job errors

## Common Operations

### Record a Merge Outcome

```bash
python3 scripts/pr_lifecycle/outcome_tracker.py record-merge \
    --pr-number 123 \
    --story-id ST-TEST-001 \
    --branch feature/test-branch \
    --head-sha abc123 \
    --opened-by agent-1 \
    --merged-by agent-2 \
    --auto-merged \
    --time-to-merge-min 45.5
```

### Record a Rollback

```bash
python3 scripts/pr_lifecycle/outcome_tracker.py record-rollback \
    --pr-number 123 \
    --reason "Critical bug discovered in production" \
    --rollback-sha def456
```

### Calculate Metrics

```bash
# Last 7 days
python3 scripts/pr_lifecycle/outcome_tracker.py metrics --days 7

# Last 30 days
python3 scripts/pr_lifecycle/outcome_tracker.py metrics --days 30
```

### Export to InfluxDB

```bash
python3 scripts/pr_lifecycle/feedback_loop.py export --days 7
```

## Best Practices

1. **Monitor Weekly Reports** - Review every Monday for trends
2. **Act on Suggestions** - Apply or dismiss suggestions promptly
3. **Track False Positives** - Document why rollbacks occurred
4. **Set Alerts** - Configure Grafana alerts for key thresholds
5. **Review Monthly** - Deep dive into monthly trends quarterly

## Integration with PR Lifecycle

The feedback loop integrates with the PR lifecycle system:

1. When a PR merges, `outcome_tracker.py` records the outcome
2. When a PR rolls back, the rollback is recorded
3. Weekly analysis generates suggestions
4. Suggestions inform auto-approval criteria adjustments

## Future Enhancements

Planned improvements:
- ML-based pattern detection
- Automated rule adjustment (with human approval)
- Integration with incident response system
- Historical trend analysis
- Peer comparison metrics

## Support

For issues or questions:
1. Check this runbook
2. Review recent weekly reports
3. Consult design doc: `docs/designs/pr-feedback-loop.md`
4. Run diagnostics: `python3 scripts/pr_lifecycle/feedback_loop.py analyze`
